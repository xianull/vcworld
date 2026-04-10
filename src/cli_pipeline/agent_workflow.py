#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VCWorld Agent Workflow — Harness Engineering Layer 3.

Implements a self-iterating, tool-augmented agent workflow that:
1. Validates inputs
2. Retrieves evidence
3. Queries biological knowledge
4. Generates a prompt
5. Runs LLM inference
6. Validates the output
7. Iterates if validation fails (up to max_retries)
"""

from __future__ import annotations

import json
import os
import random
import tempfile
from typing import Any, Dict, List, Optional

from .utils.logging import StageLogger
from .utils.parsing import extract_prediction, validate_prediction
from .utils.common import load_json, load_similarity_json
from .tools.data_tools import validate_gene_names, validate_drug_names
from .tools.knowledge_tools import query_pathway, query_ppi, get_gene_function, get_drug_mechanism
from .tools.validation_tools import check_causal_chain_completeness, cross_validate_prediction
from .stages.retrieve import build_retrieval_results
from .stages.prompt import generate_prompts, _default_template_path
from .stages.infer_api import run_inference_api


class VCWorldAgentWorkflow:
    """Agent-driven pipeline for a single (drug, gene, cell_line) prediction.

    Usage::

        workflow = VCWorldAgentWorkflow(
            task="de",
            pert="Drug-X",
            gene="Gene-Y",
            cell_line="C32",
            data_csv="C32_DE.csv",
            drug_desc_json="drug_simp.json",
            gene_desc_json="gene_output.json",
            drug_sim_json="combined_similarity_sorted.json",
            gene_sim_json="results_close_gene.json",
            api_url="https://api.example.com/v1/chat/completions",
            api_model="gpt-4",
            api_key="sk-...",
        )
        result = workflow.run()
        print(result["prediction"])
    """

    def __init__(
        self,
        *,
        task: str,
        pert: str,
        gene: str,
        cell_line: str,
        data_csv: str,
        drug_desc_json: str,
        gene_desc_json: str,
        drug_sim_json: str,
        gene_sim_json: str,
        api_url: str,
        api_model: str,
        api_key: Optional[str] = None,
        template_file: Optional[str] = None,
        budget: int = 10,
        seed: int = 42,
        max_retries: int = 2,
        enable_knowledge_query: bool = True,
    ) -> None:
        self.task = task
        self.pert = pert
        self.gene = gene
        self.cell_line = cell_line
        self.data_csv = data_csv
        self.drug_desc_json = drug_desc_json
        self.gene_desc_json = gene_desc_json
        self.drug_sim_json = drug_sim_json
        self.gene_sim_json = gene_sim_json
        self.api_url = api_url
        self.api_model = api_model
        self.api_key = api_key
        self.template_file = template_file or _default_template_path(task)
        self.budget = budget
        self.seed = seed
        self.max_retries = max_retries
        self.enable_knowledge_query = enable_knowledge_query

        self._log = StageLogger("agent_workflow")
        self._state: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Step 1: Validate inputs
    # ------------------------------------------------------------------

    def step_1_validate_inputs(self) -> Dict[str, Any]:
        self._log.start(pert=self.pert, gene=self.gene, cell_line=self.cell_line, task=self.task)

        drug_desc = load_json(self.drug_desc_json)
        gene_desc = load_json(self.gene_desc_json)

        drug_result = validate_drug_names([self.pert], list(drug_desc.keys()))
        gene_result = validate_gene_names([self.gene], list(gene_desc.keys()))

        issues = []
        if self.pert in drug_result["invalid"]:
            sugg = drug_result["suggestions"].get(self.pert, [])
            issues.append(
                f"Drug '{self.pert}' not in drug_desc. "
                + (f"Suggestions: {sugg}" if sugg else "No suggestions.")
            )
        if self.gene in gene_result["invalid"]:
            sugg = gene_result["suggestions"].get(self.gene, [])
            issues.append(
                f"Gene '{self.gene}' not in gene_desc. "
                + (f"Suggestions: {sugg}" if sugg else "No suggestions.")
            )

        result = {
            "drug_valid": self.pert not in drug_result["invalid"],
            "gene_valid": self.gene not in gene_result["invalid"],
            "issues": issues,
        }
        self._state["validation"] = result
        if issues:
            self._log.warn("Input validation issues", issues=issues)
        return result

    # ------------------------------------------------------------------
    # Step 2: Retrieve evidence
    # ------------------------------------------------------------------

    def step_2_retrieve_evidence(self) -> List[List[str]]:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            retrieval_path = f.name

        try:
            build_retrieval_results(
                data_csv=self.data_csv,
                drug_sim_json=self.drug_sim_json,
                out_json=retrieval_path,
                gene_sim_json=self.gene_sim_json,
                budget=self.budget,
                seed=self.seed,
                case_split="train",
            )
            retrieval = load_json(retrieval_path)
        finally:
            os.unlink(retrieval_path)

        # Find the case matching our pert/gene
        pairs: List[List[str]] = []
        for case in retrieval:
            tc = case.get("test_case", {})
            if (tc.get("drug", "").strip().lower() == self.pert.strip().lower() and
                    tc.get("gene", "").strip().lower() == self.gene.strip().lower()):
                pairs = case.get("retrieved_pairs", [])
                break

        self._state["evidence_pairs"] = pairs
        self._log.progress(evidence_pairs=len(pairs))
        return pairs

    # ------------------------------------------------------------------
    # Step 3: Query biological knowledge
    # ------------------------------------------------------------------

    def step_3_query_knowledge(self) -> Dict[str, Any]:
        if not self.enable_knowledge_query:
            return {}

        pathway_data = query_pathway(self.pert, self.gene)
        ppi_data = query_ppi(self.gene, top_k=5)
        gene_func = get_gene_function(self.gene)
        drug_mech = get_drug_mechanism(self.pert)

        knowledge = {
            "pathway": pathway_data,
            "ppi": ppi_data,
            "gene_function": gene_func,
            "drug_mechanism": drug_mech,
        }
        self._state["knowledge"] = knowledge
        self._log.progress(
            pathway_source=pathway_data.get("source"),
            ppi_source=ppi_data.get("source"),
            shared_pathways=len(pathway_data.get("shared_pathways", [])),
        )
        return knowledge

    # ------------------------------------------------------------------
    # Step 4: Generate prompt
    # ------------------------------------------------------------------

    def step_4_generate_prompt(self, attempt: int = 0) -> str:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as rf:
            retrieval_path = rf.name
            pairs = self._state.get("evidence_pairs", [])
            json.dump([{
                "test_case": {"drug": self.pert, "gene": self.gene},
                "retrieved_pairs": pairs,
            }], rf)

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as pf:
            prompt_path = pf.name

        try:
            generate_prompts(
                task=self.task,
                retrieval_json=retrieval_path,
                drug_desc_json=self.drug_desc_json,
                gene_desc_json=self.gene_desc_json,
                template_file=self.template_file,
                output_file=prompt_path,
                seed=self.seed + attempt,
            )
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_text = f.read()
        finally:
            os.unlink(retrieval_path)
            os.unlink(prompt_path)

        self._state["prompt_text"] = prompt_text
        return prompt_text

    # ------------------------------------------------------------------
    # Step 5: Run inference
    # ------------------------------------------------------------------

    def step_5_infer(self) -> str:
        prompt_text = self._state.get("prompt_text", "")
        if not prompt_text:
            raise RuntimeError("No prompt text available. Run step_4 first.")

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as pf:
            pf.write(prompt_text)
            prompt_path = pf.name

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as of:
            output_path = of.name

        try:
            run_inference_api(
                api_url=self.api_url,
                api_model=self.api_model,
                api_key=self.api_key,
                prompts_file=prompt_path,
                output_file=output_path,
            )
            with open(output_path, "r", encoding="utf-8") as f:
                raw_output = f.read()
        finally:
            os.unlink(prompt_path)
            os.unlink(output_path)

        self._state["raw_output"] = raw_output
        return raw_output

    # ------------------------------------------------------------------
    # Step 6: Validate output
    # ------------------------------------------------------------------

    def step_6_validate_output(self) -> Dict[str, Any]:
        raw_output = self._state.get("raw_output", "")
        parsed = extract_prediction(raw_output, self.task)

        chain_check = check_causal_chain_completeness(
            drug=self.pert,
            gene=self.gene,
            reasoning_steps=parsed.get("reasoning_steps", []),
        )

        cross_check = cross_validate_prediction(
            drug=self.pert,
            gene=self.gene,
            cell_line=self.cell_line,
            prediction=parsed.get("prediction") or "Uncertain",
            evidence_pairs=self._state.get("evidence_pairs", []),
            task=self.task,
        )

        # Adjust confidence
        base_conf = parsed.get("confidence", 0.5)
        adj = cross_check.get("confidence_adjustment", 0.0)
        final_conf = max(0.0, min(1.0, base_conf + adj))

        validation = {
            "prediction": parsed.get("prediction"),
            "confidence": final_conf,
            "is_valid": parsed.get("is_valid", False),
            "reasoning_steps": parsed.get("reasoning_steps", []),
            "causal_chain": chain_check,
            "cross_validation": cross_check,
        }
        self._state["validation_result"] = validation

        self._log.progress(
            prediction=validation["prediction"],
            is_valid=validation["is_valid"],
            chain_score=chain_check["score"],
        )
        return validation

    # ------------------------------------------------------------------
    # Step 7: Decide whether to retry
    # ------------------------------------------------------------------

    def step_7_should_retry(self, validation: Dict[str, Any], attempt: int) -> bool:
        if attempt >= self.max_retries:
            return False
        if not validation.get("is_valid"):
            self._log.warn("Prediction invalid, retrying", attempt=attempt + 1)
            return True
        if validation.get("prediction") == "Uncertain" and attempt < 1:
            self._log.warn("Uncertain prediction, retrying with different seed", attempt=attempt + 1)
            return True
        return False

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """Execute the full agent workflow with optional retry loop."""
        # Step 1: validate
        input_check = self.step_1_validate_inputs()

        # Step 2: retrieve evidence
        self.step_2_retrieve_evidence()

        # Step 3: query knowledge (best-effort)
        knowledge = self.step_3_query_knowledge()

        # Steps 4–7: generate → infer → validate → retry loop
        validation: Dict[str, Any] = {}
        for attempt in range(self.max_retries + 1):
            self.step_4_generate_prompt(attempt=attempt)
            self.step_5_infer()
            validation = self.step_6_validate_output()

            if not self.step_7_should_retry(validation, attempt):
                break

        self._log.complete(
            prediction=validation.get("prediction"),
            confidence=validation.get("confidence"),
            is_valid=validation.get("is_valid"),
        )

        return {
            "task": self.task,
            "pert": self.pert,
            "gene": self.gene,
            "cell_line": self.cell_line,
            "prediction": validation.get("prediction"),
            "confidence": validation.get("confidence"),
            "is_valid": validation.get("is_valid"),
            "reasoning_steps": validation.get("reasoning_steps", []),
            "causal_chain_score": validation.get("causal_chain", {}).get("score"),
            "evidence_pairs": len(self._state.get("evidence_pairs", [])),
            "knowledge": knowledge,
            "input_issues": input_check.get("issues", []),
        }
