# Author: Nicola Antonello
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import psycopg

from regulator_graded_rag.bm25 import BM25, Hit
from regulator_graded_rag.cache import StageCache
from regulator_graded_rag.configs import load_config
from regulator_graded_rag.gold import gold_version, load_items
from regulator_graded_rag.index import build_index
from regulator_graded_rag.manifest import Manifest
from regulator_graded_rag.metrics import DEPTH
from regulator_graded_rag.pipeline import Pipeline, build, code_digest
from regulator_graded_rag.review import Record

Conn = psycopg.Connection[tuple[Any, ...]]
REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / "eval" / "runs" / "2026-11-24-bm25-dev-1"


def test_the_bm25_config_reproduces_the_committed_baseline(
    db: Conn, manifest: Manifest, test_index: str, tmp_path: Path
) -> None:
    # The baseline was run before configs existed, so this is what lets bm25.toml stand
    # for it without a rerun (ADR-0023).
    run = json.loads((BASELINE / "run.json").read_text(encoding="utf-8"))
    gold = REPO / run["gold"]["path"]
    # Controls: the same corpus and the same items, or equal hits would prove nothing.
    assert run["corpus_version"] == str(manifest.version)
    assert gold_version(gold) == run["gold"]["version"]
    text = (BASELINE / "questions.jsonl").read_text(encoding="utf-8")
    committed = {
        line["id"]: line["hits"] for line in map(json.loads, text.splitlines())
    }
    items = load_items(gold)
    assert sorted(committed) == sorted(item.id for item in items)
    config = load_config(REPO / "eval" / "configs" / "bm25.toml")
    version = str(manifest.version)
    pipeline = build(
        config,
        db,
        corpus_version=version,
        cache=StageCache(tmp_path),
        schema=test_index,
    )
    for item in items:
        hits = pipeline.search(item.question, DEPTH)
        assert [[h.passage_id, h.score] for h in hits] == committed[item.id], item.id

    # The cache file gives the real scores back: a pipeline over it never searches.
    bm25 = BM25(db, corpus_version=version, schema=test_index)

    class Refuses:
        def identity(self) -> Mapping[str, object]:
            return bm25.identity()

        def search(self, question: str, k: int) -> list[Hit]:
            raise AssertionError(f"searched again for {question!r}")

    again = Pipeline(
        config,
        [Refuses()],
        corpus_version=version,
        cache=StageCache(tmp_path),
        code=code_digest(),
    )
    for item in items:
        hits = again.search(item.question, DEPTH)
        assert [[h.passage_id, h.score] for h in hits] == committed[item.id], item.id


def test_a_rebuilt_index_gives_bm25_a_new_identity(
    db: Conn, manifest: Manifest, test_index: str, index_records: list[Record]
) -> None:
    # The identity joins the cache key, so hits from an index built before never come
    # back after a rebuild; the server, the same both times, is part of it too.
    version = str(manifest.version)
    before = BM25(db, corpus_version=version, schema=test_index).identity()
    build_index(db, index_records, version, schema=test_index)
    after = BM25(db, corpus_version=version, schema=test_index).identity()
    assert before.keys() == after.keys() == {"index_built", "server"}
    assert before["server"] == after["server"] and before != after
