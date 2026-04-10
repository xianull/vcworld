#!/usr/bin/env bash
# =============================================================================
# VCWorld Data Download Script
# =============================================================================
# Downloads all required data files for VCWorld pipeline:
#   1. VCWorld knowledge graph data (Zenodo: 10.5281/zenodo.18513982)
#      - drug_simp.json          (drug descriptions, LLM-generated from KG)
#      - gene_output.json        (gene function descriptions)
#      - combined_similarity_sorted.json  (hybrid drug similarity, α=0.7)
#      - results_close_gene.json (gene similarity via KG path topology)
#   2. Tahoe-100M h5ad files for 5 cell lines (HuggingFace: tahoebio/Tahoe-100M)
#      - C32_cells.h5ad
#      - HOP62_cells.h5ad
#      - HepG2C3A_cells.h5ad
#      - Hs766T_cells.h5ad
#      - PANC1_cells.h5ad
#
# Usage:
#   bash download_data.sh [--data-dir ./data] [--cell-lines C32,HOP62] [--skip-h5ad]
#
# Requirements:
#   pip install huggingface_hub datasets
# =============================================================================

set -euo pipefail

DATA_DIR="./data"
CELL_LINES="C32,HOP62,HepG2C3A,Hs766T,PANC1"
SKIP_H5AD=false
ZENODO_DOI="10.5281/zenodo.18513982"
ZENODO_RECORD_ID="18513982"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-dir)    DATA_DIR="$2";    shift 2 ;;
    --cell-lines)  CELL_LINES="$2";  shift 2 ;;
    --skip-h5ad)   SKIP_H5AD=true;   shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

log() { echo "[$(date '+%H:%M:%S')] $*"; }
log_section() { echo; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; echo "  $*"; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; }

mkdir -p "$DATA_DIR"

# =============================================================================
# Part 1: Download VCWorld KG data from Zenodo
# =============================================================================
log_section "Part 1: VCWorld Knowledge Graph Data (Zenodo)"

ZENODO_TARBALL="${DATA_DIR}/VCWorld.tar.gz"

if [[ ! -f "$ZENODO_TARBALL" ]]; then
  log "Downloading VCWorld.tar.gz from Zenodo..."
  # Try zenodo API first, then direct URL
  ZENODO_URL="https://zenodo.org/records/${ZENODO_RECORD_ID}/files/VCWorld.tar.gz"
  if command -v wget &>/dev/null; then
    wget -O "$ZENODO_TARBALL" "$ZENODO_URL" || {
      log "wget failed, trying curl..."
      curl -L -o "$ZENODO_TARBALL" "$ZENODO_URL"
    }
  else
    curl -L -o "$ZENODO_TARBALL" "$ZENODO_URL"
  fi
  log "Downloaded: $ZENODO_TARBALL"
else
  log "Already exists: $ZENODO_TARBALL (skipping download)"
fi

log "Extracting VCWorld.tar.gz..."
tar -xzf "$ZENODO_TARBALL" -C "$DATA_DIR" --strip-components=1 2>/dev/null || \
  tar -xzf "$ZENODO_TARBALL" -C "$DATA_DIR"

# Verify required KG files
KG_FILES=("drug_simp.json" "gene_output.json" "combined_similarity_sorted.json" "results_close_gene.json")
log "Verifying KG files..."
for f in "${KG_FILES[@]}"; do
  # Search recursively in case of nested dirs
  found=$(find "$DATA_DIR" -name "$f" 2>/dev/null | head -1)
  if [[ -n "$found" ]]; then
    # Move to data dir root if nested
    if [[ "$found" != "${DATA_DIR}/${f}" ]]; then
      mv "$found" "${DATA_DIR}/${f}"
    fi
    SIZE=$(du -sh "${DATA_DIR}/${f}" | cut -f1)
    log "  ✓ $f ($SIZE)"
  else
    log "  ✗ $f NOT FOUND in archive — check Zenodo record manually"
  fi
done

# =============================================================================
# Part 2: Download Tahoe-100M h5ad files
# =============================================================================
if [[ "$SKIP_H5AD" == false ]]; then
  log_section "Part 2: Tahoe-100M Cell Line h5ad Files (HuggingFace)"
  log "Note: Full Tahoe-100M is multi-TB. We download only the 5 VCWorld cell lines."
  log "      Each h5ad is ~1-5 GB. Requires: pip install huggingface_hub"

  python3 - <<'PYEOF'
import os, sys

data_dir = os.environ.get("DATA_DIR", "./data")

# Cell line name mapping: VCWorld name -> Tahoe-100M file pattern
CELL_LINE_MAP = {
    "C32":       "C32",
    "HOP62":     "HOP62",
    "HepG2C3A":  "HepG2",   # HepG2/C3A stored as HepG2 in Tahoe
    "Hs766T":    "Hs766T",
    "PANC1":     "PANC1",
}

cell_lines_env = os.environ.get("CELL_LINES", "C32,HOP62,HepG2C3A,Hs766T,PANC1")
requested = [c.strip() for c in cell_lines_env.split(",")]

try:
    from huggingface_hub import hf_hub_download, list_repo_files
    print("[HF] Listing available files in tahoebio/Tahoe-100M...")

    # List all files to find exact h5ad filenames
    try:
        all_files = list(list_repo_files("tahoebio/Tahoe-100M", repo_type="dataset"))
        h5ad_files = [f for f in all_files if f.endswith(".h5ad")]
        print(f"[HF] Found {len(h5ad_files)} h5ad files in repo")
    except Exception as e:
        print(f"[HF] Could not list files: {e}")
        h5ad_files = []

    for vcworld_name in requested:
        out_path = os.path.join(data_dir, f"{vcworld_name}_cells.h5ad")
        if os.path.exists(out_path):
            size = os.path.getsize(out_path) / 1e9
            print(f"[HF] Already exists: {vcworld_name}_cells.h5ad ({size:.1f} GB)")
            continue

        # Find matching file in repo
        tahoe_key = CELL_LINE_MAP.get(vcworld_name, vcworld_name)
        matches = [f for f in h5ad_files if tahoe_key.lower() in f.lower()]

        if not matches:
            print(f"[HF] WARNING: No h5ad found for {vcworld_name} (key={tahoe_key})")
            print(f"[HF]          Available: {h5ad_files[:5]}")
            continue

        src_file = matches[0]
        print(f"[HF] Downloading {src_file} -> {vcworld_name}_cells.h5ad ...")
        try:
            local = hf_hub_download(
                repo_id="tahoebio/Tahoe-100M",
                filename=src_file,
                repo_type="dataset",
                local_dir=data_dir,
            )
            os.rename(local, out_path)
            size = os.path.getsize(out_path) / 1e9
            print(f"[HF] ✓ {vcworld_name}_cells.h5ad ({size:.1f} GB)")
        except Exception as e:
            print(f"[HF] ✗ Failed to download {vcworld_name}: {e}")

except ImportError:
    print("[HF] huggingface_hub not installed.")
    print("[HF] Run: pip install huggingface_hub")
    print("[HF] Then re-run this script, or download manually:")
    for name in requested:
        print(f"[HF]   python -c \"from huggingface_hub import hf_hub_download; "
              f"hf_hub_download('tahoebio/Tahoe-100M', '{name}_cells.h5ad', repo_type='dataset', local_dir='./data')\"")
PYEOF

fi  # end SKIP_H5AD

# =============================================================================
# Summary
# =============================================================================
log_section "Download Summary"
echo "Files in $DATA_DIR:"
ls -lh "$DATA_DIR"/*.{json,h5ad,gz} 2>/dev/null | awk '{printf "  %-45s %s\n", $NF, $5}' || true

echo
echo "Next step — run the pipeline:"
echo "  bash run_pipeline.sh \\"
echo "    --cell-line C32 \\"
echo "    --task both \\"
echo "    --mode api \\"
echo "    --model gpt-4o-mini \\"
echo "    --api-url https://api.openai.com/v1/chat/completions \\"
echo "    --api-key \$OPENAI_API_KEY \\"
echo "    --data-dir $DATA_DIR"
