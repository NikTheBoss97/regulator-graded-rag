# Author: Nicola Antonello
import json
from pathlib import Path

import pytest

from regulator_graded_rag.report import (
    EMPTY,
    END,
    START,
    load_runs,
    main,
    render,
    results,
    table,
)

RUN: dict[str, object] = {
    "status": "complete",
    "retriever": "bm25",
    "settings": {"k1": 1.2, "b": 0.75},
    "split": "dev",
    "corpus_version": "c" * 64,
    "gold": {"version": "g" * 64, "answerable": 3},
    "seconds": {"median": 0.012},
}
SUMMARY = [
    {
        "type": "all",
        "n": 3,
        "recall": {"5": 0.5, "10": 2 / 3, "20": 2 / 3, "50": 1.0},
        "mrr": 0.5,
        "ndcg10": 0.6,
    }
]


def write_run(
    root: Path,
    name: str,
    changes: dict[str, object] | None = None,
    summary: list[dict[str, object]] | None = None,
) -> None:
    folder = root / name
    folder.mkdir()
    run = RUN | (changes or {})
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    scores = {"per_question": [], "summary": SUMMARY if summary is None else summary}
    (folder / "scores.json").write_text(json.dumps(scores), encoding="utf-8")


def test_a_config_run_links_its_config_instead_of_its_checksums(
    tmp_path: Path,
) -> None:
    # A config run's settings are its file's path and SHA-256s, which would fill the
    # README's first screen; the committed file holds every setting.
    config_run: dict[str, object] = {
        "retriever": "dense-x",
        "settings": {
            "config_file": "eval/configs/dense-x.toml",
            "config_sha256": "a" * 64,
            "vectors_sha256": "b" * 64,
        },
        "config": {"path": "eval/configs/dense-x.toml", "sha256": "a" * 64},
    }
    write_run(tmp_path, "2026-11-25-dense-x-dev-1", config_run)
    write_run(tmp_path, "2026-11-24-bm25-dev-1")
    block = results(tmp_path)
    assert "| [dense-x.toml](eval/configs/dense-x.toml) |" in block
    assert "a" * 64 not in block and "b" * 64 not in block
    assert "| k1=1.2, b=0.75 |" in block


def test_runs_on_other_gold_sets_get_blocks_of_their_own(tmp_path: Path) -> None:
    # Results are compared only on the same corpus and gold set.
    write_run(tmp_path, "2026-11-20-bm25-dev-1")
    changes: dict[str, object] = {"gold": {"version": "h" * 64, "answerable": 4}}
    write_run(tmp_path, "2026-11-20-bm25-dev-2", changes)
    block = results(tmp_path)
    assert block.count("**Dev, ") == 2
    assert "gold set hhhhhhhh…, 4 answerable questions" in block


def test_a_held_out_block_counts_every_held_out_run(tmp_path: Path) -> None:
    # ADR-0014: every look at the held-out split counts, a stopped one included.
    write_run(tmp_path, "2026-11-20-bm25-heldout-1", {"split": "heldout"})
    stopped = tmp_path / "2026-11-21-bm25-heldout-2"
    stopped.mkdir()
    run = {"status": "running", "split": "heldout", "heldout_runs": 2}
    (stopped / "run.json").write_text(json.dumps(run), encoding="utf-8")
    title = (
        "**Held-out, corpus cccccccc…, gold set gggggggg…, 3 answerable questions,"
        " held-out runs: 2**"
    )
    assert title in results(tmp_path)


def test_a_run_with_nothing_scored_keeps_its_row(tmp_path: Path) -> None:
    write_run(tmp_path, "2026-11-20-bm25-dev-1", summary=[])
    assert "| — | — | — | — | — | — | 0.012 |" in results(tmp_path)


def test_render_replaces_only_the_block() -> None:
    readme = f"# Title\n\n{START}\nold\n{END}\n\nAfter.\n"
    assert render(readme, "new") == f"# Title\n\n{START}\nnew\n{END}\n\nAfter.\n"
    with pytest.raises(ValueError, match="markers"):
        render("# Title\n", "new")


def test_no_run_gives_the_empty_line() -> None:
    assert table([]) == EMPTY


def test_a_run_gives_a_row_under_its_versions(tmp_path: Path) -> None:
    folder = tmp_path / "2026-11-20-bm25-dev-1"
    folder.mkdir()
    run = {
        "name": folder.name,
        "status": "complete",
        "retriever": "bm25",
        "settings": {"k1": 1.2, "b": 0.75},
        "split": "dev",
        "corpus_version": "c" * 64,
        "gold": {"version": "g" * 64, "answerable": 3},
        "seconds": {"median": 0.012},
    }
    summary = [
        {
            "type": "all",
            "n": 3,
            "recall": {"5": 0.5, "10": 2 / 3, "20": 2 / 3, "50": 1.0},
            "mrr": 0.5,
            "ndcg10": 0.6,
        }
    ]
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    (folder / "scores.json").write_text(
        json.dumps({"per_question": [], "summary": summary}), encoding="utf-8"
    )
    block = table(load_runs(tmp_path))
    assert "corpus cccccccc…, gold set gggggggg…, 3 answerable questions" in block
    assert "| 0.667 | 0.500 | 0.667 | 1.000 | 0.500 | 0.600 |" in block
    assert "k1=1.2, b=0.75" in block


def test_check_reports_a_readme_that_differs_and_writing_fixes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    readme = Path("README.md")
    readme.write_text(f"{START}\nedited by hand\n{END}\n", encoding="utf-8")
    assert main(["--check"]) == 1
    assert "edited by hand" in readme.read_text(encoding="utf-8")
    assert main([]) == 0 and main(["--check"]) == 0
    assert readme.read_text(encoding="utf-8") == f"{START}\n{EMPTY}\n{END}\n"
