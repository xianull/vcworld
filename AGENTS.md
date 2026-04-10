# VCWorld Agent Knowledge Index

## Project Overview

**Goal**: Predict cellular response to drug perturbations using LLM-based causal reasoning.

**Data**: GeneTAK benchmark
- 5 cell lines: C32, PANC-1, HepG2/C3A, HOP-62, Hs766T
- 348 drugs
- Triplets: (drug, gene, cell_line)

**Pipeline**: `prepare` → `retrieve` → `prompt` → `infer`

---

## Key Concepts

### Tasks

- **DE (Differential Expression)**: Binary classification
  - Output: `Yes` (gene is differentially expressed) or `No`
  - Choices: `["A) Perturbation of this drug does not impact the gene of interest.", "B) Perturbation of this drug results in differential expression of the gene of interest."]`

- **DIR (Directional Change)**: Ternary classification
  - Output: `Increase` (expression goes up), `Decrease` (goes down), or `Uncertain`
  - Choices: `["A) Perturbation of this drug results in a decrease in expression of the gene of interest.", "B) Perturbation of this drug results in an increase in expression of the gene of interest."]`

### Reasoning Framework

LLM performs 5-step causal reasoning:

1. **Mechanism & Analogue Identification**: Find drugs in evidence set with same MoA or target pathway nodes
2. **Specificity & Relevance Analysis**: Analyze drug-gene-cell triad; consider cell line mutations (e.g., KRAS G12D, TP53 status)
3. **Downstream Signaling Cascade**: Trace pathway from drug target → kinases → TFs → gene
4. **Causal Bridge & Evidence Synthesis**: Connect drug effect to gene regulation; cite analogue cases
5. **Final Deterministic Prediction**: Output Yes/No/Increase/Decrease/Uncertain

### Evidence Pairs

- Retrieved from training data using drug/gene similarity
- Budget: 10 pairs per test case (configurable)
- Format: `[[drug1, gene1], [drug2, gene2], ...]`
- Each pair includes label (0/1 for DE, 0/1 for DIR direction)

---

## Data Locations

### Templates
- `support/DE_template.py` — DE task prompt template with cell line descriptions
- `support/DIR_template.py` — DIR task prompt template

### Cell Line Descriptions
Defined in templates; include:
- Tissue origin
- Hallmark mutations (KRAS, TP53, CDKN2A, etc.)
- Doubling time
- Microsatellite status (MSS)
- Typical use cases

### Similarity Data
- `drug_sim.json` — Drug similarity neighbors (format: `{drug: [similar_drugs]}`)
- `gene_sim.json` — Gene similarity neighbors (format: `{gene: [similar_genes]}`)

### CSV Datasets
- `{cell_line}_DE.csv` — Columns: `pert, gene, label, split`
- `{cell_line}_DIR.csv` — Columns: `pert, gene, label, split`

---

## Pipeline Stages

### 1. Prepare
**Input**: `.h5ad` file (AnnData object)
**Output**: DE and DIR CSV files

```bash
python cli.py de prepare \
  --h5ad data.h5ad \
  --out-dir output/ \
  --cell-line C32 \
  --fdr 0.05 --lfc 0.25
```

**Key Parameters**:
- `--fdr`: FDR threshold for DEGs (default 0.05)
- `--lfc`: Log-fold-change threshold (default 0.25)
- `--train-fraction`: Train/test split (default 0.3)

### 2. Retrieve
**Input**: DE/DIR CSV, drug/gene similarity JSONs
**Output**: Retrieval JSON with evidence pairs

```bash
python cli.py de retrieve \
  --data-csv C32_DE.csv \
  --drug-sim drug_sim.json \
  --gene-sim gene_sim.json \
  --out retrieval.json \
  --budget 10
```

**Key Parameters**:
- `--budget`: Max pairs per case (default 10)
- `--case-split`: "train" or "test" (default "test")
- `--max-cases`: Limit number of cases (optional)

### 3. Prompt
**Input**: Retrieval JSON, drug/gene descriptions, template
**Output**: Prompt text file

```bash
python cli.py de prompt \
  --retrieval retrieval.json \
  --drug-desc drug_descriptions.json \
  --gene-desc gene_descriptions.json \
  --out prompts.txt
```

**Key Parameters**:
- `--template`: Custom template file (optional; defaults to `support/DE_template.py`)
- `--cell-line-idx`: Force specific cell line (optional; random if not set)
- `--max-cases`: Limit prompts (optional)

### 4. Infer (Local)
**Input**: Prompt text file, HF model name
**Output**: Inference results text file

```bash
python cli.py de infer \
  --model meta-llama/Llama-2-7b-hf \
  --prompts prompts.txt \
  --out results.txt \
  --batch-size 4 \
  --dtype bfloat16
```

### 5. Infer-API
**Input**: Prompt text file, API endpoint
**Output**: Inference results text file

```bash
python cli.py de infer-api \
  --api-url https://api.example.com/v1/chat/completions \
  --api-model gpt-4 \
  --prompts prompts.txt \
  --out results.txt \
  --api-key $API_KEY
```

### 6. Single-Case Prompt
**Input**: Single drug/gene/cell-line, retrieval data
**Output**: Single prompt for out-of-dataset sample

```bash
python cli.py single prompt \
  --pert "Drug-X" \
  --gene "Gene-Y" \
  --cell-line "C32 cells" \
  --mode de \
  --data-csv C32_DE.csv \
  --drug-desc drug_descriptions.json \
  --gene-desc gene_descriptions.json \
  --drug-sim drug_sim.json \
  --gene-sim gene_sim.json \
  --out single_prompt.txt
```

---

## Available Tools (Harness Engineering)

### Common Utilities (`utils/common.py`)
- `parse_prompt_block(block_text)` — Extract system prompt, user input, header from prompt block
- `load_similarity_json(path)` — Load and normalize similarity JSON (handles multiple formats)
- `resolve_api_key(cli_key)` — Resolve API key from CLI > env > fallback
- `post_json(url, payload, api_key, timeout)` — Send JSON POST request with Bearer auth
- `load_json(path)` — Load JSON file
- `load_csv_pairs(path)` — Load CSV with pert/gene/label/split columns

### Template Loading (`utils/template.py`)
- `load_template_vars(template_file)` — Safe template loading (replaces `exec()`)

### Parsing (`utils/parsing.py`)
- `extract_prediction(response_text, task)` — Extract structured prediction from LLM output
  - Returns: `{prediction, confidence, reasoning_steps, is_valid}`
- `validate_prediction(prediction, task)` — Validate prediction format

### Logging (`utils/logging.py`)
- `StageLogger(stage)` — Structured JSON logging
  - Methods: `.start()`, `.progress()`, `.complete()`, `.error()`, `.warn()`

### Type Definitions (`schemas.py`)
- `PrepareOutput` — Output schema for prepare stage
- `RetrieveOutput` — Output schema for retrieve stage
- `PromptOutput` — Output schema for prompt stage
- `InferOutput` — Output schema for infer stage

---

## Common Patterns

### Prompt Format
All prompts follow this structure:

```
=== Prompt N (drug | gene) ===
[Start of Prompt]
<system prompt with 5-step reasoning framework>
[End of Prompt]

[Start of Input]
- Description of molecule drug (drug): <description>
- Description of gene of interest (gene): <description>
- Context: <cell line description>
- Examples: <evidence pairs formatted as Example 1, Example 2, ...>
[End of Input]

[Start of Output]
1)
2)
3)
4)
5)
[End of Output]

================================================================================
```

### Evidence Pair Formatting
```
Example 1:
- Drug: Drug-A
- Gene: Gene-X
- Drug Description: <description>
- Gene Description: <description>
- Result: <choice from choices_de or choices_dir>

Example 2:
...
```

### Prediction Extraction
LLM output is parsed to extract:
- Final prediction (last occurrence of Yes/No/Increase/Decrease/Uncertain)
- Reasoning steps (numbered 1–5)
- Confidence score (heuristic based on hedging language)

---

## Configuration

### Environment Variables
- `LLM_DRUG_API_KEY` — API key for inference API (checked before `API_KEY`)
- `API_KEY` — Fallback API key

### CLI Arguments
All stages support:
- `--seed` — Random seed (default varies by stage)
- `--max-cases` — Limit number of cases (optional)

---

## Troubleshooting

### Import Errors
If you see `ModuleNotFoundError`, ensure:
1. You're running from the project root
2. `src/` is in `PYTHONPATH` or you're using relative imports
3. All `__init__.py` files exist in `src/cli_pipeline/` and `src/cli_pipeline/utils/`

### Template Loading Errors
- Old code used `exec()` which is now replaced with `importlib`
- If template file has syntax errors, `load_template_vars()` will raise `SyntaxError` with traceback
- Ensure template defines: `cell_lines`, `prompt_vcworld_DE` or `prompt_test_de`, `choices_de`

### Prompt Parsing Errors
- Prompts must have `[Start of Prompt]...[End of Prompt]` and `[Start of Input]...[End of Output]` markers
- If markers are missing, the stage logs an error and skips that prompt

### Prediction Extraction
- If LLM output doesn't end with Yes/No/Increase/Decrease/Uncertain, prediction is `None` and `is_valid=False`
- Check `reasoning_steps` to debug multi-step reasoning

---

## Next Steps (Harness Engineering Layers 2–3)

### Layer 2: Bioinformatics Tools
- `tools/data_tools.py` — Gene/drug validation, statistical checks
- `tools/knowledge_tools.py` — Pathway/PPI queries (KEGG, STRING, etc.)
- `tools/validation_tools.py` — Consistency checks, causal chain validation

### Layer 3: Agent Orchestration
- `agent_workflow.py` — Agent-driven pipeline with self-iteration and validation
- Agent can call tools, validate predictions, and retry if needed
- Multi-agent collaboration for cross-validation

---

## References

- **GeneTAK**: Benchmark dataset for drug-gene-cell predictions
- **Cell Lines**: CCLE, DepMap, NCI-60 panel
- **Pathways**: KEGG, Reactome
- **PPI**: STRING database
