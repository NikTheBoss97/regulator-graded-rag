# Author: Nicola Antonello
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import psycopg
import pytest

from regulator_graded_rag.bm25 import StaleIndex
from regulator_graded_rag.configs import DenseStage
from regulator_graded_rag.dense import Dense
from regulator_graded_rag.embed import embed_stage
from regulator_graded_rag.embeddings import read_header
from regulator_graded_rag.manifest import Manifest

Conn = psycopg.Connection[tuple[Any, ...]]
VECTORS = "rgrvec_dense_test"
STAGE = DenseStage("test/fixture-model", "0123456789abcdef", "a" * 64, "Q: ", 512)


class KeywordEncoder:
    """Stands in for a model: the target passage points one way, every other passage
    another, and the question the target's way."""

    dim = 3

    def __init__(self, target: str) -> None:
        self.target = target
        self.passages_seen = 0
        self.prompts: list[str] = []

    def queries(self, texts: Sequence[str], prompt: str) -> list[list[float]]:
        self.prompts.append(prompt)
        return [[1.0, 0.0, 0.0] for _ in texts]

    def passages(self, texts: Sequence[str]) -> list[list[float]]:
        self.passages_seen += len(texts)
        return [
            [1.0, 0.0, 0.0] if text == self.target else [0.0, 0.0, 1.0]
            for text in texts
        ]

    def too_long(self, texts: Sequence[str]) -> int:
        return sum(len(text) > 1000 for text in texts)

    def runtime(self) -> dict[str, str]:
        return {"gpu": "test GPU", "torch": "2.14.1", "cuda": "12.6"}


@pytest.fixture
def vectors_schema(db: Conn) -> Iterator[str]:
    """A vector schema of the test's own, never the owner's rgrvec."""
    yield VECTORS
    db.execute(f"DROP SCHEMA IF EXISTS {VECTORS} CASCADE")


def test_dense_search_finds_the_nearest_fixture_passage(
    db: Conn, manifest: Manifest, test_index: str, vectors_schema: str, tmp_path: Path
) -> None:
    version = str(manifest.version)
    # The passage the question should find: one whose text no other passage repeats.
    rows = db.execute(f"SELECT id, text FROM {test_index}.passages ORDER BY ordinal")
    texts: dict[str, str] = dict(rows.fetchall())
    counts = Counter(texts.values())
    target = next(pid for pid, text in texts.items() if counts[text] == 1)
    encoder = KeywordEncoder(texts[target])
    # Before any vectors are loaded, the stage refuses and names the command.
    with pytest.raises(StaleIndex, match="regulator_graded_rag.embed"):
        Dense(
            db,
            stage=STAGE,
            corpus_version=version,
            encoder=encoder,
            schema=vectors_schema,
            index_schema=test_index,
        )

    def embed() -> Path:
        return embed_stage(
            db,
            STAGE,
            encoder,
            corpus_version=version,
            folder=tmp_path,
            schema=vectors_schema,
            index_schema=test_index,
        )

    path = embed()
    header = read_header(path)
    assert (header["count"], header["max_length"]) == (len(texts), 512)
    assert header["dtype"] == "float32"
    long_ones = sum(len(text) > 1000 for text in texts.values())
    assert long_ones > 0 and header["truncated"] == long_ones
    dense = Dense(
        db,
        stage=STAGE,
        corpus_version=version,
        encoder=encoder,
        schema=vectors_schema,
        index_schema=test_index,
    )
    hits = dense.search("Which passage?", 3)
    assert hits[0].passage_id == target and hits[0].score == pytest.approx(1.0)
    assert [hit.score for hit in hits[1:]] == pytest.approx([0.0, 0.0], abs=1e-6)
    # The question goes in with the stage's prompt, and the stage names its vectors,
    # their precision and cut passages, read back from the meta table, and its runtime.
    assert encoder.prompts == ["Q: "]
    identity = dense.identity()
    assert {key: identity[key] for key in ("vectors_sha256", "dtype", "truncated")} == {
        "vectors_sha256": header["sha256"],
        "dtype": "float32",
        "truncated": long_ones,
    }
    assert {key: identity[key] for key in ("gpu", "torch", "cuda")} == encoder.runtime()
    # A second embed finds the file and loads it again, computing nothing.
    seen = encoder.passages_seen
    assert embed() == path and encoder.passages_seen == seen
    # Vectors for a corpus the index does not hold are never computed, so no file can
    # claim a version its passages are not from.
    with pytest.raises(ValueError, match="the index holds corpus version"):
        embed_stage(
            db,
            STAGE,
            encoder,
            corpus_version="d" * 64,
            folder=tmp_path / "other",
            schema=vectors_schema,
            index_schema=test_index,
        )
    assert encoder.passages_seen == seen and not (tmp_path / "other").exists()
