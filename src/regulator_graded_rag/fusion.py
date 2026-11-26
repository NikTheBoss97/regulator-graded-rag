# Author: Nicola Antonello
"""Fusing two first stages' rankings into one (ADR-0024).

Both methods score the union of the lists they are given and return its top DEPTH,
best first. Passages with equal scores keep the order in which they first appear: the
first list's order, then the second's passages that the first did not hold.

- rrf: a passage scores the sum of 1/(k + rank) over the lists it is in, with ranks
  counted from 1.
- weighted: alpha times the dense list's score plus 1 - alpha times BM25's, each
  min-max normalized over its own list for the question. A passage missing from a list
  scores 0 there, and so does every passage of a list whose scores are all equal. A
  list's lowest passage also scores 0, so it ties with the passages the list lacks: with
  alpha 0 the ties keep BM25's order and give exactly its ranking, while with alpha 1
  they put BM25's passages before the dense list's lowest ones.
"""

import math
from collections.abc import Mapping, Sequence

from regulator_graded_rag.bm25 import Hit
from regulator_graded_rag.metrics import DEPTH


def _first_seen(lists: Sequence[Sequence[Hit]]) -> dict[str, int]:
    """Each passage's position in the lists read one after the other, first time
    only."""
    seen: dict[str, int] = {}
    for hits in lists:
        for hit in hits:
            seen.setdefault(hit.passage_id, len(seen))
    return seen


def _best(scores: Mapping[str, float], seen: Mapping[str, int]) -> list[Hit]:
    ranked = sorted(scores, key=lambda passage: (-scores[passage], seen[passage]))
    return [Hit(passage, scores[passage]) for passage in ranked[:DEPTH]]


def rrf(lists: Sequence[Sequence[Hit]], k: float) -> list[Hit]:
    """The lists fused by reciprocal rank: the sum of 1/(k + rank), ranks from 1."""
    parts: dict[str, list[float]] = {}
    for hits in lists:
        for rank, hit in enumerate(hits, start=1):
            parts.setdefault(hit.passage_id, []).append(1 / (k + rank))
    scores = {passage: math.fsum(terms) for passage, terms in parts.items()}
    return _best(scores, _first_seen(lists))


def _min_max(hits: Sequence[Hit]) -> dict[str, float]:
    """Each hit's score scaled to 0..1 over the list; all 0 when the scores are equal."""
    if not hits:
        return {}
    low = min(hit.score for hit in hits)
    high = max(hit.score for hit in hits)
    if high == low:
        return {hit.passage_id: 0.0 for hit in hits}
    return {hit.passage_id: (hit.score - low) / (high - low) for hit in hits}


def weighted(bm25: Sequence[Hit], dense: Sequence[Hit], alpha: float) -> list[Hit]:
    """BM25's and the dense list's hits fused by alpha * dense + (1 - alpha) * bm25,
    each normalized over its own list, 0 where a list lacks the passage."""
    lexical, semantic = _min_max(bm25), _min_max(dense)
    seen = _first_seen([bm25, dense])
    scores = {
        passage: alpha * semantic.get(passage, 0.0)
        + (1 - alpha) * lexical.get(passage, 0.0)
        for passage in seen
    }
    return _best(scores, seen)
