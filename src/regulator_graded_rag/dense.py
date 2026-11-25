# Author: Nicola Antonello
"""The dense first stage: a question's nearest passages by embedding (ADR-0009).

The question is embedded with the stage's model and prompt, then compared with every
passage's stored vector by cosine distance, exactly, as embeddings.nearest does. The
stage refuses to search vectors that are missing, made for another corpus version, or
of another dimension than its model's, and names the command that makes them.
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
from regulator_graded_rag.index import SCHEMA

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
        made_for, dim, sha256 = meta
        if made_for != corpus_version:
            raise StaleIndex(
                f"the vectors for {stage.model} hold corpus version {made_for}, not"
                f" {corpus_version}: {EMBED}"
            )
        if dim != encoder.dim:
            raise StaleIndex(
                f"the vectors for {stage.model} have dimension {dim}, but its model"
                f" gives {encoder.dim}: {EMBED}"
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
        self._identity = {
            "vectors_sha256": sha256,
            "server": str(server),
            "pgvector": str(pgvector),
        }

    def identity(self) -> Mapping[str, object]:
        """What a search reads besides its settings: the vectors, by their SHA-256, and
        the server and pgvector release that compute the distances."""
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
