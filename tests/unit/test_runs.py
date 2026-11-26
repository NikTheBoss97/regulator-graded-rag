# Author: Nicola Antonello
import json
import subprocess
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pytest

from regulator_graded_rag.bm25 import Hit
from regulator_graded_rag.cache import CACHE_ROOT
from regulator_graded_rag.configs import ConfigError, load_config
from regulator_graded_rag.gold import Item, gold_version
from regulator_graded_rag.metrics import DEPTH
from regulator_graded_rag.runs import (
    ResumeMismatch,
    RunExists,
    cache_root,
    freeze,
    frozen_matches,
    header,
    main,
    run_config,
    run_name,
    run_retrieval,
    run_tuned,
    score_run,
)
from regulator_graded_rag.tuning import assign_folds

BASELINE = Path("eval/configs/bm25.toml")


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
VERSION = "g" * 64
HEAD: dict[str, object] = {
    "stage": "retrieval",
    "retriever": "fake",
    "settings": {"k": 1.0},
    "split": "dev",
    "gold": {"version": VERSION},
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
    assert score_run(tmp_path / "r", [*ITEMS, unanswerable], VERSION)[0].n == 3


def test_an_empty_ranking_scores_zero(tmp_path: Path) -> None:
    # A question with no indexed word finds nothing, and still counts, at 0.
    run_retrieval(Fake(empty_on="two"), ITEMS, tmp_path / "r", HEAD)
    assert lines(tmp_path / "r")[1]["hits"] == []
    overall = score_run(tmp_path / "r", ITEMS, VERSION)[0]
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
    first = score_run(tmp_path / "r", ITEMS, VERSION)
    data = (tmp_path / "r" / "scores.json").read_bytes()
    assert score_run(tmp_path / "r", ITEMS, VERSION) == first
    assert (tmp_path / "r" / "scores.json").read_bytes() == data
    assert [(s.type, s.n, s.recall[10]) for s in first] == [
        ("all", 3, 2 / 3),
        ("lookup", 3, 2 / 3),
    ]


def test_scoring_refuses_a_run_of_other_items(tmp_path: Path) -> None:
    run_retrieval(Fake(), ITEMS[:2], tmp_path / "r", HEAD)
    with pytest.raises(ValueError, match="differ"):
        score_run(tmp_path / "r", ITEMS, VERSION)


def test_scores_name_their_gold_version(tmp_path: Path) -> None:
    run_retrieval(Fake(), ITEMS, tmp_path / "r", HEAD)
    score_run(tmp_path / "r", ITEMS, VERSION)
    scores = json.loads((tmp_path / "r" / "scores.json").read_text(encoding="utf-8"))
    assert scores["gold_version"] == VERSION


def test_scoring_refuses_another_gold_version(tmp_path: Path) -> None:
    # Scores name the gold set they were computed against, so it must be the run's.
    run_retrieval(Fake(), ITEMS, tmp_path / "r", HEAD)
    with pytest.raises(ValueError, match="gold set"):
        score_run(tmp_path / "r", ITEMS, "h" * 64)
    assert not (tmp_path / "r" / "scores.json").exists()


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


def test_the_header_names_the_code_tree(tmp_path: Path) -> None:
    # A rebase merge gives the commit a new ID but keeps its tree (ADR-0012).
    gold = tmp_path / "items.jsonl"
    gold.write_text("", encoding="utf-8")
    git = header(Fake(), gold, [], "dev", "c" * 64, tmp_path, Path("."))["git"]
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()
    assert isinstance(git, dict) and git["tree"] == tree


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


def test_a_config_changed_after_its_run_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A config that produced a run is never edited: a change gets a new name (ADR-0023).
    monkeypatch.delenv("DATABASE_URL", raising=False)
    gold = tmp_path / "items.jsonl"
    gold.write_text(json.dumps(asdict(ITEMS[0])) + "\n", encoding="utf-8")
    config = tmp_path / "bm25.toml"
    config.write_bytes(BASELINE.read_bytes())
    runs = tmp_path / "runs"
    (runs / "2026-11-25-bm25-dev-1").mkdir(parents=True)
    # Another config's run, with its own contents, never stops this one.
    (runs / "2026-11-25-other-dev-1").mkdir()
    other = {"retriever": "other", "status": "complete", "config": {"sha256": "1" * 64}}
    other_file = runs / "2026-11-25-other-dev-1" / "run.json"
    other_file.write_text(json.dumps(other), encoding="utf-8")
    argv = ["--split", "dev", "--gold", str(gold), "--runs", str(runs)]

    def ran(sha256: str) -> str:
        run = {"retriever": "bm25", "status": "complete", "config": {"sha256": sha256}}
        run_file = runs / "2026-11-25-bm25-dev-1" / "run.json"
        run_file.write_text(json.dumps(run), encoding="utf-8")
        assert main([*argv, "--config", str(config)]) == 1
        return capsys.readouterr().out

    # The same config again is no change: without a database it stops there instead.
    unchanged = ran(load_config(config).sha256)
    assert "DATABASE_URL" in unchanged and "new name" not in unchanged
    changed = ran("0" * 64)
    assert "2026-11-25-bm25-dev-1" in changed and "needs a new name" in changed


def test_the_config_path_is_recorded_without_the_home_folder(tmp_path: Path) -> None:
    # Run records are committed, and an absolute path names the user's home folder.
    repo = tmp_path / "repo"
    inside = repo / "eval" / "configs" / "bm25.toml"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(BASELINE.read_bytes())
    outside = tmp_path / "bm25.toml"
    outside.write_bytes(BASELINE.read_bytes())
    paths = [
        run_config(path, tmp_path / "runs", repo).path for path in (inside, outside)
    ]
    assert paths == ["eval/configs/bm25.toml", "bm25.toml"]


def test_the_header_holds_the_whole_config(tmp_path: Path) -> None:
    config = load_config(BASELINE)
    gold = tmp_path / "items.jsonl"
    gold.write_text("", encoding="utf-8")
    head = header(Fake(), gold, [], "dev", "c" * 64, tmp_path, Path("."), config=config)
    assert head["config"] == {
        "path": "eval/configs/bm25.toml",
        "sha256": config.sha256,
        "text": config.text,
    }
    assert "config" not in header(
        Fake(), gold, [], "dev", "c" * 64, tmp_path, Path(".")
    )


def test_a_config_is_not_mixed_with_the_bm25_flags(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The config sets k1 and b itself, so a flag beside it would be ignored unseen; 0
    # is a value too.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for flag in ("--k1", "--b"):
        assert main(["--split", "dev", "--config", str(BASELINE), flag, "0"]) == 1
        assert f"so {flag} cannot go with it" in capsys.readouterr().out


def test_a_retriever_that_reports_compute_seconds_is_timed_by_them(
    tmp_path: Path,
) -> None:
    # An answer from the pipeline's cache takes microseconds, so the run records the
    # seconds its stages took to compute it; any other retriever is timed by the clock.
    class Cached(Fake):
        def compute_seconds(self) -> float:
            return 0.5

    for name, retriever in (("cached", Cached()), ("timed", Fake())):
        clock = iter([0.0, 1.0, 1.0, 3.0, 3.0, 6.0]).__next__
        run_retrieval(retriever, ITEMS, tmp_path / name, HEAD, clock=clock)
    assert [x["seconds"] for x in lines(tmp_path / "cached")] == [0.5, 0.5, 0.5]
    assert [x["seconds"] for x in lines(tmp_path / "timed")] == [1.0, 2.0, 3.0]


def test_each_split_keeps_its_own_stage_cache() -> None:
    # Held-out hit lists stay apart from dev's, under a heldout/ path.
    assert cache_root("dev") == CACHE_ROOT / "dev"
    assert cache_root("heldout") == CACHE_ROOT / "heldout"


TUNED = (
    '[[first_stage]]\nkind = "bm25"\nk1 = 1.2\nb = 0.75\n'
    '[[first_stage]]\nkind = "dense"\nmodel = "m"\nrevision = "r"\n'
    f'weights_sha256 = "{"a" * 64}"\nquery_prompt = ""\nmax_length = 512\n'
    '[fusion]\nmethod = "rrf"\nk = [10, 60]\n[cv]\nfolds = 2\nseed = "s"\n'
)
TUNED_ITEMS = [
    *ITEMS,
    item("U-1", "four", (), "unanswerable"),
    item("U-2", "five", (), "unanswerable"),
]


class ByFold:
    """A grid value's retriever that finds the cited section only for the given items;
    elsewhere it returns a passage of its own, so a line shows which value wrote it."""

    name = "tuned"

    def __init__(self, finds: set[str], miss: str) -> None:
        self.finds = finds
        self.miss = miss

    def settings(self) -> dict[str, str | float]:
        return {"config_file": "tuned.toml"}

    def search(self, question: str, k: int) -> list[Hit]:
        found = next(i for i in TUNED_ITEMS if i.question == question)
        if found.id in self.finds:
            return [Hit(f"{found.evidence[0].split('(')[0]}:1", 1.0)]
        return [Hit(self.miss, 1.0)]


def tuned_config(tmp_path: Path) -> Path:
    path = tmp_path / "tuned.toml"
    path.write_text('name = "tuned"\n' + TUNED, encoding="utf-8", newline="\n")
    return path


def tuned_run(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[float, ByFold], dict[str, int]]:
    fold_of = assign_folds(TUNED_ITEMS, "s", 2)

    def fold(n: int) -> set[str]:
        return {i for i, f in fold_of.items() if f == n}

    # Value 10 finds fold 1's sections and value 60 fold 0's, so each fold should get
    # the value that is worse on its own questions.
    retrievers = {10.0: ByFold(fold(1), "910.1:1"), 60.0: ByFold(fold(0), "960.1:1")}
    config = load_config(tuned_config(tmp_path))
    run = run_tuned(config, retrievers, TUNED_ITEMS, tmp_path / "r", HEAD)
    return run, retrievers, fold_of


def test_a_tuned_run_searches_unanswerable_items_with_their_folds_value(
    tmp_path: Path,
) -> None:
    run, retrievers, fold_of = tuned_run(tmp_path)
    tuning = run["tuning"]
    assert isinstance(tuning, dict)
    written = {line["id"]: line["hits"] for line in lines(tmp_path / "r")}
    assert set(written) == {i.id for i in TUNED_ITEMS}
    for found in TUNED_ITEMS:
        value = tuning["folds"][str(fold_of[found.id])]
        hits = retrievers[value].search(found.question, DEPTH)
        assert written[found.id] == [[hit.passage_id, hit.score] for hit in hits]
    # The two unanswerable items sit in different folds, which chose different values.
    assert written["U-1"] != written["U-2"]


def test_a_tuned_run_records_its_folds_and_final_value(tmp_path: Path) -> None:
    run, _, _ = tuned_run(tmp_path)
    expected = {
        "setting": "k",
        "grid": [10.0, 60.0],
        "seed": "s",
        "folds": {"0": 10.0, "1": 60.0},
        "all_dev": 60.0,
    }
    assert run["tuning"] == expected
    saved = json.loads((tmp_path / "r" / "run.json").read_text(encoding="utf-8"))
    assert saved["tuning"] == expected and saved["status"] == "complete"


def test_a_tuned_run_starts_again_rather_than_resume(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runs = tmp_path / "runs"
    (runs / "stopped").mkdir(parents=True)
    (runs / "stopped" / "run.json").write_text("{}", encoding="utf-8")
    argv = ["--split", "dev", "--config", str(tuned_config(tmp_path))]
    assert main([*argv, "--resume", "stopped", "--runs", str(runs)]) == 1
    assert "starts again" in capsys.readouterr().out


def test_tuning_never_touches_the_held_out_split(tmp_path: Path) -> None:
    # A tuned run on held-out items would choose its values on them (ADR-0014): the
    # held-out run uses the config fixed at the value chosen on dev.
    never = {10.0: ByFold(set(), "910.1:1"), 60.0: ByFold(set(), "960.1:1")}
    config = load_config(tuned_config(tmp_path))
    with pytest.raises(ConfigError, match="held-out"):
        run_tuned(
            config, never, TUNED_ITEMS, tmp_path / "r", {**HEAD, "split": "heldout"}
        )
    assert not (tmp_path / "r").exists()
