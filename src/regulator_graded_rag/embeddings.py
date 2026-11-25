# Author: Nicola Antonello
"""Passage embeddings for exact vector search (ADR-0009).

A model's passage vectors are computed once, on the Windows laptop, and saved as raw
little-endian float32 rows, one per passage in the index's order, so row i belongs to
the passage with ordinal i + 1. A JSON sidecar, <file>.json, names the model, its
revision, the corpus version, the count, the dimension, how many passages were longer
than the model's input, and the raw file's SHA-256. The file holds no pickle and needs
no numpy to read.

Loading a file fills a pgvector table, <schema>.<model key>, keyed by passage ordinal,
and the model's row in <schema>.meta, in one transaction. A file is refused when its
SHA-256, corpus version, model, revision or row count does not match, since a row too
many or too few would put every vector on the wrong passage. Search is exact: Postgres
compares the question with every passage, with no approximate index, and breaks ties
by ordinal, as BM25 does.
"""

import array
import hashlib
import json
import os
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from psycopg import sql

from regulator_graded_rag.bm25 import Conn, Hit
from regulator_graded_rag.index import SCHEMA, indexed_version

VECTORS = "rgrvec"

_META = """
CREATE TABLE IF NOT EXISTS {s}.meta (
  model_key text PRIMARY KEY,
  model text NOT NULL,
  revision text NOT NULL,
  corpus_version text NOT NULL,
  count integer NOT NULL,
  dim integer NOT NULL,
  sha256 text NOT NULL,
  loaded timestamptz NOT NULL DEFAULT now()
)
"""

_NEAREST = """
SELECT p.id, 1 - (v.embedding <=> %(query)s::vector) AS score
FROM {vs}.{key} v
JOIN {s}.passages p USING (ordinal)
ORDER BY v.embedding <=> %(query)s::vector, v.ordinal
LIMIT %(k)s
"""


class Encoder(Protocol):
    """A model that turns text into L2-normalized vectors."""

    dim: int

    def queries(self, texts: Sequence[str], prompt: str) -> list[list[float]]: ...

    def passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    def too_long(self, texts: Sequence[str]) -> int:
        """How many texts hold more tokens than the model reads."""
        ...


def model_key(model: str, revision: str) -> str:
    """A model at a revision as a table name: lowercase, every other character an
    underscore, then the revision's first 8 characters."""
    return re.sub(r"[^a-z0-9]", "_", f"{model}_{revision[:8]}".lower())


def _sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".json")


def _write_whole(path: Path, data: bytes) -> None:
    """Write through a .part file and a rename, so a cut-off write leaves no half file."""
    part = path.with_name(path.name + ".part")
    part.write_bytes(data)
    os.replace(part, path)


def write_vectors(
    path: Path, vectors: Sequence[Sequence[float]], header: Mapping[str, object]
) -> str:
    """Write the rows as little-endian float32, and the header with the count, the
    dimension and the rows' SHA-256 as <path>.json; return the SHA-256."""
    dims = {len(row) for row in vectors}
    if len(dims) != 1:
        raise ValueError("vectors need one dimension, shared by every row")
    rows = array.array("f", (x for row in vectors for x in row))
    if sys.byteorder != "little":
        rows.byteswap()
    data = rows.tobytes()
    sha256 = hashlib.sha256(data).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_whole(path, data)
    full = {**header, "count": len(vectors), "dim": dims.pop(), "sha256": sha256}
    text = json.dumps(full, indent=2, sort_keys=True) + "\n"
    _write_whole(_sidecar(path), text.encode("utf-8"))
    return sha256


def read_header(path: Path) -> dict[str, Any]:
    """The vectors file's sidecar."""
    header: dict[str, Any] = json.loads(_sidecar(path).read_text(encoding="utf-8"))
    return header


def _checked(path: Path) -> tuple[dict[str, Any], array.array[float]]:
    """The header and the rows' numbers, refused unless the file matches the header's
    SHA-256 and holds exactly its count of rows."""
    header = read_header(path)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != header["sha256"]:
        raise ValueError(
            f"{path.name} does not match the SHA-256 its header records: compute it"
            " again"
        )
    count, dim = int(header["count"]), int(header["dim"])
    if len(data) != count * dim * 4:
        raise ValueError(
            f"{path.name} holds {len(data) // 4} numbers, not {count} rows of {dim}"
        )
    numbers = array.array("f")
    numbers.frombytes(data)
    if sys.byteorder != "little":
        numbers.byteswap()
    return header, numbers


def read_vectors(path: Path) -> tuple[dict[str, Any], list[list[float]]]:
    """The header and the rows, refused unless they match (see _checked)."""
    header, numbers = _checked(path)
    dim = int(header["dim"])
    return header, [numbers[i : i + dim].tolist() for i in range(0, len(numbers), dim)]


def _text(vector: Sequence[float]) -> str:
    """A vector as pgvector reads it. A float32 value printed as its shortest double
    reads back as the same float32."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def _rows(numbers: array.array[float], dim: int) -> Iterator[tuple[int, str]]:
    for i in range(0, len(numbers), dim):
        yield i // dim + 1, _text(numbers[i : i + dim])


def load_vectors(
    conn: Conn,
    path: Path,
    *,
    model: str,
    revision: str,
    corpus_version: str,
    schema: str = VECTORS,
    index_schema: str = SCHEMA,
) -> None:
    """Load the file into <schema>.<model key>, refused unless it holds this model at
    this revision, for this corpus version, one row per passage of the index."""
    header, numbers = _checked(path)
    if header["corpus_version"] != corpus_version:
        raise ValueError(
            f"{path.name} holds vectors of corpus version {header['corpus_version']},"
            f" not {corpus_version}: delete {path.as_posix()} and embed again"
        )
    if (header["model"], header["revision"]) != (model, revision):
        raise ValueError(
            f"{path.name} holds model {header['model']} at revision"
            f" {header['revision']}, not {model} at revision {revision}"
        )
    indexed = indexed_version(conn, index_schema)
    if indexed != corpus_version:
        raise ValueError(
            f"the index holds corpus version {indexed}, not {corpus_version}:"
            ' run "uv run python -m regulator_graded_rag.index" first'
        )
    s, i = sql.Identifier(schema), sql.Identifier(index_schema)
    found = conn.execute(sql.SQL("SELECT count(*) FROM {i}.passages").format(i=i))
    passages = int(next(iter(found.fetchone() or (0,))))
    if int(header["count"]) != passages:
        raise ValueError(
            f"{path.name} holds {header['count']} rows, but the index holds"
            f" {passages} passages"
        )
    key = model_key(model, revision)
    table = sql.Identifier(schema, key)
    dim = int(header["dim"])
    with conn.transaction():
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {s}").format(s=s))
        conn.execute(sql.SQL(_META).format(s=s))
        conn.execute(sql.SQL("DROP TABLE IF EXISTS {t}").format(t=table))
        conn.execute(
            sql.SQL(
                "CREATE TABLE {t} (ordinal integer PRIMARY KEY,"
                " embedding vector({dim}) NOT NULL)"
            ).format(t=table, dim=sql.Literal(dim))
        )
        copy = sql.SQL("COPY {t} (ordinal, embedding) FROM STDIN").format(t=table)
        with conn.cursor().copy(copy) as rows:
            for row_ in _rows(numbers, dim):
                rows.write_row(row_)
        conn.execute(
            sql.SQL("DELETE FROM {s}.meta WHERE model_key = %s").format(s=s), (key,)
        )
        conn.execute(
            sql.SQL(
                "INSERT INTO {s}.meta"
                " (model_key, model, revision, corpus_version, count, dim, sha256)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)"
            ).format(s=s),
            (key, model, revision, corpus_version, passages, dim, header["sha256"]),
        )


def vectors_meta(
    conn: Conn, key: str, schema: str = VECTORS
) -> tuple[str, int, str] | None:
    """The corpus version, dimension and SHA-256 of the model's loaded vectors; None
    when none are loaded."""
    found = conn.execute("SELECT to_regclass(%s)", (f"{schema}.meta",)).fetchone()
    if found is None or found[0] is None:
        return None
    row = conn.execute(
        sql.SQL(
            "SELECT corpus_version, dim, sha256 FROM {s}.meta WHERE model_key = %s"
        ).format(s=sql.Identifier(schema)),
        (key,),
    ).fetchone()
    return None if row is None else (str(row[0]), int(row[1]), str(row[2]))


def nearest(
    conn: Conn,
    query: Sequence[float],
    k: int,
    *,
    key: str,
    schema: str = VECTORS,
    index_schema: str = SCHEMA,
) -> list[Hit]:
    """The k passages nearest the query vector by cosine distance, compared with every
    passage; the score is 1 - distance, and ties go to the lower ordinal."""
    query_text = sql.SQL(_NEAREST).format(
        vs=sql.Identifier(schema),
        key=sql.Identifier(key),
        s=sql.Identifier(index_schema),
    )
    rows = conn.execute(query_text, {"query": _text(query), "k": k}).fetchall()
    return [Hit(passage_id, float(score)) for passage_id, score in rows]
