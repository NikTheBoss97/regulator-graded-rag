# Author: Nicola Antonello
from typing import Any

from psycopg import Connection


def test_postgres_is_version_18(conn: Connection[tuple[Any, ...]]) -> None:
    row = conn.execute("SELECT current_setting('server_version_num')::int").fetchone()
    assert row is not None and row[0] // 10000 == 18


def test_pgvector_computes_an_exact_distance(conn: Connection[tuple[Any, ...]]) -> None:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    row = conn.execute("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector").fetchone()
    assert row is not None and row[0] == 1.0
