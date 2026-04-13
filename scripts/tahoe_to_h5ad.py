#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convert Tahoe-100M Parquet shards to per-cell-line h5ad files.

Data format (from actual parquet inspection):
- Each shard contains ALL ~50 cell lines (cannot skip shards by cell line)
- Columns: genes (sparse indices), expressions (sparse values), cell_line_id, drug, sample, ...
- Must scan all 3388 shards and filter by cell_line_id

Usage:
    python3 tahoe_to_h5ad.py --cell-lines C32 --out-dir ~/data/VCWorld
    python3 tahoe_to_h5ad.py --cell-lines C32 HOP62 --workers 8
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HF_REPO = "tahoebio/Tahoe-100M"
TOTAL_SHARDS = 3388

CELL_LINE_MAP = {
    "C32":      "CVCL_1097",
    "HOP62":    "CVCL_1285",
    "HepG2C3A": "CVCL_1098",
    "Hs766T":   "CVCL_0334",
    "PANC1":    "CVCL_0480",
}


def setup_hf(endpoint: str) -> None:
    os.environ["HF_ENDPOINT"] = endpoint
    os.environ["HUGGINGFACE_HUB_VERBOSITY"] = "warning"


def hf_download(filename: str, cache_dir: Path) -> Path:
    from huggingface_hub import hf_hub_download
    local = hf_hub_download(
        repo_id=HF_REPO,
        filename=filename,
        repo_type="dataset",
        local_dir=str(cache_dir),
    )
    return Path(local)


def load_gene_vocabulary(cache_dir: Path) -> Dict[int, str]:
    """Load gene index -> gene name mapping. Returns empty dict if unavailable."""
    import json
    try:
        vocab_path = hf_download("metadata/gene_vocabulary.json", cache_dir)
        with open(vocab_path) as f:
            vocab = json.load(f)
        if not vocab:
            return {}
        first_key = next(iter(vocab))
        if isinstance(first_key, str) and not first_key.isdigit():
            return {int(v): k for k, v in vocab.items()}
        else:
            return {int(k): v for k, v in vocab.items()}
    except Exception as e:
        print(f"  [vocab] Could not load gene vocabulary: {e}")
        return {}


def shard_to_sparse(df_cl, n_genes: int):
    """
    Convert filtered shard DataFrame to sparse matrix.
    Vectorized — avoids iterrows() which is 100x slower.
    """
    import numpy as np
    from scipy.sparse import csr_matrix

    n_cells = len(df_cl)
    if n_cells == 0:
        return csr_matrix((0, n_genes), dtype=np.float32)

    row_idx: List[int] = []
    col_idx: List[int] = []
    data: List[float] = []

    for i, (genes, exprs) in enumerate(
        zip(df_cl["genes"].tolist(), df_cl["expressions"].tolist())
    ):
        for g, e in zip(genes, exprs):
            if 0 <= g < n_genes:
                row_idx.append(i)
                col_idx.append(g)
                data.append(e)

    if not data:
        return csr_matrix((n_cells, n_genes), dtype=np.float32)

    return csr_matrix(
        (np.array(data, dtype=np.float32),
         (np.array(row_idx, dtype=np.int32), np.array(col_idx, dtype=np.int32))),
        shape=(n_cells, n_genes),
    )


def download_shard(shard_idx: int, cache_dir: Path) -> Optional[Path]:
    """Download one shard, return local path or None on error."""
    fname = f"data/train-{shard_idx:05d}-of-{TOTAL_SHARDS:05d}.parquet"
    try:
        return hf_download(fname, cache_dir)
    except Exception as e:
        print(f"  [dl] ERROR shard {shard_idx}: {e}")
        return None


def convert_cell_line(
    vcworld_name: str,
    cvcl_id: str,
    out_dir: Path,
    cache_dir: Path,
    workers: int = 4,
) -> None:
    """
    Stream-write h5ad via h5py to avoid peak memory from vstack.
    Writes X (sparse CSR stored as data/indices/indptr), obs, and var
    incrementally — never holds more than one batch in memory at once.
    """
    import pandas as pd
    import numpy as np
    import h5py
    from scipy.sparse import csr_matrix

    out_path = out_dir / f"{vcworld_name}_cells.h5ad"
    if out_path.exists():
        print(f"[{vcworld_name}] Already exists: {out_path}, skipping.")
        return

    print(f"[{vcworld_name}] Loading gene vocabulary...")
    gene_vocab = load_gene_vocabulary(cache_dir)
    n_genes = (max(gene_vocab.keys()) + 1) if gene_vocab else 20000
    gene_names = [gene_vocab.get(i, f"gene_{i}") for i in range(n_genes)]
    print(f"[{vcworld_name}] {n_genes} genes")

    META_COLS = ["drug", "sample", "BARCODE_SUB_LIB_ID",
                 "cell_line_id", "moa-fine", "canonical_smiles", "plate"]
    META_OUT  = ["drug", "sample", "BARCODE_SUB_LIB_ID",
                 "cell_line_id", "moa_fine", "canonical_smiles", "plate"]

    tmp_path = out_dir / f"{vcworld_name}_cells.h5ad.tmp"
    tmp_path.unlink(missing_ok=True)

    # Pre-allocate resizable h5py datasets
    with h5py.File(tmp_path, "w") as f:
        # CSR components — resizable along cell axis
        f.create_dataset("X/data",    shape=(0,), maxshape=(None,), dtype="float32", chunks=True)
        f.create_dataset("X/indices", shape=(0,), maxshape=(None,), dtype="int32",   chunks=True)
        f.create_dataset("X/indptr",  shape=(1,), maxshape=(None,), dtype="int64",   chunks=True,
                         data=np.array([0], dtype=np.int64))
        for col in META_OUT:
            f.create_dataset(f"obs/{col}", shape=(0,), maxshape=(None,),
                             dtype=h5py.special_dtype(vlen=str), chunks=True)

    total_cells = 0
    total_nnz   = 0

    def process_shard(shard_idx: int):
        local = download_shard(shard_idx, cache_dir)
        if local is None:
            return shard_idx, None, None
        try:
            df = pd.read_parquet(local, columns=["cell_line_id", "genes", "expressions"]
                                 + [c for c in META_COLS if c != "cell_line_id"])
        except Exception as e:
            print(f"  [read] ERROR shard {shard_idx}: {e}")
            return shard_idx, None, None
        df_cl = df[df["cell_line_id"] == cvcl_id]
        if df_cl.empty:
            return shard_idx, None, None
        X_chunk = shard_to_sparse(df_cl, n_genes)
        meta_chunk = df_cl[[c for c in META_COLS if c in df_cl.columns]].copy()
        meta_chunk = meta_chunk.rename(columns={"moa-fine": "moa_fine"})
        return shard_idx, X_chunk, meta_chunk

    print(f"[{vcworld_name}] Scanning {TOTAL_SHARDS} shards with {workers} workers...")
    shard_indices = list(range(TOTAL_SHARDS))

    with h5py.File(tmp_path, "a") as f:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(process_shard, i): i for i in shard_indices}
            done = 0
            for fut in as_completed(futures):
                done += 1
                _, X_chunk, meta_chunk = fut.result()
                if X_chunk is None:
                    if done % 200 == 0 or done == TOTAL_SHARDS:
                        print(f"[{vcworld_name}]   {done}/{TOTAL_SHARDS} shards done, "
                              f"{total_cells} cells so far")
                    continue

                n = X_chunk.shape[0]
                nnz = X_chunk.nnz

                # Append CSR data
                ds_data = f["X/data"]
                ds_data.resize(total_nnz + nnz, axis=0)
                ds_data[total_nnz:] = X_chunk.data

                ds_idx = f["X/indices"]
                ds_idx.resize(total_nnz + nnz, axis=0)
                ds_idx[total_nnz:] = X_chunk.indices

                ds_ptr = f["X/indptr"]
                new_ptr = X_chunk.indptr[1:] + total_nnz
                old_len = ds_ptr.shape[0]
                ds_ptr.resize(old_len + n, axis=0)
                ds_ptr[old_len:] = new_ptr

                # Append obs metadata
                for col in META_OUT:
                    ds = f[f"obs/{col}"]
                    vals = meta_chunk[col].fillna("").astype(str).values if col in meta_chunk.columns \
                           else np.array([""] * n)
                    ds.resize(total_cells + n, axis=0)
                    ds[total_cells:] = vals

                total_cells += n
                total_nnz   += nnz

                if done % 200 == 0 or done == TOTAL_SHARDS:
                    print(f"[{vcworld_name}]   {done}/{TOTAL_SHARDS} shards done, "
                          f"{total_cells} cells so far")

    if total_cells == 0:
        print(f"[{vcworld_name}] No cells found for {cvcl_id}!")
        tmp_path.unlink(missing_ok=True)
        return

    # Finalise: build proper h5ad from the streamed h5 file
    print(f"[{vcworld_name}] Finalising h5ad ({total_cells} cells x {n_genes} genes)...")
    import anndata as ad

    with h5py.File(tmp_path, "r") as f:
        data    = f["X/data"][:]
        indices = f["X/indices"][:]
        indptr  = f["X/indptr"][:]
        X = csr_matrix((data, indices, indptr), shape=(total_cells, n_genes))
        obs_dict = {col: f[f"obs/{col}"][:].astype(str).tolist() for col in META_OUT}

    obs = pd.DataFrame(obs_dict)
    var = pd.DataFrame(index=gene_names)
    var.index.name = "gene_name"

    adata = ad.AnnData(X=X, obs=obs, var=var)
    adata.write_h5ad(out_path)
    tmp_path.unlink(missing_ok=True)
    size = out_path.stat().st_size / 1e9
    print(f"[{vcworld_name}] Saved: {out_path} ({size:.2f} GB, {total_cells} cells)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Tahoe-100M shards to h5ad")
    parser.add_argument("--cell-lines", nargs="+",
                        default=["C32", "HOP62", "HepG2C3A", "Hs766T", "PANC1"])
    parser.add_argument("--out-dir", default="~/data/VCWorld")
    parser.add_argument("--hf-endpoint", default="https://hf-mirror.com")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel shard download workers (default: 4)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir / "_hf_cache"
    cache_dir.mkdir(exist_ok=True)

    setup_hf(args.hf_endpoint)

    for vcworld_name in args.cell_lines:
        cvcl_id = CELL_LINE_MAP.get(vcworld_name)
        if not cvcl_id:
            print(f"Unknown cell line: {vcworld_name}. Valid: {list(CELL_LINE_MAP)}")
            continue

        print(f"\n{'='*60}")
        print(f"Processing: {vcworld_name} ({cvcl_id})")
        print(f"{'='*60}")
        convert_cell_line(vcworld_name, cvcl_id, out_dir, cache_dir, args.workers)

    print("\n=== Done ===")
    for f in sorted(out_dir.glob("*.h5ad")):
        print(f"  {f.name}  {f.stat().st_size / 1e9:.2f} GB")


if __name__ == "__main__":
    main()
