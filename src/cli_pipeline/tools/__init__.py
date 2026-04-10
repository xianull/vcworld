"""VCWorld bioinformatics tool registry."""

from .data_tools import validate_gene_names, validate_drug_names, check_statistical_validity
from .knowledge_tools import query_pathway, query_ppi, get_gene_function, get_drug_mechanism
from .validation_tools import check_causal_chain_completeness, cross_validate_prediction

BIOINFORMATICS_TOOLS = {
    "validate_gene_names": validate_gene_names,
    "validate_drug_names": validate_drug_names,
    "check_statistical_validity": check_statistical_validity,
    "query_pathway": query_pathway,
    "query_ppi": query_ppi,
    "get_gene_function": get_gene_function,
    "get_drug_mechanism": get_drug_mechanism,
    "check_causal_chain_completeness": check_causal_chain_completeness,
    "cross_validate_prediction": cross_validate_prediction,
}
