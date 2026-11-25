# Author: Nicola Antonello
import json
from pathlib import Path

from regulator_graded_rag.bm25 import Hit
from regulator_graded_rag.cache import Entry, StageCache, source_digest, stage_key


def test_a_put_is_read_back_after_reopening(tmp_path: Path) -> None:
    # The seconds the stage took come back too: an answer read from the cache still
    # costs what it cost to compute.
    hits = [Hit("171.1:1", 2.5), Hit("172.101:3", 1.0)]
    StageCache(tmp_path).put("k1", "Is it?", hits, 0.125)
    assert StageCache(tmp_path).get("k1", "Is it?") == Entry(hits, 0.125)


def test_the_cache_key_changes_with_the_source(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "a.py").write_text("x = 1\n", encoding="utf-8")
    before = source_digest(package)
    # A key does not depend on the order its parts are given in.
    assert stage_key({"stage": "bm25", "source": before}) == stage_key(
        {"source": before, "stage": "bm25"}
    )
    (package / "a.py").write_text("x = 2\n", encoding="utf-8")
    after = source_digest(package)
    assert before != after
    assert stage_key({"stage": "bm25", "source": before}) != stage_key(
        {"stage": "bm25", "source": after}
    )


def test_a_missing_entry_is_none(tmp_path: Path) -> None:
    cache = StageCache(tmp_path)
    assert cache.get("k1", "Is it?") is None
    cache.put("k1", "Is it?", [Hit("a:1", 1.0)], 0.5)
    assert cache.get("k1", "Another?") is None
    assert cache.get("k2", "Is it?") is None


def test_a_cut_off_cache_file_is_ignored(tmp_path: Path) -> None:
    StageCache(tmp_path).put("k1", "Q1", [Hit("a:1", 1.0)], 0.5)
    with (tmp_path / "k1.jsonl").open("a", encoding="utf-8", newline="\n") as file:
        file.write('{"question": "')
    # A put after a crash must not glue its line onto the cut-off one.
    StageCache(tmp_path).put("k1", "Q2", [Hit("b:1", 2.0)], 0.25)
    reopened = StageCache(tmp_path)
    assert reopened.get("k1", "Q1") == Entry([Hit("a:1", 1.0)], 0.5)
    assert reopened.get("k1", "Q2") == Entry([Hit("b:1", 2.0)], 0.25)


def test_cache_lines_are_written_with_sorted_keys(tmp_path: Path) -> None:
    StageCache(tmp_path).put("k1", "Q1", [Hit("a:1", 1.0)], 0.5)
    line = (tmp_path / "k1.jsonl").read_text(encoding="utf-8").splitlines()[0]
    assert line == json.dumps(json.loads(line), sort_keys=True)
