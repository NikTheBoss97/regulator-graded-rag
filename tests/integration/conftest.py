# Author: Nicola Antonello
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from regulator_graded_rag.manifest import Manifest, check_bytes, load_manifest

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
