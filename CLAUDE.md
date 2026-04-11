# VCWorld Project — Development Workflow

## Environment Setup

- **Local machine**: Code writing, editing, version control (macOS)
- **Remote server**: Code execution, data download, pipeline runs
- **SSH**: `ssh jcw@192.168.112.108 -p 3313`

### Server Specs
- Hostname: `api-node`
- CPU: 96 cores (x86_64)
- RAM: 503 GB
- Storage: `/gpfs/flash` 307 TB (78% used)
- Python: 3.8.10 (via `~/anaconda3`)
- GPU: none on this node (API inference mode)
- Home dir contents: `anaconda3`, `projects`, `tools`, `scripts`, `mytmp`

## Workflow Rules

1. All code is written **locally** on this machine
2. Code is synced to the server via `rsync` or `git push` + `git pull`
3. All execution (pipeline runs, model inference, data download) happens **on the server**
4. Claude can control the server via SSH Bash commands

## Sync Commands

```bash
# Sync local code to server (run from project root)
rsync -avz --exclude='*.pyc' --exclude='__pycache__' --exclude='.git' \
  /Users/xianull/Documents/Q2_projects/VCWorld/ \
  jcw@192.168.112.108:/path/to/VCWorld/ -p 3313

# Or via git
git push origin main
# then on server: git pull origin main
```

## Server Execution Pattern

Claude will use this pattern to run commands on the server:

```bash
ssh jcw@192.168.112.108 -p 3313 "cd /path/to/VCWorld && <command>"
```

## Project Structure (Local)

```
VCWorld/
├── src/cli_pipeline/          # Main pipeline code
│   ├── stages/                # prepare, retrieve, prompt, infer
│   ├── utils/                 # common, template, parsing, logging
│   ├── tools/                 # data_tools, knowledge_tools, validation_tools
│   ├── schemas.py             # TypedDict output types
│   └── agent_workflow.py      # Agent orchestration layer
├── support/                   # Prompt templates (DE/DIR)
├── AGENTS.md                  # Agent knowledge index
├── run_pipeline.sh            # One-click pipeline runner
└── download_data.sh           # Data download script
```

## Data Location (Server)

All data lives at: `~/data/VCWorld/` (`/gpfs/flash/home/jcw/data/VCWorld/`)

### KG Data (Downloaded ✓)
- `~/data/VCWorld/drug_simp.json`              (132K — drug descriptions)
- `~/data/VCWorld/gene_output.json`            (912K — gene descriptions)
- `~/data/VCWorld/combined_similarity_sorted.json` (232K — drug similarity)
- `~/data/VCWorld/results_close_gene.json`     (205M — gene similarity)
- `~/data/VCWorld/VCWorld/KG/`                 (full KG: graph.json, edges.json, nodes.json)

Source: Zenodo https://doi.org/10.5281/zenodo.18513982 (VCWorld.tar.gz, 189MB)

### h5ad Data (Pending)
Tahoe-100M is stored as 3388 Parquet shards on HuggingFace (tahoebio/Tahoe-100M).
Use `scripts/tahoe_to_h5ad.py` to download and convert:

```bash
cd ~/projects/vcworld
HF_ENDPOINT=https://hf-mirror.com ~/anaconda3/bin/python3 scripts/tahoe_to_h5ad.py \
  --cell-lines C32 HOP62 HepG2C3A Hs766T PANC1 \
  --out-dir ~/data/VCWorld
```

Expected output: `{cell_line}_cells.h5ad` per cell line (~1-5 GB each)
