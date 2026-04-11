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
    import pandas as pd
    import numpy as np
    import anndata as ad
    from scipy.sparse import vstack as sp_vstack, csr_matrix

    out_path = out_dir / f"{vcworld_name}_cells.h5ad"
    if out_path.exists():
        print(f"[{vcworld_name}] Already exists: {out_path}, skipping.")
        return

    # Load gene vocabulary (best-effort)
    print(f"[{vcworld_name}] Loading gene vocabulary...")
    gene_vocab = load_gene_vocabulary(cache_dir)
    n_genes = (max(gene_vocab.keys()) + 1) if gene_vocab else 20000
    gene_names = [gene_vocab.get(i, f"gene_{i}") for i in range(n_genes)]
    print(f"[{vcworld_name}] {n_genes} genes")

    META_COLS = ["drug", "sample", "BARCODE_SUB_LIB_ID",
                 "cell_line_id", "moa-fine", "canonical_smiles", "plate"]

    chunks_X = []
    chunks_meta = []
    total_cells = 0
    errors = 0

    shard_indices = list(range(TOTAL_SHARDS))
    print(f"[{vcworld_name}] Scanning {TOTAL_SHARDS} shards with {workers} workers...")

    def process_shard(shard_idx: int) -> Tuple[int, Optional[object], Optional[object]]:
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

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_shard, i): i for i in shard_indices}
        done = 0
        for fut in as_completed(futures):
            done += 1
            shard_idx, X_chunk, meta_chunk = fut.result()
            if X_chunk is not None:
                chunks_X.append(X_chunk)
                chunks_meta.append(meta_chunk)
                total_cells += X_chunk.shape[0]
            elif X_chunk is None and meta_chunk is None and futures[fut] is not None:
                # None,None means either empty shard or error — errors already printed
                pass
            if done % 200 == 0 or done == TOTAL_SHARDS:
                print(f"[{vcworld_name}]   {done}/{TOTAL_SHARDS} shards done, "
                      f"{total_cells} cells collected so far")

    if not chunks_X:
        print(f"[{vcworld_name}] No cells found for {cvcl_id}!")
        return

    print(f"[{vcworld_name}] Stacking {len(chunks_X)} chunks ({total_cells} cells)...")
    X = sp_vstack(chunks_X, format="csr")
    obs = pd.concat(chunks_meta, ignore_index=True)
    var = pd.DataFrame(index=gene_names)
    var.index.name = "gene_name"

    print(f"[{vcworld_name}] Building AnnData ({X.shape[0]} x {X.shape[1]})...")
    adata = ad.AnnData(X=X, obs=obs, var=var)
    adata.write_h5ad(out_path)
    size = out_path.stat().st_size / 1e9
    print(f"[{vcworld_name}] Saved: {out_path} ({size:.2f} GB, {X.shape[0]} cells)")


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
