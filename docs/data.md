# VCWorld Data & Configuration

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

## Configuration

### Environment Variables
- `LLM_DRUG_API_KEY` — API key for inference API (checked before `API_KEY`)
- `API_KEY` — Fallback API key

### CLI Arguments
All stages support:
- `--seed` — Random seed (default varies by stage)
- `--max-cases` — Limit number of cases (optional)
