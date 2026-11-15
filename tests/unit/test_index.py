# Author: Nicola Antonello
import json
from dataclasses import replace
from pathlib import Path

import pytest

from regulator_graded_rag.db import database_url
from regulator_graded_rag.index import read_passages
from regulator_graded_rag.manifest import Manifest
from regulator_graded_rag.passages import version_of
from regulator_graded_rag.review import Record


def test_passages_that_differ_from_the_manifest_are_refused(tmp_path: Path) -> None:
    rows: list[Record] = [
        {
            "id": "171.1:1",
            "kind": "text",
            "source": "a.xml",
            "page": 1,
            "text": "§ 171.1 A.\nRule.",
        }
    ]
    path = tmp_path / "passages.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    version = version_of((r["id"], r["text"]) for r in rows)
    manifest = Manifest("2025", "2025-10-01", (), 1, version)
    assert [r["id"] for r in read_passages(path, manifest)] == ["171.1:1"]
    with pytest.raises(ValueError, match="differ from the manifest"):
        read_passages(path, replace(manifest, version="0" * 64))


def test_without_a_database_url_the_message_says_how_to_start_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="docker compose up -d --wait"):
        database_url()
