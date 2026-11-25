# Author: Nicola Antonello
"""BM25 written in SQL over the index tables (ADR-0005), the baseline retriever.

The variant the bm25s library calls "lucene", its default, which the integration test
checks it against on the whole corpus. For a passage p and a question q:

    score(p, q) = sum over q's lexemes t of
        qtf(t) * ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
               * tf(t, p) / (tf(t, p) + k1 * (1 - b + b * len(p) / avglen))

where N is the number of passages, df(t) the passages holding t, tf(t, p) its count in p,
len(p) the passage's number of terms, and qtf(t) the number of times the question holds
t, as Lucene and bm25s count a repeated query word each time. Like Lucene since version 8
(LUCENE-8563), it has no (k1 + 1) factor in the numerator, which would scale every score
alike; unlike Lucene, which stores a passage's length in one byte, it uses exact lengths,
so its scores match bm25s's, not Lucene's own. k1 is 1.2 and b 0.75, Lucene's and
Elasticsearch's defaults, fixed before any dev run. Postgres's english configuration
splits and stems the question as it did the passages, and an index built with another
configuration is refused. Every number is double precision, and ties are broken in
corpus order, so a rerun on another machine gives the same ranking.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import psycopg
from psycopg import sql

from regulator_graded_rag.index import CONFIG, SCHEMA, index_label

K1 = 1.2
B = 0.75

_SEARCH = """
WITH q AS (
  SELECT lexeme, cardinality(positions) AS qtf
  FROM unnest(to_tsvector(%(config)s::regconfig, %(question)s))
)
SELECT p.id,
       sum(q.qtf * ln(1 + (s.n - d.df + 0.5) / (d.df + 0.5))
           * t.tf / (t.tf + %(k1)s::double precision
                     * (1 - %(b)s::double precision
                        + %(b)s::double precision * l.length / s.avgdl))) AS score
FROM q
JOIN {s}.df d USING (lexeme)
JOIN {s}.terms t USING (lexeme)
JOIN {s}.lengths l USING (ordinal)
JOIN {s}.passages p USING (ordinal)
CROSS JOIN {s}.stats s
GROUP BY p.ordinal, p.id
ORDER BY score DESC, p.ordinal
LIMIT %(k)s
"""

Conn = psycopg.Connection[tuple[Any, ...]]


@dataclass(frozen=True)
class Hit:
    passage_id: str
    score: float


class Retriever(Protocol):
    """What every retrieval method gives the harness."""

    name: str

    def settings(self) -> dict[str, str | float]: ...

    def search(self, question: str, k: int) -> list[Hit]: ...


class StaleIndex(RuntimeError):
    """The index was built from another corpus version, so it is never searched."""


class BM25:
    name = "bm25"

    def __init__(
        self,
        conn: Conn,
        *,
        corpus_version: str,
        k1: float = K1,
        b: float = B,
        schema: str = SCHEMA,
        config: str = CONFIG,
    ) -> None:
        version, built_with = index_label(conn, schema) or (None, None)
        if version != corpus_version:
            raise StaleIndex(
                f"the index holds corpus version {version}, not {corpus_version}:"
                ' run "uv run python -m regulator_graded_rag.index"'
            )
        if built_with != config:
            raise StaleIndex(
                f"the index was built with the {built_with} text-search configuration,"
                f" not {config}, so questions would be stemmed differently"
            )
        self._conn = conn
        self._k1 = k1
        self._b = b
        self._config = config
        self._query = sql.SQL(_SEARCH).format(s=sql.Identifier(schema))
        self._built = sql.SQL(
            "SELECT extract(epoch FROM built)::text, version() FROM {s}.meta"
        ).format(s=sql.Identifier(schema))

    def identity(self) -> dict[str, str]:
        """What a search reads besides its settings: when the index was built, in
        seconds since 1970 whatever the session's time zone, and the server that computes
        the scores, whose arithmetic could change in the last digits."""
        row = self._conn.execute(self._built).fetchone()
        assert row is not None, "an index always has its meta row"
        built, server = row
        return {"index_built": built, "server": server}

    def settings(self) -> dict[str, str | float]:
        return {
            "k1": self._k1,
            "b": self._b,
            "config": self._config,
            "variant": "lucene",
        }

    def search(self, question: str, k: int) -> list[Hit]:
        """The k best passages, best first; none when no word of the question is indexed."""
        params = {
            "config": self._config,
            "question": question,
            "k1": self._k1,
            "b": self._b,
            "k": k,
        }
        rows = self._conn.execute(self._query, params).fetchall()
        return [Hit(passage_id, float(score)) for passage_id, score in rows]


def tokens(conn: Conn, text: str, config: str = CONFIG) -> list[str]:
    """The text's lexemes, each repeated by its count, in order of first appearance."""
    rows = conn.execute(
        "SELECT lexeme, positions FROM unnest(to_tsvector(%s::regconfig, %s))",
        (config, text),
    ).fetchall()
    return [
        lexeme
        for lexeme, positions in sorted(rows, key=lambda r: min(r[1]))
        for _ in positions
    ]
