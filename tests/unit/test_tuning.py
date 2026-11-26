# Author: Nicola Antonello
import hashlib
import random
from collections import Counter

from regulator_graded_rag.gold import Item
from regulator_graded_rag.tuning import assign_folds, choose


def item(id_: str, type_: str) -> Item:
    evidence = () if type_ == "unanswerable" else ("171.1",)
    return Item(id_, "q", type_, "", evidence, "", "", "dev", "PHMSA", "owner", "2025")


ITEMS = [
    *(item(f"17-{n:04}-Q1", "lookup") for n in range(13)),
    *(item(f"18-{n:04}-Q1", "table") for n in range(7)),
    *(item(f"U-{n}", "unanswerable") for n in range(4)),
]


def test_folds_split_each_type_evenly() -> None:
    fold_of = assign_folds(ITEMS, "seed", 5)
    assert set(fold_of) == {i.id for i in ITEMS}
    for kind in ("lookup", "table", "unanswerable"):
        counts = Counter(fold_of[i.id] for i in ITEMS if i.type == kind)
        sizes = [counts.get(fold, 0) for fold in range(5)]
        assert max(sizes) - min(sizes) <= 1, (kind, sizes)


def test_each_type_is_dealt_from_the_first_fold() -> None:
    # The rule is exact, so a record's folds can be dealt again from its seed: within
    # each type, the item with the smallest hash goes to fold 0, the next to fold 1.
    fold_of = assign_folds(ITEMS, "seed", 5)
    for kind in ("lookup", "table", "unanswerable"):
        ordered = sorted(
            (i for i in ITEMS if i.type == kind),
            key=lambda i: hashlib.sha256(f"seed:{i.id}".encode()).hexdigest(),
        )
        assert [fold_of[i.id] for i in ordered[:2]] == [0, 1]


def test_folds_depend_only_on_seed_and_id() -> None:
    shuffled = ITEMS.copy()
    random.Random(7).shuffle(shuffled)
    assert assign_folds(shuffled, "seed", 5) == assign_folds(ITEMS, "seed", 5)
    assert assign_folds(ITEMS, "another seed", 5) != assign_folds(ITEMS, "seed", 5)


def test_choose_never_uses_the_folds_own_questions() -> None:
    # Fold 0 holds a and b, fold 1 holds c and d. Value 10 is best on fold 1's
    # questions, value 60 on fold 0's, and on all of dev 60 wins.
    fold_of = {"a": 0, "b": 0, "c": 1, "d": 1}
    scores = {
        10.0: {"a": 0.0, "b": 0.0, "c": 0.6, "d": 0.6},
        60.0: {"a": 1.0, "b": 1.0, "c": 0.5, "d": 0.5},
    }
    chosen, all_dev = choose(scores, fold_of, 2)
    # Each fold gets the value chosen on the other fold, worse on its own questions.
    assert chosen == {0: 10.0, 1: 60.0}
    assert all_dev == 60.0


def test_the_all_dev_value_is_chosen_on_every_item() -> None:
    # Here fold 1's value, chosen on fold 0's questions, differs from the value that is
    # best on all of them, which phase 4 uses.
    fold_of = {"a": 0, "b": 0, "c": 1, "d": 1}
    scores = {
        10.0: {"a": 0.6, "b": 0.6, "c": 0.0, "d": 0.0},
        60.0: {"a": 0.5, "b": 0.5, "c": 1.0, "d": 1.0},
    }
    assert choose(scores, fold_of, 2) == ({0: 60.0, 1: 10.0}, 60.0)


def test_choose_breaks_ties_by_grid_order() -> None:
    fold_of = {"a": 0, "b": 1}
    scores = {60.0: {"a": 0.5, "b": 0.5}, 10.0: {"a": 0.5, "b": 0.5}}
    assert choose(scores, fold_of, 2) == ({0: 60.0, 1: 60.0}, 60.0)
