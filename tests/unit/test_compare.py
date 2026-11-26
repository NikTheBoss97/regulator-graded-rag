# Author: Nicola Antonello
import json
import math
import statistics
from pathlib import Path

import pytest

from regulator_graded_rag.compare import (
    DRAWS,
    compare,
    letter_sums,
    main,
    paired_p,
    t_quantile,
)
from regulator_graded_rag.power import mdd


def make_run(
    root: Path,
    name: str,
    recalls: list[float],
    gold: str = "g" * 64,
    corpus: str = "c" * 64,
) -> Path:
    """A complete, scored dev run whose questions alternate lookup and table."""
    folder = root / name
    folder.mkdir()
    run = {
        "status": "complete",
        "split": "dev",
        "corpus_version": corpus,
        "gold": {"version": gold},
    }
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    per_question = [
        {
            "id": f"Q{i:03}",
            "type": "lookup" if i % 2 == 0 else "table",
            "recall": {"10": r},
        }
        for i, r in enumerate(recalls)
    ]
    scores = {"gold_version": gold, "per_question": per_question, "summary": []}
    (folder / "scores.json").write_text(json.dumps(scores), encoding="utf-8")
    return folder


def test_t_quantile_matches_known_values() -> None:
    assert t_quantile(0.975, 213) == pytest.approx(1.971164, abs=1e-5)
    assert t_quantile(0.975, 9) == pytest.approx(2.262157, abs=1e-4)


def test_identical_runs_give_p_one_and_a_zero_interval(tmp_path: Path) -> None:
    c = compare(
        make_run(tmp_path, "a", [0.0, 1.0] * 50),
        make_run(tmp_path, "b", [0.0, 1.0] * 50),
    )
    assert (c.mean, c.low, c.high, c.p) == (0.0, 0.0, 0.0, 1.0)


def test_a_large_consistent_gain_is_significant(tmp_path: Path) -> None:
    c = compare(
        make_run(tmp_path, "a", [0.0] * 100),
        make_run(tmp_path, "b", [1.0] * 60 + [0.0] * 40),
    )
    assert c.p < 0.001 and c.low > 0 and c.improved and not c.regressed
    # No random draw reaches a gain this large, and the observed arrangement still
    # counts, so p is the smallest value the test can give, never 0.
    assert c.p == 1 / (1 + DRAWS)


def test_the_p_value_is_reproducible_from_its_seed() -> None:
    diffs = [0.1, -0.2, 0.3] * 40
    assert paired_p(diffs) == paired_p(diffs)
    assert paired_p(diffs, seed="other") != paired_p(diffs)


@pytest.mark.parametrize("field", ["corpus", "gold"])
def test_runs_on_other_versions_are_not_compared(tmp_path: Path, field: str) -> None:
    a = make_run(tmp_path, "a", [0.0, 1.0])
    b = make_run(tmp_path, "b", [0.0, 1.0], **{field: "h" * 64})
    with pytest.raises(ValueError, match=field):
        compare(a, b)


def test_only_dev_runs_are_compared(tmp_path: Path) -> None:
    # The held-out folder has no scores.json, so the refusal must come before any
    # scores are opened; held-out results come with the owner's run (ADR-0014).
    a = make_run(tmp_path, "a", [0.0, 1.0])
    held_out = tmp_path / "held-out"
    held_out.mkdir()
    run = {"status": "complete", "split": "heldout", "corpus_version": "c" * 64}
    (held_out / "run.json").write_text(json.dumps(run), encoding="utf-8")
    with pytest.raises(ValueError, match="dev"):
        compare(a, held_out)


def test_letter_sums_add_each_letters_questions_in_letter_order() -> None:
    # A question's letter is its ID without "-Q<n>"; Q10 sorts before Q2 and stays
    # with its letter.
    ids = ["17-0002-Q1", "17-0002-Q3", "18-0001-Q1", "18-0001-Q10", "18-0001-Q2"]
    assert letter_sums(ids, [0.0, -1.0, 0.5, 1.0, 0.25]) == [-1.0, 1.75]


def test_a_letter_level_test_keeps_the_per_question_statistic() -> None:
    # Flipping whole letters changes the unit of randomization, not the statistic: with
    # one question per letter the two tests are the same test.
    diffs = [0.5, -0.25, 1.0, 0.75, -0.5, 1.0, 0.25, 0.5, 1.0]
    ids = [f"{n:02}-0001-Q1" for n in range(len(diffs))]
    assert paired_p(letter_sums(ids, diffs)) == paired_p(diffs)


def test_t_quantile_is_rounded_to_twelve_digits() -> None:
    # A last-bit difference in a math library must not reach a committed record.
    q = t_quantile(0.975, 213)
    assert q == float(f"{q:.12g}")


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_the_p_value_is_two_sided_for_a_gain_and_a_loss(sign: float) -> None:
    # Four equal differences among ten: 2 of the 16 sign patterns of those four are
    # as far from zero as observed, so the exact two-sided p is 0.125.
    assert paired_p([sign] * 4 + [0.0] * 6) == pytest.approx(0.125, abs=0.005)


def test_the_committed_seed_gives_these_draws() -> None:
    # Pins the draws themselves, not only their repeatability: Python guarantees
    # random()'s sequence across versions, not getrandbits()'s.
    assert paired_p([0.1, -0.2, 0.3] * 40) == 70 / (1 + DRAWS)


def test_each_type_and_flip_is_reported(tmp_path: Path) -> None:
    # make_run gives even questions the lookup type; b gains 1.0 on each of them.
    c = compare(
        make_run(tmp_path, "a", [0.0] * 10), make_run(tmp_path, "b", [1.0, 0.0] * 5)
    )
    assert (c.by_type["lookup"].n, c.by_type["lookup"].mean) == (5, 1.0)
    assert c.by_type["table"].mean == 0.0
    assert c.improved == ("Q000", "Q002", "Q004", "Q006", "Q008")
    assert c.regressed == ()


def test_an_incomplete_run_is_refused(tmp_path: Path) -> None:
    a = make_run(tmp_path, "a", [0.0, 1.0])
    b = make_run(tmp_path, "b", [0.0, 1.0])
    run = json.loads((b / "run.json").read_text(encoding="utf-8"))
    (b / "run.json").write_text(
        json.dumps(run | {"status": "running"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="not a complete run"):
        compare(a, b)


def test_the_spread_gives_the_detectable_difference(tmp_path: Path) -> None:
    c = compare(
        make_run(tmp_path, "a", [0.0, 1.0] * 50),
        make_run(tmp_path, "b", [1.0, 0.0] * 50),
    )
    assert c.sd == pytest.approx(statistics.stdev([1.0, -1.0] * 50))
    assert c.mdd == pytest.approx(mdd(c.sd, 100))
    # The interval uses Student's t, not the normal quantile.
    width = 2 * t_quantile(0.975, 99) * c.sd / math.sqrt(100)
    assert c.high - c.low == pytest.approx(width)


def test_main_writes_the_comparison_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runs, out = tmp_path / "runs", tmp_path / "comparisons"
    runs.mkdir()
    make_run(runs, "base", [0.0, 1.0] * 10)
    make_run(runs, "new", [1.0, 1.0] * 10)
    assert main(["base", "new", "--runs", str(runs), "--out", str(out)]) == 0
    record = json.loads((out / "base--new.json").read_text(encoding="utf-8"))
    assert record["a"] == "base" and record["b"] == "new" and record["n"] == 20
    assert "new" in capsys.readouterr().out
