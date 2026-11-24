# Author: Nicola Antonello
import json
from pathlib import Path
from typing import Any

import psycopg

from regulator_graded_rag.bm25 import BM25
from regulator_graded_rag.manifest import Manifest
from regulator_graded_rag.runs import run_retrieval, score_run
from tests.unit.test_runs import item

Conn = psycopg.Connection[tuple[Any, ...]]


def test_a_bm25_run_on_the_real_index(
    db: Conn, manifest: Manifest, test_index: str, tmp_path: Path
) -> None:
    # Three questions about the corpus, written for this test, never taken from a letter.
    items = [
        item(
            "99-0001-Q1",
            "Do the hazardous materials regulations apply to a person who"
            " reconditions a packaging?",
            ("171.1(a)",),
        ),
        item(
            "99-0001-Q2",
            "Must a lithium battery shipped with equipment be protected against"
            " short circuits?",
            ("173.185(c)",),
        ),
        item(
            "99-0002-Q1",
            "Which column of the Hazardous Materials Table gives the special"
            " provisions?",
            ("172.101(h)",),
            "table",
        ),
    ]
    version = str(manifest.version)
    retriever = BM25(db, corpus_version=version, schema=test_index)
    head: dict[str, object] = {
        "corpus_version": version,
        "retriever": "bm25",
        "settings": retriever.settings(),
        "split": "dev",
        "gold": {"version": "f" * 64},
    }
    run = run_retrieval(retriever, items, tmp_path / "r", head)
    text = (tmp_path / "r" / "questions.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.splitlines()]
    assert run["status"] == "complete" and all(len(r["hits"]) == 50 for r in rows)
    assert all(
        [s for _, s in r["hits"]] == sorted((s for _, s in r["hits"]), reverse=True)
        for r in rows
    )
    assert score_run(tmp_path / "r", items, "f" * 64)[0].n == 3  # the row "all"
