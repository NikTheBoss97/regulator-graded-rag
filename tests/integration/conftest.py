# Author: Nicola Antonello
import os
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest


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
