# Author: Nicola Antonello
import json
import math
import statistics
from pathlib import Path

import pytest

from regulator_graded_rag.power import Z_80, Z_975, main, mdd, table


def write_run(folder: Path, split: str, recalls: list[float]) -> Path:
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(json.dumps({"split": split}), encoding="utf-8")
    per_question = [{"id": f"Q{i}", "recall": {"10": r}} for i, r in enumerate(recalls)]
    scores = json.dumps({"per_question": per_question})
    (folder / "scores.json").write_text(scores, encoding="utf-8")
    return folder


def rejects(c: float, delta: float, nu: int, steps: int = 2000) -> float:
    """P(|T| > c) for T = (Z + delta) / sqrt(V / nu), with Z standard normal and V
    chi-square on nu degrees of freedom: the noncentral t, by Simpson's rule over V."""
    phi = statistics.NormalDist().cdf
    h = (nu + 40 * math.sqrt(2 * nu)) / steps
    total = 0.0
    for i in range(1, steps + 1):  # the density is 0 at V = 0
        v = i * h
        weight = 1 if i == steps else (4 if i % 2 else 2)
        log_density = (
            (nu / 2 - 1) * math.log(v)
            - v / 2
            - nu / 2 * math.log(2)
            - math.lgamma(nu / 2)
        )
        s = math.sqrt(v / nu)
        total += (
            weight * (phi(delta - c * s) + phi(-delta - c * s)) * math.exp(log_density)
        )
    return total * h / 3


def test_mdd_follows_the_corrected_formula() -> None:
    assert mdd(0.4, 100) == pytest.approx(
        (Z_975 + Z_80) * 0.4 / math.sqrt(100 - Z_975**2 / 2)
    )


@pytest.mark.parametrize("n", [10, 214])
def test_a_paired_t_test_has_power_0_8_at_the_mdd(n: int) -> None:
    # The exact power, not the normal approximation: without the z**2/2 term a sample
    # of 10 would reach only about 0.70.
    low, high = 1.9, 3.5
    for _ in range(40):
        middle = (low + high) / 2
        low, high = (
            (middle, high) if rejects(middle, 0, n - 1) > 0.05 else (low, middle)
        )
    shift = mdd(1.0, n) * math.sqrt(n)  # the noncentrality when the spread is 1
    assert rejects(low, shift, n - 1) == pytest.approx(0.8, abs=0.01)


def test_a_stronger_correlation_detects_a_smaller_difference() -> None:
    rows = table([0.0, 1.0] * 50)
    assert [r.assumption for r in rows][:4] == [
        "rho=0.0",
        "rho=0.3",
        "rho=0.5",
        "rho=0.7",
    ]
    assert rows[0].mdd > rows[1].mdd > rows[2].mdd > rows[3].mdd


def test_the_spreads_follow_the_correlation_and_the_discordant_share() -> None:
    scores = [0.0, 1.0] * 50
    s = statistics.stdev(scores)
    rows = table(scores)
    assert [r.assumption for r in rows][4:] == [
        "discordant=0.1",
        "discordant=0.2",
        "discordant=0.3",
    ]
    spreads = [math.sqrt(2 * s**2 * (1 - rho)) for rho in (0.0, 0.3, 0.5, 0.7)]
    spreads += [math.sqrt(d) for d in (0.1, 0.2, 0.3)]
    assert [r.sd for r in rows] == pytest.approx(spreads)
    assert [r.mdd for r in rows] == pytest.approx([mdd(sd, 100) for sd in spreads])


def test_main_prints_the_table_and_the_shortfall(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recalls = [0.0, 1.0] * 50
    assert main([str(write_run(tmp_path / "r", "dev", recalls))]) == 0
    out = capsys.readouterr().out
    for row in table(recalls):
        assert f"{row.assumption:<16}{row.sd:>8.3f}{row.mdd:>8.3f}" in out
    assert (
        "answerable dev questions: 100, 20 short of the 120 the design expected" in out
    )


def test_enough_questions_show_no_shortfall(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(write_run(tmp_path / "r", "dev", [0.0, 1.0] * 65))]) == 0
    out = capsys.readouterr().out
    assert "answerable dev questions: 130, no shortfall against the 120" in out


def test_only_a_dev_run_gives_a_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The folder has no scores.json, so the refusal must come before opening one.
    folder = tmp_path / "r"
    folder.mkdir()
    (folder / "run.json").write_text(json.dumps({"split": "heldout"}), encoding="utf-8")
    assert main([str(folder)]) == 1
    assert "not a dev run" in capsys.readouterr().out


def test_a_missing_run_is_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(tmp_path / "2026-11-20-bm25-dev-9")]) == 1
    assert "2026-11-20-bm25-dev-9" in capsys.readouterr().out
