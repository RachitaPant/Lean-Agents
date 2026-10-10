"""C1: tool retrieval + token budget, as a smolagents ToolCallingAgent subclass.

Each lever is a separate option so ablations can attribute the savings:

- single_tool_listing: tools reach the model once, through the native `tools` field. Stock
  smolagents also lists every tool in the system prompt (~41% of a first request on dev).
- compact_descriptions: BFCL repeats each API's boilerplate in every tool description (~27% of
  a first request); it is stated once per API in the system prompt instead.
- retriever="bm25", k: per step, offer the top-k tools for (turn text + last observation),
  plus the API's core tools (agent/retrieval/core_tools.json), plus tools already used.
  If the model calls a real tool that wasn't offered (Groq rejects it with HTTP 400), the tool
  is added and the step retried: the "retrieval miss" safety net.
- history_keep_steps / request_token_budget: keep the last N steps verbatim and shorten older
  observations, so requests stay under the provider's per-request limit (Groq free: 8K TPM).

Prompts, the agent loop and tool execution are otherwise stock smolagents.
"""

from __future__ import annotations

import importlib.resources
import json
import re
from dataclasses import asdict, dataclass

import yaml
from smolagents import ActionStep, ToolCallingAgent
from smolagents.agents import populate_template
from smolagents.models import get_tool_json_schema
from smolagents.utils import AgentGenerationError

from agent.retrieval.tool_index import ToolIndex, split_preamble

TOOL_LISTING_BLOCK = re.compile(
    r"Above example were using notional tools that might not exist for you\. You only have access to these tools:\n"
    r"\s*\{%- for tool in tools\.values\(\) %\}.*?\{%- endfor %\}",
    re.S,
)
LEAN_TOOL_TEXT = (
    "Above example were using notional tools that might not exist for you. "
    "Your tools are given to you in the tool-calling interface; at each step you are offered the tools "
    "most relevant to the current request.\n"
    "  {%- if custom_tool_groups %}\n"
    "  The tools belong to these systems:\n"
    "  {%- for group in custom_tool_groups %}\n"
    "  - {{ group }}\n"
    "  {%- endfor %}\n"
    "  {%- endif %}"
)
MISSING_TOOL = re.compile(r"attempted to call tool '([^']+)' which was not in request\.tools")
CHARS_PER_TOKEN = 4.0  # conservative (Groq measured ~5.0 on this prompt mix), so budgets err low
OLD_OBSERVATION_CHARS = 300
MAX_MISS_RETRIES = 2


@dataclass(frozen=True)
class LeanOptions:
    single_tool_listing: bool = True
    compact_descriptions: bool = True
    retriever: str | None = "bm25"  # None: offer every tool
    k: int = 5
    core_tools: bool = True
    observation_query: bool = True
    history_keep_steps: int | None = 4  # None: replay full history (stock)
    request_token_budget: int | None = 6000  # estimated prompt tokens incl. tool schemas

    def to_dict(self) -> dict:
        return asdict(self)


def lean_prompt_templates() -> dict:
    templates = yaml.safe_load(
        importlib.resources.files("smolagents.prompts").joinpath("toolcalling_agent.yaml").read_text()
    )
    new, n = TOOL_LISTING_BLOCK.subn(LEAN_TOOL_TEXT, templates["system_prompt"])
    if n != 1:
        raise RuntimeError("smolagents system prompt changed; update TOOL_LISTING_BLOCK")
    templates["system_prompt"] = new
    return templates


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f" …[{len(text) - limit} chars cut]"


class LeanToolCallingAgent(ToolCallingAgent):
    def __init__(self, tools, model, options: LeanOptions, core_tool_names: set[str] | None = None, **kwargs):
        if options.compact_descriptions and not options.single_tool_listing:
            raise ValueError("compact_descriptions needs single_tool_listing (the API text lives in the lean prompt)")
        self.options = options
        groups: list[str] = []
        if options.compact_descriptions:
            for tool in tools:
                pre, specific = split_preamble(tool.description)
                if pre:
                    tool.description = specific
                    if pre not in groups:
                        groups.append(pre)
        # set before super().__init__, which renders the system prompt
        self._tool_groups = groups
        self.index = ToolIndex(tools) if options.retriever == "bm25" else None
        self.core = (core_tool_names or set()) if options.core_tools else set()
        self.forced: set[str] = set()  # tools added after a retrieval miss
        self.retrieval_misses = 0
        templates = lean_prompt_templates() if options.single_tool_listing else None
        super().__init__(tools=tools, model=model, prompt_templates=templates, **kwargs)
        self.offered: list[str] = list(self.tools)

    # --- prompts ---------------------------------------------------------------------------
    def initialize_system_prompt(self) -> str:
        if not self.options.single_tool_listing:
            return super().initialize_system_prompt()
        return populate_template(
            self.prompt_templates["system_prompt"],
            variables={
                "tools": self.tools,
                "managed_agents": self.managed_agents,
                "custom_instructions": self.instructions,
                "custom_tool_groups": self._tool_groups,
            },
        )

    # --- tool selection ---------------------------------------------------------------------
    def _used_tools(self) -> set[str]:
        return {
            tc.name for s in self.memory.steps if isinstance(s, ActionStep) and s.tool_calls for tc in s.tool_calls
        }

    def _query(self) -> str:
        parts = [self.task or ""]
        if self.options.observation_query:
            last = next((s for s in reversed(self.memory.steps) if isinstance(s, ActionStep)), None)
            if last is not None:
                parts.append(_shorten(str(last.observations or ""), 500))
                if last.error:
                    parts.append(_shorten(str(last.error), 500))
        return " ".join(parts)

    def select_tools(self) -> list[str]:
        if self.index is None:
            names = [n for n in self.tools if n != "final_answer"]
        else:
            picked = self.index.top_k(self._query(), self.options.k)
            extra = (self.core | self._used_tools() | self.forced) - set(picked)
            names = picked + sorted(n for n in extra if n in self.tools and n != "final_answer")
        self.offered = names + ["final_answer"]
        return self.offered

    @property
    def tools_and_managed_agents(self):
        return [self.tools[n] for n in self.offered if n in self.tools] + list(self.managed_agents.values())

    def _step_stream(self, memory_step):
        for attempt in range(MAX_MISS_RETRIES + 1):
            self.select_tools()
            try:
                yield from super()._step_stream(memory_step)
                return
            except AgentGenerationError as e:
                m = MISSING_TOOL.search(str(e))
                name = m.group(1) if m else None
                if self.index is None or not name or name not in self.tools or attempt == MAX_MISS_RETRIES:
                    raise
                self.forced.add(name)  # a real tool we didn't offer: offer it and retry the step
                self.retrieval_misses += 1

    # --- history ----------------------------------------------------------------------------
    def write_memory_to_messages(self, summary_mode: bool = False):
        keep = self.options.history_keep_steps
        if keep is None and self.options.request_token_budget is None:
            return super().write_memory_to_messages(summary_mode)
        action_steps = [s for s in self.memory.steps if isinstance(s, ActionStep)]
        keep = len(action_steps) if keep is None else keep
        budget = self.options.request_token_budget
        while True:
            messages = self._render(action_steps[: max(0, len(action_steps) - keep)], summary_mode)
            if budget is None or keep == 0 or self._estimate_tokens(messages) <= budget:
                return messages
            keep -= 1

    def _render(self, compress: list[ActionStep], summary_mode: bool):
        compress_ids = {id(s) for s in compress}
        messages = self.memory.system_prompt.to_messages(summary_mode=summary_mode)
        for step in self.memory.steps:
            if id(step) in compress_ids:
                for msg in step.to_messages(summary_mode=True):  # drops the model's free text
                    for part in msg.content or []:
                        if isinstance(part, dict) and part.get("type") == "text":
                            part["text"] = _shorten(part["text"], OLD_OBSERVATION_CHARS)
                    messages.append(msg)
            else:
                messages.extend(step.to_messages(summary_mode=summary_mode))
        return messages

    def _estimate_tokens(self, messages) -> int:
        chars = 0
        for msg in messages:
            content = msg.content if not isinstance(msg, dict) else msg.get("content")
            if isinstance(content, str):
                chars += len(content)
            else:
                chars += sum(len(p.get("text", "")) for p in content or [] if isinstance(p, dict))
        chars += len(json.dumps([get_tool_json_schema(t) for t in self.tools_and_managed_agents]))
        return int(chars / CHARS_PER_TOKEN)

