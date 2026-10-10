"""Small, dependency-free Okapi BM25 for ranking tool descriptions against a query."""

from __future__ import annotations

import math
import re
from collections import Counter

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    """a an and are as at be by can could do does for from has have i if in into is it its me my
    of on or our please so that the their them then there these this to was we what when which
    will with would you your""".split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens; splits camelCase and snake_case (lockDoors -> lock, doors) and
    drops stopwords. A crude suffix strip makes 'files'/'file', 'booking'/'book' match."""
    text = _CAMEL.sub(" ", text).replace("_", " ").lower()
    out = []
    for tok in _TOKEN.findall(text):
        if tok in STOPWORDS:
            continue
        for suffix in ("ing", "es", "s"):
            if len(tok) > len(suffix) + 3 and tok.endswith(suffix):
                tok = tok[: -len(suffix)]
                break
        out.append(tok)
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.avgdl = sum(self.len) / max(1, len(docs))
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for tf, dl in zip(self.tf, self.len):
            s = 0.0
            for t in query:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out
