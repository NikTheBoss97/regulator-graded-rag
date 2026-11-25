# Author: Nicola Antonello
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest

from regulator_graded_rag import dense as dense_module
from regulator_graded_rag import pipeline as pipeline_module
from regulator_graded_rag.bm25 import Conn, Hit, StaleIndex
from regulator_graded_rag.cache import StageCache
from regulator_graded_rag.configs import DenseStage, load_config
from regulator_graded_rag.dense import Dense
from regulator_graded_rag.embeddings import model_key
from regulator_graded_rag.pipeline import build

SHA = "a" * 64
CORPUS = "c" * 64
STAGE = DenseStage(
    "BAAI/bge-base-en-v1.5",
    "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a",
    SHA,
    "Represent this sentence for searching relevant passages: ",
    512,
)
CONFIG = f"""[[first_stage]]
kind = "dense"
model = "{STAGE.model}"
revision = "{STAGE.revision}"
weights_sha256 = "{SHA}"
query_prompt = "{STAGE.query_prompt}"
max_length = 512
"""


class FakeEncoder:
    """Stands in for a model: three dimensions, the question always [1, 0, 0]."""

    dim = 3

    def queries(self, texts: Sequence[str], prompt: str) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    def passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0, 0.0, 1.0] for _ in texts]

    def too_long(self, texts: Sequence[str]) -> int:
        return 0


@pytest.mark.parametrize(
    ("meta", "match"),
    [
        (None, "no vectors"),
        (("d" * 64, 3, SHA), "corpus version"),
        ((CORPUS, 768, SHA), "dimension"),
    ],
)
def test_dense_refuses_a_stale_vector_table(
    monkeypatch: pytest.MonkeyPatch, meta: tuple[str, int, str] | None, match: str
) -> None:
    # Vectors of another corpus, or of a model of another size, rank the wrong passages.
    monkeypatch.setattr(dense_module, "vectors_meta", lambda conn, key, schema: meta)
    with pytest.raises(StaleIndex, match=match) as raised:
        Dense(
            cast(Conn, None), stage=STAGE, corpus_version=CORPUS, encoder=FakeEncoder()
        )
    assert "regulator_graded_rag.embed" in str(raised.value)


def test_dense_refuses_an_index_of_another_corpus_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The vectors are keyed by passage ordinal, so over an index rebuilt for another
    # corpus every vector would name the wrong passage, as BM25 already refuses.
    monkeypatch.setattr(
        dense_module, "vectors_meta", lambda conn, key, schema: (CORPUS, 3, SHA)
    )
    monkeypatch.setattr(dense_module, "indexed_version", lambda conn, schema: "d" * 64)
    with pytest.raises(StaleIndex, match="the index holds corpus version") as raised:
        Dense(
            cast(Conn, None), stage=STAGE, corpus_version=CORPUS, encoder=FakeEncoder()
        )
    assert "regulator_graded_rag.index" in str(raised.value)


def test_a_dense_config_builds_a_dense_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made: list[tuple[object, ...]] = []

    class FakeDense:
        def __init__(
            self,
            conn: Conn,
            *,
            stage: DenseStage,
            corpus_version: str,
            encoder: FakeEncoder,
            index_schema: str,
        ) -> None:
            made.append((stage, corpus_version, encoder, index_schema))

        def identity(self) -> dict[str, object]:
            return {"vectors_sha256": "v" * 64}

        def search(self, question: str, k: int) -> list[Hit]:
            return [Hit("171.1:1", 0.9)][:k]

    monkeypatch.setattr(pipeline_module, "Dense", FakeDense)
    monkeypatch.setattr(pipeline_module, "code_digest", lambda: "s" * 64)
    path = tmp_path / "dense-bge.toml"
    path.write_text(f'name = "dense-bge"\n{CONFIG}', encoding="utf-8")
    config = load_config(path)
    encoder = FakeEncoder()
    pipeline = build(
        config,
        cast(Conn, None),
        corpus_version=CORPUS,
        cache=StageCache(tmp_path / "cache"),
        encoders={model_key(STAGE.model, STAGE.revision): encoder},
    )
    assert made == [(config.first[0], CORPUS, encoder, "rgr")]
    # The run record names the exact embeddings the stage searched.
    assert pipeline.settings()["vectors_sha256"] == "v" * 64
    assert pipeline.search("Is it?", 1) == [Hit("171.1:1", 0.9)]
