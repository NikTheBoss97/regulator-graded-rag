# Author: Nicola Antonello
"""Index the passages in Postgres with the statistics BM25 needs (ADR-0004, ADR-0005).

Usage: python -m regulator_graded_rag.index [--passages PATH] [--manifest PATH] [--force],
from the repository root, with DATABASE_URL set as in .env.example.

The schema rgr holds the passages in file order and, from Postgres's english text-search
configuration, each passage's term counts (a lexeme's count is its number of positions),
its length in terms, each term's document frequency and the corpus's size and mean
length. It is labelled with the corpus version and rebuilt from scratch, in one
transaction, only when that version changes or --force asks.
Exit code 0 when the index holds the manifest's corpus version, 1 when it cannot.
"""

import argparse
import json
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from regulator_graded_rag.db import connect, database_url
from regulator_graded_rag.manifest import DEFAULT_MANIFEST, Manifest, load_manifest
from regulator_graded_rag.passages import DEFAULT_OUT, version_of
from regulator_graded_rag.review import Record

SCHEMA = "rgr"
CONFIG = "english"

_TABLES = (
    (
        "CREATE TABLE {s}.meta (corpus_version text NOT NULL, config regconfig NOT NULL,"
        " built timestamptz NOT NULL DEFAULT now())"
    ),
    (
        "CREATE TABLE {s}.passages (ordinal integer PRIMARY KEY, id text NOT NULL UNIQUE,"
        " unit text NOT NULL, kind text NOT NULL, text text NOT NULL)"
    ),
    (
        "CREATE TABLE {s}.terms (lexeme text NOT NULL, ordinal integer NOT NULL"
        " REFERENCES {s}.passages, tf integer NOT NULL, PRIMARY KEY (lexeme, ordinal))"
    ),
    (
        "CREATE TABLE {s}.lengths (ordinal integer PRIMARY KEY REFERENCES {s}.passages,"
        " length integer NOT NULL)"
    ),
    "CREATE TABLE {s}.df (lexeme text PRIMARY KEY, df integer NOT NULL)",
    "CREATE TABLE {s}.stats (n double precision NOT NULL, avgdl double precision NOT NULL)",
)
_DERIVED = (
    (
        "INSERT INTO {s}.terms SELECT t.lexeme, p.ordinal, cardinality(t.positions)"
        " FROM {s}.passages p, unnest(to_tsvector(%(config)s::regconfig, p.text)) t"
    ),
    (
        "INSERT INTO {s}.lengths SELECT p.ordinal, coalesce(sum(t.tf), 0)"
        " FROM {s}.passages p LEFT JOIN {s}.terms t USING (ordinal) GROUP BY p.ordinal"
    ),
    "INSERT INTO {s}.df SELECT lexeme, count(*) FROM {s}.terms GROUP BY lexeme",
    "INSERT INTO {s}.stats SELECT count(*), avg(length) FROM {s}.lengths",
)

Conn = psycopg.Connection[tuple[Any, ...]]


def read_passages(path: Path, manifest: Manifest) -> list[Record]:
    """The passages file, refused unless its count and version are the manifest's."""
    with path.open(encoding="utf-8") as file:
        records: list[Record] = [json.loads(line) for line in file if line.strip()]
    version = version_of((r["id"], r["text"]) for r in records)
    if len(records) != manifest.passages or version != manifest.version:
        raise ValueError(
            f"{len(records)} passages with version {version} differ from the manifest"
            f" (count {manifest.passages}, version {manifest.version}):"
            ' run "uv run python -m regulator_graded_rag.passages" first'
        )
    return records


def _one(conn: Conn, query: sql.Composed, params: dict[str, Any] | None = None) -> Any:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return row[0]


def build_index(
    conn: Conn,
    records: Sequence[Record],
    version: str,
    *,
    schema: str = SCHEMA,
    config: str = CONFIG,
) -> Counter[str]:
    """Drop and rebuild the schema in one transaction; the counts of what it holds."""
    s = sql.Identifier(schema)
    params = {"config": config, "version": version}
    with conn.transaction():
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {s} CASCADE").format(s=s))
        conn.execute(sql.SQL("CREATE SCHEMA {s}").format(s=s))
        for statement in _TABLES:
            conn.execute(sql.SQL(statement).format(s=s))
        copy_passages = sql.SQL(
            "COPY {s}.passages (ordinal, id, unit, kind, text) FROM STDIN"
        ).format(s=s)
        with conn.cursor().copy(copy_passages) as copy:
            for ordinal, r in enumerate(records, start=1):
                unit = r["id"].rsplit(":", 1)[0]
                copy.write_row((ordinal, r["id"], unit, r["kind"], r["text"]))
        for statement in _DERIVED:
            conn.execute(sql.SQL(statement).format(s=s), params)
        conn.execute(
            sql.SQL(
                "INSERT INTO {s}.meta (corpus_version, config)"
                " VALUES (%(version)s, %(config)s::regconfig)"
            ).format(s=s),
            params,
        )
        return Counter(
            passages=len(records),
            lexemes=_one(conn, sql.SQL("SELECT count(*) FROM {s}.df").format(s=s)),
            terms=_one(conn, sql.SQL("SELECT count(*) FROM {s}.terms").format(s=s)),
            tokens=_one(
                conn, sql.SQL("SELECT sum(length) FROM {s}.lengths").format(s=s)
            ),
        )


def index_label(conn: Conn, schema: str = SCHEMA) -> tuple[str, str] | None:
    """The corpus version and text-search configuration the schema was built with;
    None when there is no index."""
    exists = conn.execute(
        "SELECT 1 FROM information_schema.tables"
        " WHERE table_schema = %s AND table_name = 'meta'",
        (schema,),
    ).fetchone()
    if exists is None:
        return None
    row = conn.execute(
        sql.SQL("SELECT corpus_version, config::text FROM {s}.meta").format(
            s=sql.Identifier(schema)
        )
    ).fetchone()
    return None if row is None else (str(row[0]), str(row[1]))


def indexed_version(conn: Conn, schema: str = SCHEMA) -> str | None:
    """The corpus version the schema was built from; None when there is no index."""
    label = index_label(conn, schema)
    return None if label is None else label[0]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.index",
        description="Index the passages in Postgres for BM25, when the corpus version"
        " changes.",
    )
    parser.add_argument("--passages", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--force", action="store_true", help="rebuild even when the index is current"
    )
    args = parser.parse_args(argv)
    try:
        url = database_url()
        manifest = load_manifest(args.manifest)
        records = read_passages(args.passages, manifest)
    except (RuntimeError, ValueError) as err:
        print(err)
        return 1
    except FileNotFoundError as err:
        print(
            f'{err.filename} is missing: run "uv run python -m regulator_graded_rag.passages"'
        )
        return 1
    with connect(url) as conn:
        if indexed_version(conn) == manifest.version and not args.force:
            print(f"the index holds corpus version {manifest.version} already")
            return 0
        start = time.monotonic()
        counts = build_index(conn, records, str(manifest.version))
    print(
        f"indexed {counts['passages']} passages, {counts['lexemes']} lexemes,"
        f" {counts['tokens']} tokens in {time.monotonic() - start:.1f}s,"
        f" corpus version {manifest.version}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
