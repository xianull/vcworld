# VCWorld Pipeline Reference

## Stage 1: Prepare

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

---

## Stage 2: Retrieve

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

---

## Stage 3: Prompt

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

---

## Stage 4: Infer (Local)

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

---

## Stage 5: Infer-API

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

---

## Stage 6: Single-Case Prompt

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

## Prompt Format

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

## Evidence Pair Formatting

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
