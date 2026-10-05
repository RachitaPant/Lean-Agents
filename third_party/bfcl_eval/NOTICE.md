# Vendored: Berkeley Function Calling Leaderboard (BFCL)

- Source: https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard/bfcl_eval
- Commit: `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8` (2026-03-23)
- License: Apache License 2.0, see `LICENSE` (copied from the gorilla repo root).
- Copyright: the Gorilla / BFCL authors.

## What is included

A subset only, kept at the original paths so the original imports work:

- `eval_checker/multi_turn_eval/multi_turn_checker.py`, `multi_turn_utils.py`
- `eval_checker/multi_turn_eval/func_source_code/`: the 8 multi-turn API classes
  (file system, math, message, posting, ticket, trading bot, travel, vehicle) + `long_context.py`
- `constants/executable_backend_config.py`
- `data/BFCL_v4_multi_turn_base.json`, `data/possible_answer/BFCL_v4_multi_turn_base.json`,
  and the matching `data/multi_turn_func_doc/*.json`
- empty package `__init__.py` files

Not included: model handlers, web search (needs SerpAPI), memory categories, other datasets.

## Modifications

None. All files are byte-for-byte copies of the commit above.
Our integration code lives in `eval/bfcl_adapter.py`.
