# Author: Nicola Antonello
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from regulator_graded_rag.embeddings import (
    VectorsMeta,
    load_vectors,
    model_key,
    nearest,
    read_header,
    vectors_meta,
    write_vectors,
)
from regulator_graded_rag.manifest import Manifest

Conn = psycopg.Connection[tuple[Any, ...]]
VECTORS = "rgrvec_test"
MODEL, REVISION = "test/fixture-model", "0123456789abcdef"
KEY = model_key(MODEL, REVISION)


@pytest.fixture
def vectors_schema(db: Conn) -> Iterator[str]:
    """A vector schema of the test's own, never the owner's rgrvec."""
    yield VECTORS
    db.execute(f"DROP SCHEMA IF EXISTS {VECTORS} CASCADE")


def passage_count(db: Conn, schema: str) -> int:
    row = db.execute(f"SELECT count(*) FROM {schema}.passages").fetchone()
    assert row is not None
    return int(row[0])


def fixture_file(
    folder: Path, count: int, corpus_version: str, special: dict[int, list[float]]
) -> Path:
    """One vector per passage, in ordinal order: [0, 0, 1] but for the special ones."""
    rows = [special.get(ordinal, [0.0, 0.0, 1.0]) for ordinal in range(1, count + 1)]
    path = folder / f"{KEY}.f32"
    header = {
        "model": MODEL,
        "revision": REVISION,
        "corpus_version": corpus_version,
        "max_length": 512,
        "dtype": "float32",
        "truncated": 2,
    }
    write_vectors(path, rows, header)
    return path


def test_loading_refuses_a_mismatched_file(
    db: Conn, manifest: Manifest, test_index: str, vectors_schema: str, tmp_path: Path
) -> None:
    version = str(manifest.version)
    count = passage_count(db, test_index)

    def load(
        path: Path,
        revision: str = REVISION,
        corpus_version: str = version,
        model: str = MODEL,
    ) -> None:
        load_vectors(
            db,
            path,
            model=model,
            revision=revision,
            corpus_version=corpus_version,
            schema=vectors_schema,
            index_schema=test_index,
        )

    # One row short would shift every vector onto the wrong passage.
    with pytest.raises(ValueError, match="passages"):
        load(fixture_file(tmp_path / "short", count - 1, version, {}))
    # Vectors computed for an older corpus, loaded against today's index.
    old = fixture_file(tmp_path / "old", count, "d" * 64, {})
    with pytest.raises(ValueError, match="holds vectors of corpus version"):
        load(old)
    # A corpus version the index does not hold, though the file names it.
    with pytest.raises(ValueError, match="the index holds corpus version"):
        load(old, corpus_version="d" * 64)
    good = fixture_file(tmp_path / "good", count, version, {})
    with pytest.raises(ValueError, match="revision"):
        load(good, revision="fedcba9876543210")
    # Another model's vectors, at the same revision label, are refused too.
    with pytest.raises(ValueError, match="not other/model at revision"):
        load(good, model="other/model")
    raw = bytearray(good.read_bytes())
    raw[-1] ^= 0x01
    good.write_bytes(bytes(raw))
    with pytest.raises(ValueError, match="SHA-256"):
        load(good)
    # A refused file leaves nothing behind.
    found = db.execute("SELECT to_regclass(%s)", (f"{vectors_schema}.{KEY}",))
    assert found.fetchone() == (None,)


def test_exact_search_orders_by_cosine_then_ordinal(
    db: Conn, manifest: Manifest, test_index: str, vectors_schema: str, tmp_path: Path
) -> None:
    version = str(manifest.version)
    count = passage_count(db, test_index)
    # Ordinal 7 matches the question exactly; ordinals 3 and 5 tie behind it.
    special = {7: [1.0, 0.0, 0.0], 3: [0.6, 0.8, 0.0], 5: [0.6, 0.8, 0.0]}
    path = fixture_file(tmp_path, count, version, special)
    load_vectors(
        db,
        path,
        model=MODEL,
        revision=REVISION,
        corpus_version=version,
        schema=vectors_schema,
        index_schema=test_index,
    )
    meta = db.execute(
        f"SELECT model, revision, corpus_version, count, dim, sha256, max_length,"
        f" truncated, dtype FROM {VECTORS}.meta WHERE model_key = %s",
        (KEY,),
    ).fetchone()
    sha256 = read_header(path)["sha256"]
    assert meta == (MODEL, REVISION, version, count, 3, sha256, 512, 2, "float32")
    # The reader gives the same row back.
    assert vectors_meta(db, KEY, vectors_schema) == VectorsMeta(
        version, 3, sha256, 512, 2, "float32"
    )
    # The tie must not lean on the table's physical order: rewriting ordinal 3's row
    # moves it after ordinal 5's.
    db.execute(f"UPDATE {VECTORS}.{KEY} SET embedding = embedding WHERE ordinal = 3")
    hits = nearest(
        db, [1.0, 0.0, 0.0], 4, key=KEY, schema=vectors_schema, index_schema=test_index
    )
    ids: dict[int, str] = dict(
        db.execute(
            f"SELECT ordinal, id FROM {test_index}.passages WHERE ordinal IN (1, 3, 5, 7)"
        ).fetchall()
    )
    assert [hit.passage_id for hit in hits] == [ids[7], ids[3], ids[5], ids[1]]
    assert [hit.score for hit in hits] == pytest.approx([1.0, 0.6, 0.6, 0.0], abs=1e-6)
