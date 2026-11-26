# Author: Nicola Antonello
import json
from pathlib import Path

import pytest

from regulator_graded_rag.compare import (
    compare,
    letter_sums,
    paired_p,
    write_comparison,
)

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "eval" / "runs"
COMPARISONS = REPO / "eval" / "comparisons"
REPORTS = REPO / "docs" / "evaluation"
# The report that quotes each comparison's letter-level check.
LETTER_CHECKS = {
    "2026-11-24-bm25-dev-1--2026-11-25-dense-bge-base-dev-1": (
        "0002-dense-gte-modernbert-against-bm25.md"
    ),
    "2026-11-24-bm25-dev-1--2026-11-25-dense-gte-modernbert-dev-1": (
        "0002-dense-gte-modernbert-against-bm25.md"
    ),
    "2026-11-24-bm25-dev-1--2026-11-26-dense-qwen3-embedding-dev-1": (
        "0003-dense-qwen3-embedding-against-bm25.md"
    ),
    "2026-11-24-bm25-dev-1--2026-11-26-hybrid-rrf-qwen3-embedding-dev-1": (
        "0004-hybrid-rrf-qwen3-embedding-against-bm25.md"
    ),
    "2026-11-24-bm25-dev-1--2026-11-26-hybrid-weighted-qwen3-embedding-dev-1": (
        "0005-hybrid-weighted-qwen3-embedding-against-bm25.md"
    ),
}


def _recall_at_10(run: Path) -> dict[str, float]:
    scores = json.loads((run / "scores.json").read_text(encoding="utf-8"))
    return {row["id"]: row["recall"]["10"] for row in scores["per_question"]}


def _committed() -> list[Path]:
    """The committed comparison records, in name order."""
    return sorted(COMPARISONS.glob("*.json"))


def test_the_committed_comparisons_are_found() -> None:
    # The recompute test below is skipped when it finds no record, so this one fails.
    assert _committed()


@pytest.mark.parametrize("record", _committed(), ids=lambda path: path.stem)
def test_every_committed_comparison_recomputes(record: Path, tmp_path: Path) -> None:
    # A published difference must come back from the two runs it names.
    data = json.loads(record.read_text(encoding="utf-8"))
    recomputed = write_comparison(tmp_path, compare(RUNS / data["a"], RUNS / data["b"]))
    assert recomputed.read_bytes() == record.read_bytes()


@pytest.mark.parametrize(("record", "report"), LETTER_CHECKS.items())
def test_the_reports_letter_level_checks_recompute(record: str, report: str) -> None:
    # A report's letter-level p-value must come back from the two runs, with each
    # letter's questions flipped together, and be printed as the reports print p.
    data = json.loads((COMPARISONS / f"{record}.json").read_text(encoding="utf-8"))
    a, b = (_recall_at_10(RUNS / data[side]) for side in ("a", "b"))
    ids = sorted(a)
    p = paired_p(letter_sums(ids, [b[i] - a[i] for i in ids]))
    assert f"p = {p:.2g}" in (REPORTS / report).read_text(encoding="utf-8")
