# Author: Nicola Antonello
from typing import Any

import psycopg

from regulator_graded_rag.index import build_index, indexed_version
from regulator_graded_rag.manifest import Manifest
from regulator_graded_rag.review import Record

Conn = psycopg.Connection[tuple[Any, ...]]


def one(db: Conn, query: str) -> tuple[Any, ...]:
    row = db.execute(query).fetchone()
    assert row is not None
    return row


def test_the_index_holds_every_passage(
    db: Conn, manifest: Manifest, test_index: str
) -> None:
    assert one(
        db, f"SELECT count(*), count(DISTINCT unit) FROM {test_index}.passages"
    ) == (13539, 1069)
    assert indexed_version(db, schema=test_index) == manifest.version


def test_every_passage_has_terms_within_postgres_limits(
    db: Conn, test_index: str
) -> None:
    # A tsvector keeps at most 256 positions per lexeme, each at most 16,383; positions
    # also count stop words, so the limit is checked on them, not on lengths.
    assert one(db, f"SELECT min(length) FROM {test_index}.lengths")[0] > 0
    position = one(
        db,
        f"SELECT max(pos) FROM {test_index}.passages p,"
        " unnest(to_tsvector('english', p.text)) t, unnest(t.positions) pos",
    )
    assert position[0] < 16383
    assert one(db, f"SELECT max(tf) FROM {test_index}.terms")[0] < 256


def test_the_build_leaves_statistics_for_the_planner(db: Conn, test_index: str) -> None:
    # A fresh one-row stats table is never auto-analyzed, and without its statistics the
    # planner chose a search plan about five times slower (measured on 2026-11-15).
    for table in ("passages", "terms", "lengths", "df", "stats"):
        rows = one(
            db,
            f"SELECT reltuples FROM pg_class WHERE oid = '{test_index}.{table}'::regclass",
        )
        assert rows[0] >= 0, f"{table} was never analyzed"
    assert one(
        db, f"SELECT reltuples FROM pg_class WHERE oid = '{test_index}.stats'::regclass"
    ) == (1,)


def test_a_rebuild_gives_the_same_statistics(
    db: Conn, manifest: Manifest, index_records: list[Record], test_index: str
) -> None:
    digest = (
        "SELECT md5(string_agg(lexeme || ':' || df, ',' ORDER BY lexeme)) FROM {}.df"
    )
    build_index(db, index_records, str(manifest.version), schema="rgr_test_again")
    try:
        assert one(db, digest.format(test_index)) == one(
            db, digest.format("rgr_test_again")
        )
    finally:
        db.execute("DROP SCHEMA rgr_test_again CASCADE")


def test_terms_are_counted_from_their_positions(db: Conn) -> None:
    record: Record = {
        "id": "171.1:1",
        "kind": "text",
        "source": "t.xml",
        "page": 1,
        "text": "Cylinders and cylinder valves",
    }
    build_index(db, [record], "c" * 64, schema="rgr_test_counts")
    try:
        terms: dict[str, int] = dict(
            db.execute("SELECT lexeme, tf FROM rgr_test_counts.terms").fetchall()
        )
        assert terms == {"cylind": 2, "valv": 1}
        assert one(db, "SELECT length FROM rgr_test_counts.lengths") == (3,)
    finally:
        db.execute("DROP SCHEMA rgr_test_counts CASCADE")
