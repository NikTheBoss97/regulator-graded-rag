# Author: Nicola Antonello
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pytest

from regulator_graded_rag.bm25 import Hit
from regulator_graded_rag.gold import Item, gold_version
from regulator_graded_rag.runs import (
    ResumeMismatch,
    RunExists,
    freeze,
    frozen_matches,
    header,
    main,
    run_name,
    run_retrieval,
    score_run,
)


class Fake:
    name = "fake"

    def __init__(self, fail_on: str | None = None, empty_on: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_on = fail_on
        self.empty_on = empty_on

    def settings(self) -> dict[str, str | float]:
        return {"k": 1.0}

    def search(self, question: str, k: int) -> list[Hit]:
        self.calls.append(question)
        if question == self.fail_on:
            raise RuntimeError("laptop closed")
        if question == self.empty_on:
            return []
        return [Hit("171.1:1", 2.0), Hit("173.185:3", 1.0)][:k]


def item(
    id_: str, question: str, evidence: tuple[str, ...], type_: str = "lookup"
) -> Item:
    return Item(
        id_,
        question,
        type_,
        "yes",
        evidence,
        "2020-03-02",
        "https://web.archive.org/x",
        "dev",
        "PHMSA",
        "owner",
        "2025",
    )


ITEMS = [
    item("99-0001-Q1", "one", ("171.1",)),
    item("99-0001-Q2", "two", ("173.185(a)",)),
    item("99-0002-Q1", "three", ("175.10",)),
]
HEAD: dict[str, object] = {
    "stage": "retrieval",
    "retriever": "fake",
    "settings": {"k": 1.0},
    "split": "dev",
    "gold": {"version": "g" * 64},
    "corpus_version": "c" * 64,
    "git": {"commit": "a" * 40, "dirty": False},
    "machine": {"platform": "Windows-11", "python": "3.14.7", "processor": "x86"},
}


def lines(folder: Path) -> list[dict[str, object]]:
    return [
        json.loads(x)
        for x in (folder / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_a_run_writes_a_line_per_question_and_completes(tmp_path: Path) -> None:
    run = run_retrieval(Fake(), ITEMS, tmp_path / "r", HEAD)
    assert run["status"] == "complete" and run["questions"] == 3
    assert [x["id"] for x in lines(tmp_path / "r")] == [
        "99-0001-Q1",
        "99-0001-Q2",
        "99-0002-Q1",
    ]
    assert lines(tmp_path / "r")[0]["hits"] == [["171.1:1", 2.0], ["173.185:3", 1.0]]


def test_a_stopped_run_resumes_without_repeating_questions(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="laptop closed"):
        run_retrieval(Fake(fail_on="two"), ITEMS, tmp_path / "r", HEAD)
    run_file = tmp_path / "r" / "run.json"
    assert json.loads(run_file.read_text(encoding="utf-8"))["status"] == "running"
    again = Fake()
    run = run_retrieval(again, ITEMS, tmp_path / "r", HEAD)
    assert again.calls == ["two", "three"] and len(lines(tmp_path / "r")) == 3
    assert run["questions"] == 3


def test_every_item_is_searched_and_only_answerable_ones_are_scored(
    tmp_path: Path,
) -> None:
    # Phase 4's end-to-end run reuses the hits of unanswerable items too.
    unanswerable = Item(
        "U-1",
        "four",
        "unanswerable",
        "",
        ("searched",),
        "",
        "",
        "dev",
        "o",
        "o",
        "2025",
    )
    fake = Fake()
    run_retrieval(fake, [*ITEMS, unanswerable], tmp_path / "r", HEAD)
    assert fake.calls == ["one", "two", "three", "four"]
    assert score_run(tmp_path / "r", [*ITEMS, unanswerable])[0].n == 3


def test_an_empty_ranking_scores_zero(tmp_path: Path) -> None:
    # A question with no indexed word finds nothing, and still counts, at 0.
    run_retrieval(Fake(empty_on="two"), ITEMS, tmp_path / "r", HEAD)
    assert lines(tmp_path / "r")[1]["hits"] == []
    overall = score_run(tmp_path / "r", ITEMS)[0]
    assert (overall.n, overall.recall[10], overall.mrr) == (3, 1 / 3, 1 / 3)


def test_a_partial_last_line_is_redone(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        run_retrieval(Fake(fail_on="three"), ITEMS, tmp_path / "r", HEAD)
    questions = tmp_path / "r" / "questions.jsonl"
    with questions.open("a", encoding="utf-8", newline="\n") as f:
        f.write('{"id": "99-0002-Q1", "hi')
    again = Fake()
    run_retrieval(again, ITEMS, tmp_path / "r", HEAD)
    assert again.calls == ["three"]
    assert [x["id"] for x in lines(tmp_path / "r")][-1] == "99-0002-Q1"


def test_a_cut_off_line_is_redone_even_when_it_parses(tmp_path: Path) -> None:
    # A line is whole only once its newline is written, so a cut that falls just
    # before the newline must not count the question as searched.
    with pytest.raises(RuntimeError):
        run_retrieval(Fake(fail_on="three"), ITEMS, tmp_path / "r", HEAD)
    questions = tmp_path / "r" / "questions.jsonl"
    with questions.open("a", encoding="utf-8", newline="\n") as f:
        f.write('{"id": "99-0002-Q1", "type": "lookup", "hits": [], "seconds": 0.0}')
    again = Fake()
    run_retrieval(again, ITEMS, tmp_path / "r", HEAD)
    assert again.calls == ["three"] and lines(tmp_path / "r")[-1]["hits"] != []


@pytest.mark.parametrize(
    ("field", "change"),
    [
        ("corpus_version", {"corpus_version": "d" * 64}),
        ("gold.version", {"gold": {"version": "h" * 64}}),
        ("split", {"split": "heldout"}),
        ("retriever", {"retriever": "other"}),
        ("settings", {"settings": {"k": 2.0}}),
        # The code and the machine, so every question of a run ran under the commit
        # its record names, and its times are comparable.
        ("git.commit", {"git": {"commit": "b" * 40, "dirty": False}}),
        ("git.dirty", {"git": {"commit": "a" * 40, "dirty": True}}),
        ("machine", {"machine": {"platform": "Darwin", "python": "3.14.7"}}),
    ],
)
def test_resuming_with_other_settings_is_refused(
    tmp_path: Path, field: str, change: dict[str, object]
) -> None:
    with pytest.raises(RuntimeError):
        run_retrieval(Fake(fail_on="two"), ITEMS, tmp_path / "r", HEAD)
    with pytest.raises(ResumeMismatch, match=field):
        run_retrieval(Fake(), ITEMS, tmp_path / "r", HEAD | change)


def test_a_complete_run_is_not_run_again(tmp_path: Path) -> None:
    run_retrieval(Fake(), ITEMS, tmp_path / "r", HEAD)
    with pytest.raises(RunExists):
        run_retrieval(Fake(), ITEMS, tmp_path / "r", HEAD)


def test_progress_counts_the_questions_searched(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        run_retrieval(Fake(fail_on="two"), ITEMS, tmp_path / "r", HEAD)
    seen: list[tuple[int, int, str]] = []
    run_retrieval(
        Fake(),
        ITEMS,
        tmp_path / "r",
        HEAD,
        progress=lambda i, n, id_: seen.append((i, n, id_)),
    )
    assert seen == [(2, 3, "99-0001-Q2"), (3, 3, "99-0002-Q1")]


def test_scores_are_recomputed_from_the_stored_hits(tmp_path: Path) -> None:
    run_retrieval(Fake(), ITEMS, tmp_path / "r", HEAD)
    first = score_run(tmp_path / "r", ITEMS)
    data = (tmp_path / "r" / "scores.json").read_bytes()
    assert score_run(tmp_path / "r", ITEMS) == first
    assert (tmp_path / "r" / "scores.json").read_bytes() == data
    assert [(s.type, s.n, s.recall[10]) for s in first] == [
        ("all", 3, 2 / 3),
        ("lookup", 3, 2 / 3),
    ]


def test_scoring_refuses_a_run_of_other_items(tmp_path: Path) -> None:
    run_retrieval(Fake(), ITEMS[:2], tmp_path / "r", HEAD)
    with pytest.raises(ValueError, match="differ"):
        score_run(tmp_path / "r", ITEMS)


def test_the_header_counts_spending_and_held_out_runs(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    earlier = {
        "a": {"status": "complete", "split": "dev", "cost_usd": 0.25},
        "b": {"status": "complete", "split": "heldout", "cost_usd": 0.5},
        "c": {"status": "running", "split": "heldout", "cost_usd": 4.0},
    }
    for name, run in earlier.items():
        (root / name).mkdir(parents=True)
        (root / name / "run.json").write_text(json.dumps(run), encoding="utf-8")
    gold = tmp_path / "items.jsonl"
    gold.write_text(json.dumps(asdict(ITEMS[0])) + "\n", encoding="utf-8")
    unanswerable = Item(
        "U-1", "q", "unanswerable", "", ("searched",), "", "", "dev", "o", "o", "2025"
    )
    items = [*ITEMS, unanswerable]
    dev = header(Fake(), gold, items, "dev", "c" * 64, root, Path("."))
    heldout = header(Fake(), gold, items, "heldout", "c" * 64, root, Path("."))
    assert {k: dev[k] for k in ("stage", "retriever", "settings", "split")} == {
        "stage": "retrieval",
        "retriever": "fake",
        "settings": {"k": 1.0},
        "split": "dev",
    }
    assert dev["gold"] == {
        "path": "items.jsonl",
        "version": gold_version(gold),
        "items": 4,
        "answerable": 3,
    }
    assert (dev["cost_usd"], dev["spent_usd"]) == (0.0, 0.75)
    assert (dev["heldout_runs"], heldout["heldout_runs"]) == (0, 3)
    git = dev["git"]
    assert isinstance(git, dict) and len(git["commit"]) == 40
    assert isinstance(git["dirty"], bool)


def test_the_gold_path_is_recorded_without_the_home_folder(tmp_path: Path) -> None:
    # Run records are committed, and an absolute path names the user's home folder.
    def path(given: Path) -> object:
        gold = header(Fake(), given, [], "dev", "c" * 64, tmp_path, Path("."))["gold"]
        assert isinstance(gold, dict)
        return gold["path"]

    inside = Path("tests/unit/test_runs.py")
    assert [path(inside), path(inside.resolve())] == [inside.as_posix()] * 2
    outside = tmp_path / "items.jsonl"
    outside.write_text("", encoding="utf-8")
    assert path(outside) == "items.jsonl"


def test_held_out_runs_need_the_owners_flag() -> None:
    assert main(["--split", "heldout"]) == 2


def test_resuming_a_run_that_does_not_exist_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Without a database the command stops anyway, so the message must name the run.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    gold = tmp_path / "items.jsonl"
    gold.write_text(json.dumps(asdict(ITEMS[0])) + "\n", encoding="utf-8")
    runs = tmp_path / "runs"
    argv = ["--split", "dev", "--gold", str(gold), "--runs", str(runs)]
    assert main([*argv, "--resume", "2026-11-20-bm25-dev-9"]) == 1
    assert "2026-11-20-bm25-dev-9" in capsys.readouterr().out
    assert not runs.exists()


def test_items_of_another_split_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Otherwise --gold could run held-out items as a dev run, uncounted (ADR-0014).
    monkeypatch.delenv("DATABASE_URL", raising=False)
    gold = tmp_path / "items.jsonl"
    labelled = asdict(ITEMS[0]) | {"split": "heldout"}
    gold.write_text(json.dumps(labelled) + "\n", encoding="utf-8")
    runs = tmp_path / "runs"
    assert main(["--split", "dev", "--gold", str(gold), "--runs", str(runs)]) == 1
    assert "99-0001-Q1" in capsys.readouterr().out and not runs.exists()


def test_a_gold_file_without_items_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    gold = tmp_path / "items.jsonl"
    gold.write_text("", encoding="utf-8")
    runs = tmp_path / "runs"
    assert main(["--split", "dev", "--gold", str(gold), "--runs", str(runs)]) == 1
    assert "holds no items" in capsys.readouterr().out and not runs.exists()


def test_run_names_count_up() -> None:
    assert (
        run_name(date(2026, 11, 20), "bm25", "dev", ["2026-11-20-bm25-dev-1"])
        == "2026-11-20-bm25-dev-2"
    )


def test_frozen_items_must_match_their_checksum(tmp_path: Path) -> None:
    items = tmp_path / "items.jsonl"
    items.write_text('{"id": "U-1"}\n', encoding="utf-8", newline="\n")
    frozen = tmp_path / "heldout-items.sha256"
    assert not frozen_matches(items, frozen)
    freeze(items, frozen, 1)
    assert frozen_matches(items, frozen)
    assert frozen.read_text(encoding="utf-8").split()[0] == gold_version(items)
    items.write_bytes(items.read_bytes().replace(b"U-1", b"U-2"))
    assert not frozen_matches(items, frozen)
