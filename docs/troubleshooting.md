# VCWorld Troubleshooting

## Import Errors

If you see `ModuleNotFoundError`, ensure:
1. You're running from the project root
2. `src/` is in `PYTHONPATH` or you're using relative imports
3. All `__init__.py` files exist in `src/cli_pipeline/` and `src/cli_pipeline/utils/`

## Template Loading Errors

- Old code used `exec()` which is now replaced with `importlib`
- If template file has syntax errors, `load_template_vars()` will raise `SyntaxError` with traceback
- Ensure template defines: `cell_lines`, `prompt_vcworld_DE` or `prompt_test_de`, `choices_de`

## Prompt Parsing Errors

- Prompts must have `[Start of Prompt]...[End of Prompt]` and `[Start of Input]...[End of Output]` markers
- If markers are missing, the stage logs an error and skips that prompt

## Prediction Extraction

- If LLM output doesn't end with Yes/No/Increase/Decrease/Uncertain, prediction is `None` and `is_valid=False`
- Check `reasoning_steps` to debug multi-step reasoning
