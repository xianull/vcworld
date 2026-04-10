#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run API-based inference on prompts file."""

from __future__ import annotations

import json
import time
from typing import List, Optional

from ..utils.common import PROMPT_SEPARATOR, parse_prompt_block, resolve_api_key, post_json


def run_inference_api(*, api_url: str, api_model: str, prompts_file: str, output_file: str,
                      api_key: Optional[str] = None, max_new_tokens: int = 512,
                      temperature: float = 0.6, top_p: float = 0.9,
                      timeout: int = 60, sleep_secs: float = 0.0) -> None:
    key = resolve_api_key(api_key)
    if not key:
        raise RuntimeError("API key not provided. Set --api-key, LLM_DRUG_API_KEY, or API_KEY in infer_api.py")

    with open(prompts_file, "r", encoding="utf-8") as f:
        full_content = f.read()
    prompt_blocks = [b.strip() for b in full_content.split(PROMPT_SEPARATOR) if b.strip()]

    all_messages: List[list] = []
    prompt_metadata = []
    for block in prompt_blocks:
        system_prompt, user_input, header, error = parse_prompt_block(block)
        if error:
            prompt_metadata.append({"header": header, "is_error": True, "error_message": error})
            continue
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        all_messages.append(messages)
        prompt_metadata.append({"header": header, "is_error": False})

    if not all_messages:
        print("No valid prompts to run")
        return

    all_generated: List[str] = []
    for idx, messages in enumerate(all_messages, start=1):
        payload = {
            "model": api_model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_new_tokens,
        }
        resp = post_json(api_url, payload, key, timeout)
        try:
            content = resp["choices"][0]["message"]["content"]
        except Exception:
            content = json.dumps(resp, ensure_ascii=False)
        all_generated.append(content)
        print(f"API prompt {idx}/{len(all_messages)} done")
        if sleep_secs > 0:
            time.sleep(sleep_secs)

    all_results = []
    output_idx = 0
    for meta in prompt_metadata:
        header = meta["header"]
        if meta["is_error"]:
            formatted = (
                f"--- Query for {header} ---\n"
                f"ERROR during parsing: {meta['error_message']}\n"
                f"--- End of Query for {header} ---\n\n"
                f"{PROMPT_SEPARATOR}\n\n"
            )
        else:
            if output_idx < len(all_generated):
                response = all_generated[output_idx]
                formatted = (
                    f"--- Query for {header} ---\n"
                    f"{response.strip()}\n"
                    f"--- End of Query for {header} ---\n\n"
                    f"{PROMPT_SEPARATOR}\n\n"
                )
                output_idx += 1
            else:
                formatted = (
                    f"--- Query for {header} ---\n"
                    "ERROR: No output generated for this prompt.\n"
                    f"--- End of Query for {header} ---\n\n"
                    f"{PROMPT_SEPARATOR}\n\n"
                )
        all_results.append(formatted)

    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(all_results)

    print(f"Saved outputs: {output_file}")
