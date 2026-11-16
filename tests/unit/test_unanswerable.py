# Author: Nicola Antonello
import json
from pathlib import Path

import pytest

from regulator_graded_rag.gold import load_items
from regulator_graded_rag.split import SEED, draw_key
from regulator_graded_rag.unanswerable import (
    complete,
    split_questions,
    split_unanswerable,
)


def test_the_owners_questions_are_split_once(tmp_path: Path) -> None:
    records = [
        {
            "id": f"U-{n}",
            "question": f"Which code applies to case {n}?",
            "searched": "Parts 171-180 for the code",
        }
        for n in range(1, 11)
    ]
    source = tmp_path / "all.jsonl"
    source.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    outputs = {"dev": tmp_path / "dev.jsonl", "heldout": tmp_path / "other.jsonl"}
    assert split_questions(source, outputs, "owner, 2026-11-18") == {
        "dev": 6,
        "heldout": 4,
    }
    expected = split_unanswerable([record["id"] for record in records])
    for split, path in outputs.items():
        written = load_items(path)
        ids = sorted(name for name, chosen in expected.items() if chosen == split)
        assert [item.id for item in written] == ids
        assert {item.split for item in written} == {split}
    # A second split could move a question across: it is refused, and nothing changes.
    before = {split: path.read_bytes() for split, path in outputs.items()}
    with pytest.raises(ValueError, match="split once"):
        split_questions(source, outputs, "owner, 2026-11-19")
    assert {split: path.read_bytes() for split, path in outputs.items()} == before


def test_unanswerable_items_are_split_by_the_seed() -> None:
    ids = [f"U-{n}" for n in range(1, 11)]
    split = split_unanswerable(ids)
    lowest = sorted(ids, key=lambda name: draw_key(SEED, name))[:4]
    assert sorted(name for name, s in split.items() if s == "heldout") == sorted(lowest)
    assert sorted(split) == sorted(ids)
    assert split == split_unanswerable(ids)
    assert split == split_unanswerable(list(reversed(ids)))


def test_a_repeated_id_is_refused() -> None:
    with pytest.raises(ValueError, match="U-1"):
        split_unanswerable(["U-1", "U-2", "U-1"])


def test_an_owners_question_becomes_an_unanswerable_item() -> None:
    record = {
        "id": "U-3",
        "question": "Which segregation code does the IMDG Code give a Class 8 liquid?",
        "searched": "Parts 171-180 for the IMDG Code's segregation codes",
    }
    item = complete(record, "heldout", "owner, 2026-11-18")
    assert (item.type, item.answer, item.split, item.written_by) == (
        "unanswerable",
        "",
        "heldout",
        "owner",
    )
    assert item.evidence == (record["searched"],)
    assert (item.letter_date, item.source, item.verified) == (
        "",
        "",
        "owner, 2026-11-18",
    )


@pytest.mark.parametrize(
    "record",
    [
        {"id": "U-4", "question": "Which code applies?"},
        {
            "id": "U-4",
            "question": "Which code applies?",
            "searched": "x",
            "answer": "y",
        },
        {"id": "U-4", "question": " ", "searched": "Parts 171-180"},
    ],
)
def test_a_malformed_owners_question_is_refused(record: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="U-4"):
        complete(record, "dev", "owner, 2026-11-18")
