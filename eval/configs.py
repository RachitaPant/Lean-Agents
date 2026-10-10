"""Named agent configurations for evaluation. Every result record stores its full config.

Sampling follows BFCL's own default (temperature 0.001) plus a fixed seed. Groq treats the seed
as best-effort only, so run-to-run noise is measured separately (Phase 3 noise check).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

from agent.lean_agent import LeanOptions
from agent.repair import RepairOptions
from agent.runner import BFCL_MAX_STEPS_PER_TURN, make_model


@dataclass(frozen=True)
class Config:
    name: str
    description: str
    model_id: str = "openai/gpt-oss-120b"
    provider: str = "groq"
    temperature: float = 0.001  # BFCL default (bfcl_eval/__main__.py)
    seed: int = 42
    max_steps_per_turn: int = BFCL_MAX_STEPS_PER_TURN
    lean: LeanOptions | None = field(default=None)  # None = stock agent; else C1 options

    def make_model(self):
        return make_model(self.model_id, temperature=self.temperature, seed=self.seed)

    def to_dict(self) -> dict:
        return asdict(self)


C1 = LeanOptions()  # defaults: single listing, compact docs, BM25 k=5 + core tools, history 4 steps / 6K budget
# Every C1 lever off: behaves as the stock agent, so C2 can be measured on its own
STOCK = LeanOptions(
    single_tool_listing=False, compact_descriptions=False, retriever=None, core_tools=False,
    observation_query=False, history_keep_steps=None, request_token_budget=None,
)
C2 = RepairOptions()

CONFIGS: dict[str, Config] = {
    c.name: c
    for c in [
        Config(
            name="baseline",
            description="Stock smolagents ToolCallingAgent + BFCL turn protocol (text reply ends a turn).",
        ),
        Config(name="c1", description="Baseline + C1 (all levers, k=5).", lean=C1),
        # Ablations, one lever group at a time (tune on eval/tasks/dev.jsonl only)
        Config(
            name="c1_listing",
            description="Baseline + single tool listing + compact descriptions only (no retrieval, full history).",
            lean=replace(C1, retriever=None, core_tools=False, history_keep_steps=None, request_token_budget=None),
        ),
        Config(
            name="c1_retrieval",
            description="c1_listing + BM25 retrieval k=5 with core tools (full history).",
            lean=replace(C1, history_keep_steps=None, request_token_budget=None),
        ),
        Config(name="c1_k3", description="c1 with k=3.", lean=replace(C1, k=3)),
        Config(name="c1_k10", description="c1 with k=10.", lean=replace(C1, k=10)),
        Config(name="c2", description="Baseline + C2 validate-and-repair only.", lean=replace(STOCK, repair=C2)),
        Config(name="c1_c2", description="Baseline + C1 + C2.", lean=replace(C1, repair=C2)),
    ]
}
