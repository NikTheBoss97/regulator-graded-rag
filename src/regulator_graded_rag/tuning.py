# Author: Nicola Antonello
"""Cross-validated choice of one setting on the dev split (ADR-0024).

assign_folds deals each question type's items into folds by the SHA-256 of a committed
seed and the item's ID, so every fold holds a near-equal share of each type, and an
item's fold depends on nothing else. choose picks, for each fold, the grid value with
the highest mean recall@10 over the other folds' answerable items, so no question is
scored with a value chosen on it; ties go to the first value in grid order. It also picks
the value on all of dev, which is the one phase 4 uses.
"""

import hashlib
import math
from collections.abc import Mapping, Sequence

from regulator_graded_rag.gold import Item


def assign_folds(items: Sequence[Item], seed: str, folds: int) -> dict[str, int]:
    """Each item's fold, 0 to folds - 1: within its type, items ordered by
    SHA-256("<seed>:<id>") and dealt round-robin."""
    by_type: dict[str, list[Item]] = {}
    for item in items:
        by_type.setdefault(item.type, []).append(item)
    fold_of: dict[str, int] = {}
    for kind in by_type.values():
        ordered = sorted(
            kind,
            key=lambda item: hashlib.sha256(f"{seed}:{item.id}".encode()).hexdigest(),
        )
        for position, item in enumerate(ordered):
            fold_of[item.id] = position % folds
    return fold_of


def _best(scores: Mapping[float, Mapping[str, float]], ids: Sequence[str]) -> float:
    """The grid value with the highest mean over the items, the first one on a tie."""
    chosen, best = None, -math.inf
    for value, recall in scores.items():
        mean = math.fsum(recall[i] for i in ids) / len(ids)
        if mean > best:
            chosen, best = value, mean
    assert chosen is not None
    return chosen


def choose(
    scores: Mapping[float, Mapping[str, float]],
    fold_of: Mapping[str, int],
    folds: int,
) -> tuple[dict[int, float], float]:
    """Each fold's value, chosen on the other folds' items, and the value chosen on all
    of them. scores maps each grid value, in grid order, to each answerable item's
    recall@10."""
    ids = sorted(next(iter(scores.values())))
    if any(sorted(recall) != ids for recall in scores.values()):
        raise ValueError("every grid value must score the same items")
    chosen: dict[int, float] = {}
    for fold in range(folds):
        others = [i for i in ids if fold_of[i] != fold]
        if not others:
            raise ValueError(f"fold {fold} holds every scored item")
        chosen[fold] = _best(scores, others)
    return chosen, _best(scores, ids)
