# Author: Nicola Antonello
from pathlib import Path

from regulator_graded_rag.report import render, results

REPO = Path(__file__).resolve().parents[2]


def test_the_readme_results_are_generated_from_the_run_records() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert render(readme, results(REPO / "eval" / "runs")) == readme, (
        "the README results differ from the run records:"
        ' run "uv run python -m regulator_graded_rag.report"'
    )
