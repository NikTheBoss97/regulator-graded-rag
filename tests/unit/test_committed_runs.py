# Author: Nicola Antonello
import json
import shutil
from pathlib import Path

import pytest

from regulator_graded_rag.gold import gold_version, load_items
from regulator_graded_rag.runs import score_run

REPO = Path(__file__).resolve().parents[2]


def _dev_runs() -> list[Path]:
    """The committed dev runs that are complete. Only run files are read here, so a
    held-out run's gold file is never opened."""
    folders = []
    for run_file in sorted((REPO / "eval" / "runs").glob("*/run.json")):
        run = json.loads(run_file.read_text(encoding="utf-8"))
        if run.get("split") == "dev" and run.get("status") == "complete":
            folders.append(run_file.parent)
    return folders


@pytest.mark.parametrize("folder", _dev_runs(), ids=lambda folder: folder.name)
def test_every_committed_dev_run_rescores_to_its_scores(
    folder: Path, tmp_path: Path
) -> None:
    # A published number must come back from the stored hits and the gold file.
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    gold = REPO / run["gold"]["path"]
    version = run["gold"]["version"]
    assert gold_version(gold) == version, f"{gold.name} changed since {folder.name}"
    for name in ("run.json", "questions.jsonl"):
        shutil.copyfile(folder / name, tmp_path / name)
    score_run(tmp_path, load_items(gold), version)
    rescored = (tmp_path / "scores.json").read_bytes()
    assert rescored == (folder / "scores.json").read_bytes()
