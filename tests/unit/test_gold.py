# Author: Nicola Antonello
import json
from pathlib import Path

import pytest

from regulator_graded_rag.gold import EVIDENCE, gold_version, load_items

GOOD: dict[str, object] = {
    "id": "99-0001-Q1",
    "question": "Does § 171.1 apply to a person who marks a packaging?",
    "type": "lookup",
    "answer": "yes",
    "evidence": ["171.1(a)"],
    "letter_date": "2020-03-02",
    "source": "https://web.archive.org/web/20260101000000id_/https://www.phmsa.dot.gov/regulations/title49/interp/99-0001",
    "split": "dev",
    "written_by": "PHMSA, extractor 1",
    "verified": "owner, 2026-11-20",
    "edition": "2025",
}
UNANSWERABLE = GOOD | {
    "id": "U-1",
    "question": "Which segregation code does the IMDG Code give a Class 8 liquid?",
    "type": "unanswerable",
    "answer": "",
    "evidence": ["Parts 171-180 searched for the IMDG Code's segregation codes"],
    "letter_date": "",
    "source": "",
    "written_by": "owner",
}


def write(tmp_path: Path, *records: dict[str, object]) -> Path:
    path = tmp_path / "items.jsonl"
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8", newline="\n"
    )
    return path


def test_items_load_with_their_sections(tmp_path: Path) -> None:
    items = load_items(
        write(
            tmp_path,
            GOOD,
            UNANSWERABLE,
            GOOD
            | {
                "id": "99-0001-Q2",
                "type": "multi_passage",
                "evidence": ["173.185(c)(1)", "172.appA"],
            },
        )
    )
    assert [(i.answerable, i.sections) for i in items] == [
        (True, frozenset({"171.1"})),
        (False, frozenset()),
        (True, frozenset({"173.185", "172.appA"})),
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "Q1"),
        ("type", "other"),
        ("answer", "maybe"),
        ("evidence", []),
        ("evidence", ["Part 107"]),
        ("letter_date", "March 2, 2020"),
        ("source", "https://example.com/x"),
        ("split", "test"),
        ("verified", ""),
        ("edition", "2024"),
        ("extra", 1),
        # Beyond the plan's list: the gold rules want every field filled in, the
        # question cleaned, and a refusal that names the line rather than a TypeError.
        ("id", 1),
        ("evidence", [171]),
        ("question", ""),
        ("written_by", " "),
        ("letter_date", "2020-02-30"),
    ],
)
def test_a_bad_field_is_refused(tmp_path: Path, field: str, value: object) -> None:
    with pytest.raises(ValueError, match=f":1: {field}:"):
        load_items(write(tmp_path, GOOD | {field: value}))


def test_a_missing_field_is_refused(tmp_path: Path) -> None:
    record = {key: value for key, value in GOOD.items() if key != "verified"}
    with pytest.raises(ValueError, match=":1: verified: missing"):
        load_items(write(tmp_path, record))


def test_an_unanswerable_item_has_no_answer(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=":1: answer:"):
        load_items(write(tmp_path, UNANSWERABLE | {"answer": "no"}))


@pytest.mark.parametrize(
    ("field", "value"),
    [("letter_date", "2020-03-02"), ("source", "https://web.archive.org/x")],
)
def test_an_owner_item_has_no_letter_fields(
    tmp_path: Path, field: str, value: str
) -> None:
    with pytest.raises(ValueError, match=f":1: {field}:"):
        load_items(write(tmp_path, UNANSWERABLE | {field: value}))


def test_ids_are_unique(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=":2: id: repeated"):
        load_items(write(tmp_path, GOOD, GOOD))


@pytest.mark.parametrize("line", ["{", "5", "null", "[]"])
def test_a_line_that_is_not_a_json_object_is_refused(tmp_path: Path, line: str) -> None:
    # json's own message counts lines within the one line it was given, not the file.
    path = write(tmp_path, GOOD)
    path.write_text(path.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=":2: json:"):
        load_items(path)


def test_the_gold_version_changes_with_any_byte(tmp_path: Path) -> None:
    path = write(tmp_path, GOOD)
    before = gold_version(path)
    path.write_bytes(path.read_bytes().replace(b"yes", b"no "))
    assert gold_version(path) != before and len(before) == 64


def test_a_definition_key_is_an_evidence_label() -> None:
    # eCFR keys a definition of section 171.8 by its term (plan 2c, Decision 3).
    assert EVIDENCE.fullmatch("171.8(Non-bulk%20packaging)")
    assert EVIDENCE.fullmatch("171.8(Self-defense%20spray)(1)")
