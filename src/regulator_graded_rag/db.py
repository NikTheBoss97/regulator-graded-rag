# Author: Nicola Antonello
"""The connection to the Postgres that DATABASE_URL names (ADR-0004)."""

import os
from typing import Any

import psycopg

NO_DATABASE = (
    'DATABASE_URL is not set: start Postgres with "docker compose up -d --wait" and set'
    " DATABASE_URL as in .env.example"
)


def database_url() -> str:
    """DATABASE_URL, or RuntimeError saying how to start the database and set it."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(NO_DATABASE)
    return url


def connect(url: str | None = None) -> psycopg.Connection[tuple[Any, ...]]:
    """A connection in autocommit mode: a statement that must stay whole opens its own
    transaction."""
    return psycopg.connect(url or database_url(), autocommit=True)
