# Author: Nicola Antonello
import math

import pytest

from regulator_graded_rag.gold import Item
from regulator_graded_rag.metrics import (
    CUTOFFS,
    QuestionScore,
    ndcg,
    reciprocal_rank,
    score_question,
    section_recall,
    summarize,
)

RANKED = ["171.1", "171.1", "173.185", "172.101", "175.10"]


def test_recall_counts_each_cited_section_once() -> None:
    gold = {"173.185", "172.101", "176.1"}
    assert [section_recall(RANKED, gold, k) for k in (2, 3, 4)] == [0.0, 1 / 3, 2 / 3]


def test_reciprocal_rank_is_the_first_cited_section() -> None:
    assert reciprocal_rank(RANKED, {"172.101", "173.185"}) == 1 / 3
    assert reciprocal_rank(RANKED, {"176.1"}) == 0.0


def test_ndcg_gains_once_per_cited_section() -> None:
    assert ndcg(["a", "a", "b"], {"a", "b"}) == pytest.approx(
        1.5 / (1 + 1 / math.log2(3))
    )
    assert ndcg(["b", "a", "c"], {"a", "b"}) == 1.0
    assert ndcg(["c", "a"], {"a"}, k=1) == 0.0


def test_ndcg_counts_at_most_k_sections_in_the_best_ranking() -> None:
    # An item citing 12 sections, all ranked first, has a perfect top 10.
    sections = [f"171.{n}" for n in range(1, 13)]
    assert ndcg(sections, set(sections)) == 1.0


def test_scores_use_the_units_of_passage_ids() -> None:
    item = Item(
        "99-0001-Q1",
        "q",
        "multi_passage",
        "yes",
        ("173.185(c)(1)", "172.101"),
        "2020-03-02",
        "https://web.archive.org/x",
        "dev",
        "PHMSA",
        "owner",
        "2025",
    )
    score = score_question(
        item,
        ["171.1:3", "173.185:12", "173.185:2"]
        + [f"175.10:{n}" for n in range(1, 30)]
        + ["172.101:900"],
    )
    assert score.recall == {5: 0.5, 10: 0.5, 20: 0.5, 50: 1.0} and score.rr == 0.5


def test_summaries_are_means_by_type() -> None:
    def s(t: str, r: float) -> QuestionScore:
        return QuestionScore("x", t, {k: r for k in CUTOFFS}, r, r)

    rows = summarize([s("lookup", 1.0), s("lookup", 0.0), s("table", 0.5)])
    assert [(r.type, r.n, r.recall[10]) for r in rows] == [
        ("all", 3, 0.5),
        ("table", 1, 0.5),
        ("lookup", 2, 0.5),
    ]


def test_no_scores_give_no_rows() -> None:
    # A split whose items are all unanswerable scores nothing, so it has no means.
    assert summarize([]) == []


def test_unanswerable_items_are_not_scored() -> None:
    item = Item(
        "U-1",
        "q",
        "unanswerable",
        "",
        ("searched",),
        "",
        "",
        "dev",
        "owner",
        "owner",
        "2025",
    )
    with pytest.raises(ValueError, match="U-1"):
        score_question(item, ["171.1:1"])
