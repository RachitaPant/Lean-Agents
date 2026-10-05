# Architecture Notes

How smolagents and BFCL work, and where C1–C5 hook in. Written in Phase 1 (2026-10-04) against
**smolagents 1.26.0** and **BFCL v4** (gorilla commit `6ea5797`, 2026-03-23). Line numbers refer
to those versions.

---

## 1. The smolagents loop (`ToolCallingAgent`)

```
agent.run(task, reset=False)
 └─ MultiStepAgent.run                    agents.py:436   appends TaskStep to memory
     └─ _run_stream                        agents.py:540   while not final_answer and step <= max_steps
         └─ ToolCallingAgent._step_stream  agents.py:1276  ONE step:
             1. messages = write_memory_to_messages()      system prompt + every past step
             2. chat_message = model.generate(messages,
                    tools_to_call_from=all tools,          native `tools` param
                    stop_sequences=[...])
             3. no native tool_calls? → model.parse_tool_calls()  (parse JSON out of text)
             4. process_tool_calls()               agents.py:1361
                 └─ execute_tool_call()            agents.py:1453
                     ├─ unknown name → AgentToolExecutionError
                     ├─ validate_tool_arguments()  tools.py:1361  type check vs tool.inputs
                     └─ tool(**args) → observation string
             5. final_answer called → ActionOutput(is_final_answer=True) → run ends
         └─ _finalize_step → step_callbacks(memory_step, agent=...)
```

Key facts:

- **Memory replays every step on every call.** `write_memory_to_messages` (agents.py:758)
  concatenates the system prompt and all prior `ActionStep`s. Tool calls and observations are
  sent as plain-text messages ("Calling tools: [...]", "Observation: ...") converted to
  assistant/user roles (`tool_role_conversions`, models.py:282), **not** native tool messages.
  Prompt tokens therefore grow with the number of steps, across turns when `reset=False`.
- **Tool docs are sent twice per call.** The system prompt template
  (`prompts/toolcalling_agent.yaml:93`) lists every tool via `to_tool_calling_prompt()`, *and*
  `generate()` sends the same tools as JSON schemas in the native `tools` field. Measured on
  the smoke tasks (characters, not tokens):

  | Task | Tools | System prompt | of which tool docs | Native tools JSON |
  |---|---|---|---|---|
  | multi_turn_base_100 | 21 | 10,245 | 7,226 | 8,985 |
  | multi_turn_base_3 | 19 | 13,756 | 10,743 | 12,362 |
  | multi_turn_base_17 | 29 | 16,673 | 13,630 | 16,061 |

  Groq reported 3.7K–6.2K input tokens on the *first* step of these tasks.
- **Ending a run requires `final_answer`.** It is auto-added as a tool (agents.py:402). The
  default `tool_choice="required"` (models.py:510) forces a tool call on every step.
- **Errors.** Tool/argument errors (`AgentToolCallError`, `AgentToolExecutionError`) are stored
  in the step and the loop continues, so the model sees them. A failure inside
  `model.generate` (`AgentGenerationError`, e.g. a provider HTTP 400) is **fatal**: it
  propagates out of `run()`.
- **Retries.** `ApiModel` retries rate-limit errors (429) 3 times with a 60 s base wait
  (models.py:38–41).
- **Parallel tool calls** run in a thread pool unless `max_tool_threads=1`. BFCL APIs are
  stateful (`cd` then `ls`), so we use 1.
- **Managed agents** (for C4) are passed as `managed_agents=[...]` and exposed to the manager as
  callable tools.

## 2. BFCL multi-turn

- **Data.** `BFCL_v4_multi_turn_base.json` has 200 tasks. Each has `question` (one list of
  messages per turn), `initial_config` (per-class state), and `involved_classes`. The ground
  truth (`possible_answer/…`) is a list of call strings per turn, e.g.
  `["cd(folder='document')", "mkdir(dir_name='temp')"]`.
- **Tools.** The model gets *every* function of every involved class (func docs in
  `data/multi_turn_func_doc/*.json`, 9–22 per class). The `excluded_function` field is not
  used in v4 base.
- **Simulated APIs** are plain Python classes in `func_source_code/` with
  `_load_scenario(config)`. Optional params have Python defaults.
- **Inference protocol** (`base_handler.inference_multi_turn_FC`). Per turn: call the model,
  execute its calls, repeat until a reply has **no tool calls** (end of turn). More than 20 steps
  in a turn means a forced quit, and the task fails.
- **Checking is state-based and replays strings** (`multi_turn_checker.py`). The checker does
  not look at our live objects. For each turn it **re-executes the model's logged call strings**
  on fresh instances, executes the ground truth on separate instances, then requires:
  1. a non-empty model response for every turn whose ground truth is non-empty,
  2. **state equality**: every public attribute of every instance matches,
  3. **response coverage**: every ground-truth call's output appears among the model's outputs
     so far (unordered; extra calls are allowed).

  So extra exploratory calls (`ls`, `pwd`) are fine, but anything that changes state differently
  fails.
- **Checker gotcha.** Instances are cached in module `globals()` keyed by
  `model_name + task id`. Scoring the same task twice in one process needs a fresh `model_name`
  each time (`score()` uses a random suffix).

## 3. Our adapter (`eval/bfcl_adapter.py`)

- BFCL code is vendored **unmodified** in `third_party/bfcl_eval/`. It is only the 8 multi-turn
  API classes, the checker and the base-category data (Apache-2.0, LICENSE kept). We don't use
  `pip install bfcl-eval`, because it pulls torch, sentence-transformers, faiss and many
  provider SDKs. That's too heavy for this laptop and for Vercel's 500 MB bundle.
- `BFCLEnv(task)` builds live instances and wraps each documented method as a `BFCLTool`.
  Every call that reaches an API is logged as a BFCL call string (`format_call`) into
  `calls[turn][step]`, the exact shape `multi_turn_checker` takes. `score()` runs the official
  checker.
- Schema mapping: `float→number`, `dict→object`, `tuple→array`. Optional params become
  `nullable` **and** `type: [T, "null"]`. The second form is needed because Groq validates tool
  calls server-side, ignores smolagents' non-standard `nullable`, and returned HTTP 400 on
  `path: null`. A null arg is dropped so the method default applies.
- **Fidelity test.** `tests/test_bfcl_adapter.py` replays the ground truth of all 200 base tasks
  through our tool wrappers and requires the official checker to score each one valid. It also
  checks that wrong or empty calls score invalid.

### Turn protocol (stock agent vs BFCL)

smolagents ends a run only on `final_answer`, under `tool_choice="required"`. BFCL ends a turn when
the model replies without tool calls. On Groq, `gpt-oss-120b` often replies in plain text after
one tool call. Under `"required"`, Groq rejects that reply with HTTP 400, which is fatal in
smolagents. **All 3 smoke tasks died this way on step 2**
(`eval/results/phase1_smoke_strict_stock.jsonl`).

So the baseline config is **stock smolagents + BFCL turn protocol** (`eval/run_smoke.py`):
`tool_choice="auto"`, and a text-only reply becomes a `final_answer` call
(`BFCLTurnModel.parse_tool_calls`). Prompts, tool schemas and the loop are unchanged. This
follows the benchmark's own protocol and is not an agent improvement. Every config, including
the baseline, uses it.

### Phase 1 smoke results (`eval/results/phase1_smoke.jsonl`, `openai/gpt-oss-120b`)

| Task | Result | LLM calls | Tokens (prompt+completion) | Cause |
|---|---|---|---|---|
| multi_turn_base_3 | **pass** | 14 | 78,848 + 1,833 | — |
| multi_turn_base_100 | fail | 2 | 3,731 + 61 | called non-existent tool `answer` (HTTP 400, fatal) |
| multi_turn_base_17 | fail | 6 | 31,858 + 390 | Groq **daily** token limit (200K TPD) hit mid-task (HTTP 429) |

multi_turn_base_100 also passed in an earlier run (5 calls, 19,717 + 490 tokens), so results are
not deterministic run to run. That run's file was overwritten after the nullable-schema fix,
so it is not in the results file.

Implications for later phases:
- **Tokens per task are large and grow with steps** (memory replay + tool docs sent twice).
  One 14-call task used ~80K tokens, i.e. ~40% of a model's 200K daily quota. That makes C1,
  and spreading runs across Groq models (separate quotas), urgent before the Phase 3 pilot.
- **Quota exhaustion must not count as a model failure.** `eval/run.py` must detect 429/TPD,
  stop, and resume the task the next day (Phase 3 item).
- The 8K TPM limit makes runs slow (about one call per minute at 5–7K tokens per call).

### Re-run of the failed tasks on `openai/gpt-oss-20b` (`eval/results/phase1_smoke_gpt-oss-20b.jsonl`)

| Task | Result | LLM calls | Tokens | Cause |
|---|---|---|---|---|
| multi_turn_base_100 | fail | 2 | 3,731 + 112 | Turn 1 correct; then Groq HTTP 400 `output_parse_failed` (model emitted raw reasoning text), fatal |
| multi_turn_base_17 | fail | 20 | 133,356 + 3,647 (45 min) | State mismatch: `send_message` sent **4×** instead of once; then HTTP 413 |

What went wrong in multi_turn_base_17, turn 3:
1. For the zero-argument tool `view_messages_sent`, the model passed `{"arguments": {}}` or
   `{"args": {}}`. smolagents rejected it ("Argument arguments is not in the tool's input
   schema"). That is a wrapper the model invents for empty-parameter tools; C2 can unwrap it.
2. After each rejection the model **re-sent the message** before retrying the view, so the
   state-changing call was duplicated, and BFCL's state check failed. A repair loop must not
   make the model redo side-effecting calls (C2 feedback should say the send already succeeded).
3. **HTTP 413: a single request exceeded the 8K TPM limit** (8,113 tokens requested). Because
   memory replays every step, the prompt passes 8K after ~20 steps on a 29-tool task, and
   **Groq's free tier can't serve the request at all**. That is a hard ceiling, not a slowdown.
   C1 (fewer tool docs) plus history trimming are needed for long tasks to be runnable at all.

Remaining failure seen: `gpt-oss-120b` sometimes calls a non-existent tool `answer` (instead of
`final_answer`). Groq rejects it server-side (HTTP 400, `tool_use_failed`), which is fatal.
This is a C2 target, not patched in the baseline.

## 4. Where C1–C5 hook in

| Contribution | Hook point | Approach |
|---|---|---|
| **C1 tool retrieval** | Before `model.generate` in `_step_stream`: the `tools_to_call_from` list **and** the tool list rendered into the system prompt | Subclass `ToolCallingAgent`; per step, retrieve top-k tools for (task + recent steps) and pass only those. Also stop the double listing (prompt + native). Safety net: unknown tool name → re-retrieve with larger k. Avoid a local embedding model at runtime (project rule: no local models unless necessary); precompute tool embeddings at build time or start with BM25. |
| **C2 validate & repair** | (a) `execute_tool_call` (unknown tool, `validate_tool_arguments`); (b) **`model.generate` raising on provider-side `tool_use_failed`**, which is currently fatal | Catch `AgentGenerationError` with code `tool_use_failed`, parse `failed_generation`, turn it into targeted feedback ("tool `answer` doesn't exist; use `final_answer`"), retry with a cap. Add jsonschema checks with precise messages. Log the failure taxonomy. |
| **C3 plan caching** | Around `agent.run` per task/turn | On success, store the turn's call sequence (`env.calls`) as a template with placeholders. On a new task, retrieve a template, adapt it with one LLM call, execute it, and fall back to normal steps on error. |
| **C4 multi-agent** | `managed_agents=[...]` | Planner/executor/verifier as managed agents; compare at equal token budget. |
| **C5 provider router** | `Model` layer: a `Model` subclass wrapping several `OpenAIServerModel`s | Choose a provider per call from Redis quota counters; on 429/timeout fail over. smolagents' built-in 60 s retry should be disabled (`retry=False`) so the router decides. |

Logging for Phase 3 can use `step_callbacks` (already used by the adapter to close steps) plus
`ActionStep.token_usage` and `timing`.
