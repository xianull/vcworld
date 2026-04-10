#!/usr/bin/env bash
# =============================================================================
# VCWorld End-to-End Pipeline Runner
# =============================================================================
# Usage:
#   bash run_pipeline.sh [OPTIONS]
#
# Options:
#   --cell-line   Cell line name (default: C32)
#   --task        de | dir | both (default: both)
#   --mode        local | api (default: api)
#   --model       HF model path or API model name (default: gpt-4o-mini)
#   --api-url     API endpoint URL
#   --api-key     API key (or set LLM_DRUG_API_KEY env var)
#   --data-dir    Directory containing h5ad and JSON data files
#   --out-dir     Output directory (default: ./output)
#   --max-cases   Limit number of test cases (optional, for quick testing)
#   --skip-prepare  Skip prepare stage (if CSV already exists)
#   --help        Show this help
#
# Example (API mode):
#   bash run_pipeline.sh \
#     --cell-line C32 \
#     --task both \
#     --mode api \
#     --model gpt-4o-mini \
#     --api-url https://api.openai.com/v1/chat/completions \
#     --api-key sk-... \
#     --data-dir ./data
#
# Example (local HF model):
#   bash run_pipeline.sh \
#     --cell-line C32 \
#     --task both \
#     --mode local \
#     --model meta-llama/Llama-3.1-8B-Instruct \
#     --data-dir ./data
#
# Data files required in --data-dir:
#   {cell_line}_cells.h5ad          (from Tahoe-100M / Zenodo)
#   combined_similarity_sorted.json  (drug similarity, from Zenodo)
#   results_close_gene.json          (gene similarity, from Zenodo)
#   drug_simp.json                   (drug descriptions, from Zenodo)
#   gene_output.json                 (gene descriptions, from Zenodo)
#
# Zenodo data: https://doi.org/10.5281/zenodo.18513982
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
CELL_LINE="C32"
TASK="both"
MODE="api"
MODEL="gpt-4o-mini"
API_URL="${API_URL:-}"
API_KEY="${LLM_DRUG_API_KEY:-${API_KEY:-}}"
DATA_DIR="./data"
OUT_DIR="./output"
MAX_CASES=""
SKIP_PREPARE=false
BUDGET=10
SEED=42
BATCH_SIZE=4
MAX_NEW_TOKENS=1024
DTYPE="bfloat16"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cell-line)   CELL_LINE="$2";   shift 2 ;;
    --task)        TASK="$2";        shift 2 ;;
    --mode)        MODE="$2";        shift 2 ;;
    --model)       MODEL="$2";       shift 2 ;;
    --api-url)     API_URL="$2";     shift 2 ;;
    --api-key)     API_KEY="$2";     shift 2 ;;
    --data-dir)    DATA_DIR="$2";    shift 2 ;;
    --out-dir)     OUT_DIR="$2";     shift 2 ;;
    --max-cases)   MAX_CASES="$2";   shift 2 ;;
    --skip-prepare) SKIP_PREPARE=true; shift ;;
    --budget)      BUDGET="$2";      shift 2 ;;
    --seed)        SEED="$2";        shift 2 ;;
    --batch-size)  BATCH_SIZE="$2";  shift 2 ;;
    --max-new-tokens) MAX_NEW_TOKENS="$2"; shift 2 ;;
    --help|-h)
      head -50 "$0" | grep "^#" | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if [[ "$MODE" == "api" ]]; then
  if [[ -z "$API_URL" ]]; then
    echo "ERROR: --api-url is required for API mode"
    echo "       Or set API_URL environment variable"
    exit 1
  fi
  if [[ -z "$API_KEY" ]]; then
    echo "WARNING: No API key provided. Set --api-key or LLM_DRUG_API_KEY env var."
  fi
fi

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
H5AD="${DATA_DIR}/${CELL_LINE}_cells.h5ad"
DRUG_SIM="${DATA_DIR}/combined_similarity_sorted.json"
GENE_SIM="${DATA_DIR}/results_close_gene.json"
DRUG_DESC="${DATA_DIR}/drug_simp.json"
GENE_DESC="${DATA_DIR}/gene_output.json"

# Determine which tasks to run
if [[ "$TASK" == "both" ]]; then
  TASKS=("de" "dir")
else
  TASKS=("$TASK")
fi

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
log() { echo "[$(date '+%H:%M:%S')] $*"; }
log_section() { echo; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; echo "  $*"; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; }

check_file() {
  if [[ ! -f "$1" ]]; then
    echo "ERROR: Required file not found: $1"
    echo "       Download from: https://doi.org/10.5281/zenodo.18513982"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
log_section "Pre-flight checks"

mkdir -p "$OUT_DIR"

# Check data files
check_file "$DRUG_SIM"
check_file "$GENE_SIM"
check_file "$DRUG_DESC"
check_file "$GENE_DESC"

if [[ "$SKIP_PREPARE" == false ]]; then
  check_file "$H5AD"
fi

# Check Python environment
python -c "import src.cli_pipeline.cli" 2>/dev/null || {
  echo "ERROR: Cannot import src.cli_pipeline.cli"
  echo "       Run from project root: cd VCWorld && bash run_pipeline.sh ..."
  exit 1
}

log "Cell line : $CELL_LINE"
log "Task(s)   : ${TASKS[*]}"
log "Mode      : $MODE"
log "Model     : $MODEL"
log "Data dir  : $DATA_DIR"
log "Output dir: $OUT_DIR"

# ---------------------------------------------------------------------------
# Run pipeline for each task
# ---------------------------------------------------------------------------
for TASK_NAME in "${TASKS[@]}"; do
  log_section "Task: ${TASK_NAME^^}"

  CSV_PATH="${OUT_DIR}/${CELL_LINE}_${TASK_NAME^^}.csv"
  RETRIEVAL_PATH="${OUT_DIR}/${CELL_LINE}_${TASK_NAME^^}_retrieval.json"
  PROMPTS_PATH="${OUT_DIR}/${CELL_LINE}_${TASK_NAME^^}_prompts.txt"
  PREDICTIONS_PATH="${OUT_DIR}/${CELL_LINE}_${TASK_NAME^^}_predictions.txt"

  # ── Stage 1: Prepare ──────────────────────────────────────────────────────
  if [[ "$SKIP_PREPARE" == false ]]; then
    log "[1/4] Prepare: extracting DE/DIR labels from h5ad..."
    python -m src.cli_pipeline.cli "$TASK_NAME" prepare \
      --h5ad "$H5AD" \
      --out-dir "$OUT_DIR" \
      --cell-line "$CELL_LINE" \
      --seed "$SEED"
    log "      → Saved: $CSV_PATH"
  else
    log "[1/4] Prepare: SKIPPED (using existing $CSV_PATH)"
    check_file "$CSV_PATH"
  fi

  # ── Stage 2: Retrieve ─────────────────────────────────────────────────────
  log "[2/4] Retrieve: building evidence pairs..."
  RETRIEVE_ARGS=(
    --data-csv "$CSV_PATH"
    --drug-sim "$DRUG_SIM"
    --gene-sim "$GENE_SIM"
    --out "$RETRIEVAL_PATH"
    --budget "$BUDGET"
    --seed "$SEED"
    --case-split test
  )
  if [[ -n "$MAX_CASES" ]]; then
    RETRIEVE_ARGS+=(--max-cases "$MAX_CASES")
  fi
  python -m src.cli_pipeline.cli "$TASK_NAME" retrieve "${RETRIEVE_ARGS[@]}"
  log "      → Saved: $RETRIEVAL_PATH"

  # ── Stage 3: Prompt ───────────────────────────────────────────────────────
  log "[3/4] Prompt: generating prompts..."
  PROMPT_ARGS=(
    --retrieval "$RETRIEVAL_PATH"
    --drug-desc "$DRUG_DESC"
    --gene-desc "$GENE_DESC"
    --out "$PROMPTS_PATH"
    --seed "$SEED"
  )
  if [[ -n "$MAX_CASES" ]]; then
    PROMPT_ARGS+=(--max-cases "$MAX_CASES")
  fi
  python -m src.cli_pipeline.cli "$TASK_NAME" prompt "${PROMPT_ARGS[@]}"
  log "      → Saved: $PROMPTS_PATH"

  # ── Stage 4: Infer ────────────────────────────────────────────────────────
  log "[4/4] Infer: running LLM inference ($MODE mode)..."
  if [[ "$MODE" == "api" ]]; then
    python -m src.cli_pipeline.cli "$TASK_NAME" infer-api \
      --api-url "$API_URL" \
      --api-model "$MODEL" \
      --api-key "$API_KEY" \
      --prompts "$PROMPTS_PATH" \
      --out "$PREDICTIONS_PATH" \
      --max-new-tokens "$MAX_NEW_TOKENS"
  else
    python -m src.cli_pipeline.cli "$TASK_NAME" infer \
      --model "$MODEL" \
      --prompts "$PROMPTS_PATH" \
      --out "$PREDICTIONS_PATH" \
      --batch-size "$BATCH_SIZE" \
      --max-new-tokens "$MAX_NEW_TOKENS" \
      --dtype "$DTYPE"
  fi
  log "      → Saved: $PREDICTIONS_PATH"

  log "Task ${TASK_NAME^^} complete."
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
log_section "Pipeline Complete"
echo "Output files:"
ls -lh "$OUT_DIR"/*.{csv,json,txt} 2>/dev/null | awk '{print "  "$NF, $5}'
echo
echo "Next steps:"
echo "  1. Parse predictions:  python -c \"from src.cli_pipeline.utils.parsing import extract_prediction; ...\""
echo "  2. Evaluate results:   compare predictions against ground truth labels in CSV"
echo "  3. Single-case query:  python -m src.cli_pipeline.cli single prompt --pert <drug> --gene <gene> ..."
