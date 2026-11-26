# Author: Nicola Antonello
import math

from regulator_graded_rag.bm25 import Hit
from regulator_graded_rag.fusion import rrf, weighted
from regulator_graded_rag.metrics import DEPTH


def hits(*pairs: tuple[str, float]) -> list[Hit]:
    return [Hit(passage, score) for passage, score in pairs]


def ids(found: list[Hit]) -> list[str]:
    return [hit.passage_id for hit in found]


def scores(found: list[Hit]) -> dict[str, float]:
    return {hit.passage_id: hit.score for hit in found}


def test_rrf_rewards_a_passage_in_both_lists() -> None:
    # x is second in both lists, a and b first in one each: being found twice wins.
    fused = rrf([hits(("a", 9.0), ("x", 8.0)), hits(("b", 0.9), ("x", 0.8))], 60.0)
    assert ids(fused) == ["x", "a", "b"]


def test_rrf_uses_one_based_ranks() -> None:
    # A passage ranked first in one list only scores 1/(k + 1), not 1/k.
    fused = scores(rrf([hits(("a", 9.0), ("b", 8.0)), hits(("c", 0.5))], 60.0))
    assert math.isclose(fused["a"], 1 / 61)
    assert math.isclose(fused["b"], 1 / 62)
    assert math.isclose(fused["c"], 1 / 61)


def test_rrf_breaks_ties_by_the_first_lists_order_then_the_seconds() -> None:
    # a and c both score 1/61, as b and d score 1/62: the first list's passages lead.
    fused = rrf([hits(("a", 9.0), ("b", 8.0)), hits(("c", 0.9), ("d", 0.8))], 60.0)
    assert ids(fused) == ["a", "c", "b", "d"]


def test_fusion_keeps_the_top_depth() -> None:
    first = hits(*((f"a{i}", -i) for i in range(DEPTH)))
    second = hits(*((f"b{i}", -i) for i in range(DEPTH)))
    assert len(rrf([first, second], 60.0)) == DEPTH
    assert len(weighted(first, second, 0.5)) == DEPTH


BM25 = hits(("p1", 10.0), ("p2", 5.0), ("p4", 2.0))
DENSE = hits(("p2", 0.9), ("p3", 0.5), ("p1", 0.1))


def test_weighted_alpha_one_ranks_by_the_dense_scores() -> None:
    # Only the dense scores count. Its lowest passage, p1, scores 0 as p4 does, which
    # it did not find, and the tie keeps BM25's order: alpha 1 follows the dense order
    # only above its minimum.
    assert ids(weighted(BM25, DENSE, 1.0)) == ["p2", "p3", "p1", "p4"]


def test_weighted_alpha_zero_is_the_bm25_order() -> None:
    # BM25's lowest passage, p4, ties at 0 with p3, which only the dense list found,
    # and the tie keeps BM25's order, so alpha 0 gives exactly BM25's ranking.
    assert ids(weighted(BM25, DENSE, 0.0)) == ["p1", "p2", "p4", "p3"]


def test_a_missing_passage_scores_zero_in_that_list() -> None:
    # Each list is min-max normalized over its own hits: BM25 gives p1 1, p2 0.375 and
    # p4 0; dense gives p2 1, p3 0.5 and p1 0. p3 is not in BM25's list, and p4 not in
    # the dense one, so each scores 0 there, and the missing passage does not enter the
    # other list's minimum.
    fused = scores(weighted(BM25, DENSE, 0.5))
    assert math.isclose(fused["p2"], 0.5 * 1 + 0.5 * 0.375)
    assert math.isclose(fused["p1"], 0.5 * 0 + 0.5 * 1)
    assert math.isclose(fused["p3"], 0.5 * 0.5 + 0.5 * 0)
    assert fused["p4"] == 0.0


def test_equal_scores_normalize_to_zero() -> None:
    # A list that cannot tell its passages apart adds nothing to any of them.
    fused = scores(weighted(hits(("p1", 3.0), ("p2", 3.0)), DENSE, 0.5))
    assert math.isclose(fused["p2"], 0.5 * 1)
    assert math.isclose(fused["p1"], 0.0)
    assert math.isclose(fused["p3"], 0.5 * 0.5)
