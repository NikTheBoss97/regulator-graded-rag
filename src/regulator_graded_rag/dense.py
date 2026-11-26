# Author: Nicola Antonello
"""The dense first stage: a question's nearest passages by embedding (ADR-0009).

The question is embedded with the stage's model and prompt, then compared with every
passage's stored vector by cosine distance, exactly, as embeddings.nearest does. The
stage refuses to search vectors that are missing, made for another corpus version, of
another dimension than its model's, or with another precision or input length than its
config states, and names the command that makes them. It also
refuses an index of another corpus version, as BM25 does: the vectors are keyed by
passage ordinal, so over another corpus's passages each would name the wrong one.
"""

from collections.abc import Mapping

from regulator_graded_rag.bm25 import Conn, Hit, StaleIndex
from regulator_graded_rag.configs import DenseStage
from regulator_graded_rag.embeddings import (
    VECTORS,
    Encoder,
    model_key,
    nearest,
    vectors_meta,
)
from regulator_graded_rag.index import SCHEMA, indexed_version

EMBED = (
    'run "uv run --group models --env-file .env python -m regulator_graded_rag.embed'
    ' --config <config>"'
)


class Dense:
    """A dense stage over one model's loaded vectors."""

    def __init__(
        self,
        conn: Conn,
        *,
        stage: DenseStage,
        corpus_version: str,
        encoder: Encoder,
        schema: str = VECTORS,
        index_schema: str = SCHEMA,
    ) -> None:
        key = model_key(stage.model, stage.revision)
        meta = vectors_meta(conn, key, schema)
        if meta is None:
            raise StaleIndex(
                f"no vectors for {stage.model} at {stage.revision}: {EMBED}"
            )
        if meta.corpus_version != corpus_version:
            raise StaleIndex(
                f"the vectors for {stage.model} hold corpus version"
                f" {meta.corpus_version}, not {corpus_version}: {EMBED}"
            )
        if meta.dim != encoder.dim:
            raise StaleIndex(
                f"the vectors for {stage.model} have dimension {meta.dim}, but its"
                f" model gives {encoder.dim}: {EMBED}"
            )
        if meta.dtype != stage.dtype:
            raise StaleIndex(
                f"the vectors for {stage.model} were made with dtype {meta.dtype}, not"
                f" {stage.dtype}: {EMBED}"
            )
        if meta.max_length != stage.max_length:
            raise StaleIndex(
                f"the vectors for {stage.model} were made with max_length"
                f" {meta.max_length}, not {stage.max_length}: {EMBED}"
            )
        indexed = indexed_version(conn, index_schema)
        if indexed != corpus_version:
            raise StaleIndex(
                f"the index holds corpus version {indexed}, not {corpus_version}:"
                ' run "uv run python -m regulator_graded_rag.index"'
            )
        row = conn.execute(
            "SELECT version(),"
            " (SELECT extversion FROM pg_extension WHERE extname = 'vector')"
        ).fetchone()
        server, pgvector = row if row is not None else ("", "")
        self._conn = conn
        self._stage = stage
        self._encoder = encoder
        self._key = key
        self._schema = schema
        self._index_schema = index_schema
        self._identity: dict[str, object] = {
            "vectors_sha256": meta.sha256,
            "dtype": meta.dtype,
            "truncated": meta.truncated,
            "server": str(server),
            "pgvector": str(pgvector),
            **encoder.runtime(),
        }

    def identity(self) -> Mapping[str, object]:
        """What a search reads besides its settings: the vectors, by their SHA-256, with
        the precision they were made in and the count of passages cut to the input
        length; the server and pgvector release that compute the distances; and the
        device, and torch's and CUDA's versions, that embed the question."""
        return self._identity

    def search(self, question: str, k: int) -> list[Hit]:
        """The k nearest passages, best first, by cosine similarity to the question."""
        [vector] = self._encoder.queries([question], self._stage.query_prompt)
        return nearest(
            self._conn,
            vector,
            k,
            key=self._key,
            schema=self._schema,
            index_schema=self._index_schema,
        )
