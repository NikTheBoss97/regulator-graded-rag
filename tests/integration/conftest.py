# Author: Nicola Antonello
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from regulator_graded_rag.db import connect, database_url
from regulator_graded_rag.ecfr import Cache, UnitText, edition_units
from regulator_graded_rag.fetch import http_get
from regulator_graded_rag.index import build_index
from regulator_graded_rag.manifest import Manifest, check_bytes, load_manifest
from regulator_graded_rag.passages import FileBuild, build_corpus
from regulator_graded_rag.polite import Paced
from regulator_graded_rag.review import Record

REPO = Path(__file__).resolve().parents[2]
TEST_SCHEMA = "rgr_test"


@pytest.fixture(scope="session")
def manifest() -> Manifest:
    """The committed corpus manifest."""
    return load_manifest(REPO / "corpus" / "manifest.toml")


@pytest.fixture(scope="session")
def corpus_dir(manifest: Manifest) -> Path:
    """corpus/raw/, once every file the manifest names is there with its bytes.

    A missing or changed file fails the test with the command that fetches it, never a
    skip, for the same reason as the database below.
    """
    raw = REPO / "corpus" / "raw"
    for entry in manifest.files:
        path = raw / entry.name
        problem = check_bytes(entry, path.read_bytes()) if path.is_file() else "missing"
        if problem:
            pytest.fail(
                f'{entry.name}: {problem}: run "uv run python -m regulator_graded_rag.fetch"',
                pytrace=False,
            )
    return raw


@pytest.fixture(scope="session")
def corpus_build(manifest: Manifest, corpus_dir: Path) -> list[FileBuild]:
    """The whole corpus, built once per test session."""
    return build_corpus(manifest, corpus_dir)


@pytest.fixture(scope="session")
def ecfr_cache() -> Cache:
    """eCFR's pages, fetched once a second and kept in eval/ecfr/, so a rerun fetches
    nothing. eCFR out of reach fails the test with the URL, never a skip."""
    get = Paced(lambda url: http_get(url, accept_gzip=True), interval=1.0)
    return Cache(REPO / "eval" / "ecfr", get)


@pytest.fixture(scope="session")
def ecfr_edition(ecfr_cache: Cache) -> dict[str, UnitText]:
    """The ten parts' units on the edition's day, 1 October 2025."""
    return edition_units(ecfr_cache)


@pytest.fixture(scope="session")
def db() -> Iterator[psycopg.Connection[tuple[Any, ...]]]:
    """One autocommit connection for the session; without DATABASE_URL the test fails
    with instructions, never skips."""
    try:
        url = database_url()
    except RuntimeError as err:
        pytest.fail(str(err), pytrace=False)
    with connect(url) as connection:
        yield connection


@pytest.fixture(scope="session")
def index_records(corpus_build: list[FileBuild]) -> list[Record]:
    """The whole corpus's passages as index records, in file order."""
    return [
        {"id": p.id, "kind": p.kind, "source": p.source, "page": p.page, "text": p.text}
        for build in corpus_build
        for unit in build.units
        for p in unit.passages
    ]


@pytest.fixture(scope="session")
def test_index(
    db: psycopg.Connection[tuple[Any, ...]],
    manifest: Manifest,
    index_records: list[Record],
) -> Iterator[str]:
    """The corpus indexed once in a schema of its own, never the owner's rgr."""
    build_index(db, index_records, str(manifest.version), schema=TEST_SCHEMA)
    yield TEST_SCHEMA
    db.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")


@pytest.fixture
def conn() -> Iterator[psycopg.Connection[tuple[Any, ...]]]:
    """A connection to the database that DATABASE_URL names, in autocommit mode.

    Without DATABASE_URL the test fails with instructions instead of skipping, so a
    missing database can never look like a green run.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.fail(
            'DATABASE_URL is not set: start Postgres with "docker compose up -d --wait"'
            " and set DATABASE_URL as in .env.example",
            pytrace=False,
        )
    with psycopg.connect(url, autocommit=True) as connection:
        yield connection
