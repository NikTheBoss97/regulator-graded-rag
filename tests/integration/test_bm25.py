# Author: Nicola Antonello
import itertools
import math
from typing import Any

import bm25s  # type: ignore[import-untyped]
import psycopg
import pytest

from regulator_graded_rag.bm25 import BM25, K1, B, StaleIndex, tokens
from regulator_graded_rag.index import build_index
from regulator_graded_rag.manifest import Manifest
from regulator_graded_rag.review import Record

Conn = psycopg.Connection[tuple[Any, ...]]

# Written for the test about the corpus's rules; none is taken from a letter.
QUESTIONS = (
    "Are lithium batteries packed with equipment excepted from the shipping paper requirements?",
    "What placard is required on a cargo tank carrying gasoline?",
    "May UN1090 acetone travel on a passenger aircraft?",
    "When must a DOT 3AA cylinder be requalified?",
    "battery battery battery",
)


def test_sql_bm25_equals_bm25s_on_the_whole_corpus(
    db: Conn, manifest: Manifest, test_index: str
) -> None:
    # bm25s gets its own tokens from the passages' text, not the index's counts, so a
    # wrong count in the index cannot reach both sides.
    rows = db.execute(
        f"SELECT p.id, t.lexeme, cardinality(t.positions) FROM {test_index}.passages p,"
        " unnest(to_tsvector('english', p.text)) t ORDER BY p.ordinal"
    ).fetchall()
    ids = [
        r[0]
        for r in db.execute(f"SELECT id FROM {test_index}.passages ORDER BY ordinal")
    ]
    docs: dict[str, list[str]] = {i: [] for i in ids}
    for pid, lexeme, tf in rows:
        docs[pid] += [lexeme] * tf
    model = bm25s.BM25(k1=K1, b=B, method="lucene", dtype="float64")
    model.index([docs[i] for i in ids], show_progress=False)
    retriever = BM25(db, corpus_version=str(manifest.version), schema=test_index)
    for question in QUESTIONS:
        scores = model.get_scores(tokens(db, question))
        expected = {ids[n]: float(s) for n, s in enumerate(scores) if s > 0}
        got = {h.passage_id: h.score for h in retriever.search(question, k=len(ids))}
        assert got.keys() == expected.keys()
        assert all(math.isclose(got[i], expected[i], rel_tol=1e-9) for i in got)


def test_ties_break_by_corpus_order(db: Conn) -> None:
    # In corpus order 171.9:1 comes before 171.10:1, and in text order after it, so a
    # tie broken by ID fails here.
    records: list[Record] = [
        {"id": f"171.{n}:1", "kind": "text", "source": "t.xml", "page": 1, "text": text}
        for n, text in ((9, "aerosol"), (20, "cylinder"), (10, "aerosol"))
    ]
    build_index(db, records, "t" * 64, schema="rgr_test_ties")
    try:
        hits = BM25(db, corpus_version="t" * 64, schema="rgr_test_ties").search(
            "aerosol", k=5
        )
        assert [h.passage_id for h in hits] == ["171.9:1", "171.10:1"]
        assert hits[0].score == hits[1].score
    finally:
        db.execute("DROP SCHEMA rgr_test_ties CASCADE")


def test_equal_scores_keep_corpus_order_on_the_corpus(
    db: Conn, manifest: Manifest, test_index: str
) -> None:
    ordinal: dict[str, int] = dict(
        db.execute(f"SELECT id, ordinal FROM {test_index}.passages").fetchall()
    )
    retriever = BM25(db, corpus_version=str(manifest.version), schema=test_index)
    ties = 0
    for question in QUESTIONS:
        hits = retriever.search(question, k=200)
        for a, b in itertools.pairwise(hits):
            if a.score == b.score:
                ties += 1
                assert ordinal[a.passage_id] < ordinal[b.passage_id], question
    assert ties > 0  # the questions do produce ties, so the order is tested


def test_a_question_without_index_terms_finds_nothing(
    db: Conn, manifest: Manifest, test_index: str
) -> None:
    retriever = BM25(db, corpus_version=str(manifest.version), schema=test_index)
    assert retriever.search("Is it?", k=50) == []


def test_questions_with_quotes_are_parameters(
    db: Conn, manifest: Manifest, test_index: str
) -> None:
    retriever = BM25(db, corpus_version=str(manifest.version), schema=test_index)
    hits = retriever.search("O'Brien's \\ \"cylinder\"; DROP TABLE x; --", k=3)
    assert len(hits) == 3


def test_search_refuses_an_index_of_another_corpus_version(
    db: Conn, test_index: str
) -> None:
    with pytest.raises(StaleIndex, match="regulator_graded_rag.index"):
        BM25(db, corpus_version="0" * 64, schema=test_index)


def test_search_refuses_an_index_built_with_another_configuration(
    db: Conn, manifest: Manifest, test_index: str
) -> None:
    # Questions must be stemmed as the passages were, and the run record must say so.
    with pytest.raises(StaleIndex, match="english"):
        BM25(
            db, corpus_version=str(manifest.version), schema=test_index, config="simple"
        )
