# Author: Nicola Antonello
"""Compare two runs on the same questions (ADR-0012, ADR-0024).

Usage: python -m regulator_graded_rag.compare A B [--runs DIR] [--out DIR], from the
repository root. A and B are run folders under eval/runs.

On the answerable questions both runs scored, it gives the mean difference in section
recall@10 (B minus A) with a 95% t-interval, and the two-sided p-value of a paired
randomization test: 100,000 random sign flips of the per-question differences, drawn from
a committed seed, so the same draws can be regenerated. Results by question type are
description only: the test is on the main number. It also gives the spread of the
differences and the minimum detectable difference it implies (ADR-0020), and the
questions that improved and regressed. It writes the comparison record to
eval/comparisons/<A>--<B>.json and prints a Markdown table.
Exit code 0 when compared, 1 when the runs cannot be compared.
"""

import argparse
import json
import math
import os
import random
import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Any

from regulator_graded_rag.power import mdd

PAIRED_SEED = "phase-3-paired-2026-11-25"
DRAWS = 100_000
RUNS = Path("eval/runs")
COMPARISONS = Path("eval/comparisons")


@dataclass(frozen=True)
class TypeDiff:
    n: int
    mean: float
    low: float
    high: float


@dataclass(frozen=True)
class Comparison:
    a: str
    b: str
    n: int
    mean: float
    low: float
    high: float
    p: float
    sd: float
    mdd: float
    by_type: dict[str, TypeDiff]
    improved: tuple[str, ...]
    regressed: tuple[str, ...]
    draws: int
    seed: str


def _t_cdf(x: float, df: int, steps: int = 2000) -> float:
    """Student's t distribution function at x >= 0, by Simpson's rule over the density."""
    scale = math.exp(math.lgamma((df + 1) / 2) - math.lgamma(df / 2))
    scale /= math.sqrt(df * math.pi)
    h = x / steps
    area = 0.0
    for i in range(steps + 1):
        t = i * h
        weight = 1 if i in (0, steps) else (4 if i % 2 else 2)
        area += weight * (1 + t * t / df) ** (-(df + 1) / 2)
    return 0.5 + scale * area * h / 3


@cache
def t_quantile(p: float, df: int) -> float:
    """The p quantile of Student's t on df degrees of freedom, by bisection."""
    if not 0 < p < 1:
        raise ValueError(f"a quantile needs 0 < p < 1, not {p}")
    if p < 0.5:
        return -t_quantile(1 - p, df)
    low, high = 0.0, 1.0
    while _t_cdf(high, df) < p:
        low, high = high, 2 * high
    for _ in range(60):
        middle = (low + high) / 2
        low, high = (middle, high) if _t_cdf(middle, df) < p else (low, middle)
    # Rounded to 12 significant digits, far below any reported precision, so that a
    # math library's last bit cannot change a committed record.
    return float(f"{(low + high) / 2:.12g}")


def paired_p(
    diffs: Sequence[float], draws: int = DRAWS, seed: str = PAIRED_SEED
) -> float:
    """The two-sided p-value of a paired randomization test: the share of random sign
    flips whose sum is at least as far from zero as the observed one, with the observed
    arrangement counted, so p is never 0. Bit i of a draw flips difference i; blocks of
    8 differences are summed from a table of their 256 flip patterns."""
    total = math.fsum(diffs)
    observed = abs(total)
    blocks = [diffs[i : i + 8] for i in range(0, len(diffs), 8)]
    tables = [
        [
            math.fsum(d for j, d in enumerate(block) if pattern >> j & 1)
            for pattern in range(256)
        ]
        for block in blocks
    ]
    rng = random.Random(seed)
    hits = 0
    for _ in range(draws):
        flips = rng.getrandbits(len(diffs)).to_bytes(len(blocks), "little")
        flipped = 0.0
        for table, pattern in zip(tables, flips, strict=True):
            flipped += table[pattern]
        if abs(total - 2 * flipped) >= observed - 1e-9:
            hits += 1
    return (1 + hits) / (1 + draws)


def _interval(diffs: Sequence[float]) -> tuple[float, float, float, float]:
    """The mean, its 95% t-interval and the standard deviation of the differences."""
    mean = math.fsum(diffs) / len(diffs)
    if len(diffs) < 2:
        return mean, mean, mean, 0.0
    sd = statistics.stdev(diffs)
    half = t_quantile(0.975, len(diffs) - 1) * sd / math.sqrt(len(diffs))
    return mean, mean - half, mean + half, sd


def _dev_run(folder: Path) -> dict[str, Any]:
    """A complete dev run's file. Anything else is refused before its scores are opened:
    held-out results come with the owner's single held-out run (ADR-0014)."""
    run: dict[str, Any] = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    if run.get("status") != "complete":
        raise ValueError(f"{folder.name} is not a complete run")
    if run.get("split") != "dev":
        raise ValueError(
            f"{folder.name} is a {run.get('split')} run: only dev runs are compared"
        )
    return run


def _scores(folder: Path) -> dict[str, tuple[str, float]]:
    """A run's recall@10 per scored question, with the question's type."""
    scores_file = folder / "scores.json"
    if not scores_file.exists():
        raise ValueError(f"{folder.name} has no scores.json: score it first")
    scores = json.loads(scores_file.read_text(encoding="utf-8"))
    return {
        row["id"]: (row["type"], float(row["recall"]["10"]))
        for row in scores["per_question"]
    }


def compare(a: Path, b: Path) -> Comparison:
    """B against A on the answerable questions both scored; refused unless both are
    complete dev runs on the same corpus and gold set."""
    run_a, run_b = _dev_run(a), _dev_run(b)
    for field, key in (
        ("corpus version", ("corpus_version",)),
        ("gold set version", ("gold", "version")),
    ):
        values = []
        for run in (run_a, run_b):
            value: Any = run
            for part in key:
                value = value.get(part) if isinstance(value, dict) else None
            values.append(value)
        if values[0] != values[1]:
            raise ValueError(
                f"{a.name} and {b.name} differ in {field} ({values[0]} against"
                f" {values[1]}): results compare only on the same versions"
            )
    rows_a, rows_b = _scores(a), _scores(b)
    if sorted(rows_a) != sorted(rows_b):
        raise ValueError(f"{a.name} and {b.name} scored different questions")
    ids = sorted(rows_a)
    if len(ids) < 2:
        raise ValueError("a comparison needs at least two scored questions")
    diffs = [rows_b[i][1] - rows_a[i][1] for i in ids]
    mean, low, high, sd = _interval(diffs)
    by_type: dict[str, list[float]] = {}
    for item_id, diff in zip(ids, diffs, strict=True):
        by_type.setdefault(rows_a[item_id][0], []).append(diff)
    return Comparison(
        a=a.name,
        b=b.name,
        n=len(ids),
        mean=mean,
        low=low,
        high=high,
        p=paired_p(diffs),
        sd=sd,
        mdd=mdd(sd, len(ids)),
        by_type={
            kind: TypeDiff(len(values), *_interval(values)[:3])
            for kind, values in sorted(by_type.items())
        },
        improved=tuple(i for i, d in zip(ids, diffs, strict=True) if d > 0),
        regressed=tuple(i for i, d in zip(ids, diffs, strict=True) if d < 0),
        draws=DRAWS,
        seed=PAIRED_SEED,
    )


def write_comparison(root: Path, c: Comparison) -> Path:
    """The comparison record, sorted and indented with LF, written whole."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{c.a}--{c.b}.json"
    part = path.with_name(path.name + ".part")
    text = json.dumps(asdict(c), indent=2, sort_keys=True) + "\n"
    part.write_text(text, encoding="utf-8", newline="\n")
    os.replace(part, path)
    return path


def markdown(c: Comparison) -> str:
    """The comparison as a Markdown table, for an experiment's report."""
    rows = [
        f"**{c.b} against {c.a}**, section recall@10 on {c.n} answerable questions",
        "",
        "| Questions | n | Difference | 95% interval |",
        "|---|---:|---:|---|",
        f"| all | {c.n} | {c.mean:+.3f} | [{c.low:+.3f}, {c.high:+.3f}] |",
    ]
    for kind, t in c.by_type.items():
        rows.append(
            f"| {kind} | {t.n} | {t.mean:+.3f} | [{t.low:+.3f}, {t.high:+.3f}] |"
        )
    rows += [
        "",
        (
            f"Paired randomization test: p = {c.p:.4g} ({c.draws:,} sign flips)."
            f" Spread of the differences {c.sd:.3f}, so the minimum detectable"
            f" difference at power 0.8 is {c.mdd:.3f}. Improved: {len(c.improved)};"
            f" regressed: {len(c.regressed)}."
        ),
    ]
    return "\n".join(rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.compare",
        description="Compare two runs with a paired randomization test.",
    )
    parser.add_argument("a", help="the baseline run's folder name")
    parser.add_argument("b", help="the compared run's folder name")
    parser.add_argument("--runs", type=Path, default=RUNS)
    parser.add_argument("--out", type=Path, default=COMPARISONS)
    args = parser.parse_args(argv)
    try:
        c = compare(args.runs / args.a, args.runs / args.b)
    except FileNotFoundError as err:
        print(f"{Path(str(err.filename)).as_posix()} is missing")
        return 1
    except ValueError as err:
        print(err)
        return 1
    path = write_comparison(args.out, c)
    print(markdown(c))
    print(f"written to {path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
