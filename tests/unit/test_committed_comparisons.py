# Author: Nicola Antonello
import json
from pathlib import Path

import pytest

from regulator_graded_rag.compare import compare, write_comparison

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "eval" / "runs"
COMPARISONS = REPO / "eval" / "comparisons"


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
