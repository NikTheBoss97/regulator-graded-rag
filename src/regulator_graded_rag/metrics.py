# Author: Nicola Antonello
"""Retrieval metrics over the sections the regulator cited (ADR-0012).

A ranking of passages becomes a ranking of their units, a passage's ID up to its last
colon. An item's gold is the set of sections its evidence cites, a cited paragraph
counting for its section. Section recall@k, the reciprocal rank and nDCG@10 each count a
cited section once, at the first passage that holds it. Only answerable items are
scored, and the means are reported over all of them and per question type.
"""

import math
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from statistics import fmean

from regulator_graded_rag.gold import TYPES, Item

CUTOFFS = (5, 10, 20, 50)
DEPTH = 50


def unit_of(passage_id: str) -> str:
    """The unit a passage belongs to: its ID before the last colon."""
    return passage_id.rsplit(":", 1)[0]


def section_recall(ranked: Sequence[str], gold: AbstractSet[str], k: int) -> float:
    """The share of the cited sections among the units of the top k."""
    return len(gold & set(ranked[:k])) / len(gold)


def reciprocal_rank(ranked: Sequence[str], gold: AbstractSet[str]) -> float:
    """1 / the rank of the first cited section, or 0.0 when none is ranked."""
    for rank, unit in enumerate(ranked, start=1):
        if unit in gold:
            return 1 / rank
    return 0.0


def ndcg(ranked: Sequence[str], gold: AbstractSet[str], k: int = 10) -> float:
    """Each cited section gains 1 at its first rank within k, discounted by
    log2(rank + 1); the sum is divided by the best ranking's."""
    found: set[str] = set()
    dcg = 0.0
    for rank, unit in enumerate(ranked[:k], start=1):
        if unit in gold and unit not in found:
            found.add(unit)
            dcg += 1 / math.log2(rank + 1)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(gold), k) + 1))
    return dcg / ideal


@dataclass(frozen=True)
class QuestionScore:
    id: str
    type: str
    recall: Mapping[int, float]
    rr: float
    ndcg10: float


def score_question(item: Item, passage_ids: Sequence[str]) -> QuestionScore:
    """The item's scores for a ranking of passage IDs; unanswerable items are refused."""
    if not item.answerable:
        raise ValueError(f"{item.id} is unanswerable, and only answerable items score")
    units = [unit_of(passage_id) for passage_id in passage_ids]
    gold = item.sections
    return QuestionScore(
        item.id,
        item.type,
        {k: section_recall(units, gold, k) for k in CUTOFFS},
        reciprocal_rank(units, gold),
        ndcg(units, gold),
    )


@dataclass(frozen=True)
class Summary:
    type: str
    n: int
    recall: Mapping[int, float]
    mrr: float
    ndcg10: float


def _means(label: str, scores: Sequence[QuestionScore]) -> Summary:
    return Summary(
        label,
        len(scores),
        {k: fmean(s.recall[k] for s in scores) for k in CUTOFFS},
        fmean(s.rr for s in scores),
        fmean(s.ndcg10 for s in scores),
    )


def summarize(scores: Sequence[QuestionScore]) -> list[Summary]:
    """The means over all scores, then per question type present, in TYPES order;
    no rows when nothing was scored."""
    if not scores:
        return []
    rows = [_means("all", scores)]
    for kind in TYPES:
        of_kind = [s for s in scores if s.type == kind]
        if of_kind:
            rows.append(_means(kind, of_kind))
    return rows
