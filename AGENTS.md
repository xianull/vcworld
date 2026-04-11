# VCWorld Agent Knowledge Index

## Project Overview
**Goal**: Predict cellular response to drug perturbations using LLM-based causal reasoning.
**Pipeline**: `prepare` → `retrieve` → `prompt` → `infer`
**Data**: GeneTAK benchmark — 5 cell lines, 348 drugs, (drug, gene, cell_line) triplets

## Tasks
- **DE**: Binary (Yes/No) — gene differentially expressed?
- **DIR**: Ternary (Increase/Decrease/Uncertain) — direction of change?

## Reasoning Framework (5 steps)
1. Mechanism & Analogue Identification
2. Specificity & Relevance Analysis (cell line mutations)
3. Downstream Signaling Cascade (drug → kinases → TFs → gene)
4. Causal Bridge & Evidence Synthesis
5. Final Deterministic Prediction

## Architecture
```
utils/ (common, template, parsing, logging)
  ↓
tools/ (data_tools, knowledge_tools, validation_tools)
  ↓
stages/ (prepare, retrieve, prompt, infer, infer_api)
  ↓
agent_workflow.py (7-step autonomous loop)
```

## Available Tools
| Module | Key Functions |
|--------|---------------|
| `utils/common.py` | `parse_prompt_block`, `load_similarity_json`, `post_json`, `resolve_api_key` |
| `utils/parsing.py` | `extract_prediction(text, task)` → `{prediction, confidence, reasoning_steps, is_valid}` |
| `utils/logging.py` | `StageLogger(stage).start/progress/complete/error` |
| `schemas.py` | `PrepareOutput`, `RetrieveOutput`, `PromptOutput`, `InferOutput` |
| `tools/data_tools.py` | `validate_gene_names`, `validate_drug_names`, `check_statistical_validity` |
| `tools/knowledge_tools.py` | `query_pathway(drug, gene)`, `query_ppi(gene)`, `get_gene_function`, `get_drug_mechanism` |
| `tools/validation_tools.py` | `check_causal_chain_completeness`, `cross_validate_prediction` |

## Agent Workflow (`agent_workflow.py`)
`VCWorldAgentWorkflow(task, pert, gene, cell_line, ...).run()` executes:
1. Validate inputs (drug/gene in desc files)
2. Retrieve evidence pairs (similarity-based)
3. Query biological knowledge (KEGG + STRING)
4. Generate prompt (with knowledge context injected)
5. Run LLM inference (API)
6. Validate output (causal chain + cross-validation)
7. Retry if invalid (up to max_retries)

## Docs
- [Pipeline commands & parameters](docs/pipeline.md)
- [Data locations & configuration](docs/data.md)
- [Troubleshooting](docs/troubleshooting.md)

## References
- GeneTAK benchmark | KEGG | STRING | CCLE/DepMap
