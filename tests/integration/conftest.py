# Author: Nicola Antonello
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from regulator_graded_rag.ecfr import Cache, UnitText, edition_units
from regulator_graded_rag.fetch import http_get
from regulator_graded_rag.manifest import Manifest, check_bytes, load_manifest
from regulator_graded_rag.passages import FileBuild, build_corpus
from regulator_graded_rag.polite import Paced

REPO = Path(__file__).resolve().parents[2]


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
