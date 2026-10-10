"""Index a task's tools and pick the top-k for a query (C1 tool retrieval).

Tool documents are built from the tool name (split into words), the description with the
per-API boilerplate removed, and the parameter names and descriptions.
"""

from __future__ import annotations

from smolagents import Tool

from agent.retrieval.bm25 import BM25, tokenize

PREAMBLE_MARKER = "Tool description:"


def split_preamble(description: str) -> tuple[str, str]:
    """BFCL descriptions are '<API boilerplate> Tool description: <specific text>'.
    Returns (preamble, specific). No marker → ('', description)."""
    if PREAMBLE_MARKER in description:
        pre, rest = description.split(PREAMBLE_MARKER, 1)
        return pre.strip(), rest.strip()
    return "", description


def _response_fields(schema: dict) -> list[str]:
    """Field names and descriptions of a BFCL response schema (recursively)."""
    out = []
    for name, spec in (schema.get("properties") or {}).items():
        out += [name, str(spec.get("description", ""))]
        if isinstance(spec, dict):
            out += _response_fields(spec)
            if isinstance(spec.get("items"), dict):
                out += _response_fields(spec["items"])
    return out


def tool_document(tool: Tool) -> list[str]:
    _, specific = split_preamble(tool.description)
    parts = [tool.name, tool.name, specific]  # name twice: it's the strongest signal
    for pname, spec in tool.inputs.items():
        parts += [pname, str(spec.get("description", ""))]
    # What a tool returns is often what the user asks for ("price" -> get_stock_info)
    parts += _response_fields(getattr(tool, "response_doc", None) or {})
    return tokenize(" ".join(parts))


class ToolIndex:
    def __init__(self, tools: list[Tool]):
        self.tools = [t for t in tools if t.name != "final_answer"]
        self.bm25 = BM25([tool_document(t) for t in self.tools])

    def rank(self, query: str) -> list[tuple[str, float]]:
        scores = self.bm25.scores(tokenize(query))
        order = sorted(range(len(self.tools)), key=lambda i: (-scores[i], self.tools[i].name))
        return [(self.tools[i].name, scores[i]) for i in order]

    def top_k(self, query: str, k: int) -> list[str]:
        return [name for name, _ in self.rank(query)[:k]]
