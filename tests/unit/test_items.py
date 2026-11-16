# Author: Nicola Antonello
import json
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from regulator_graded_rag import items, unanswerable
from regulator_graded_rag.drafts import Draft, write_drafts
from regulator_graded_rag.gold import Item, load_items, write_items
from regulator_graded_rag.items import build, latest
from regulator_graded_rag.review_page import Decision, digest
from regulator_graded_rag.unanswerable import complete
from tests.unit.test_review_page import DRAFT

A = DRAFT
B = replace(DRAFT, id="99-0002-Q1", letter="99-0002")
C = replace(DRAFT, id="99-0003-Q1", letter="99-0003")
OWNED = complete(
    {
        "id": "U-1",
        "question": "Which segregation code does the IMDG Code give a Class 8 liquid?",
        "searched": "Parts 171-180 for the IMDG Code's segregation codes",
    },
    "dev",
    "owner, 2026-11-18",
)


def decided(
    draft: Draft,
    action: str,
    fields: dict[str, object] | None = None,
    at: str = "2026-11-20T10:00:00+00:00",
) -> dict[str, object]:
    return {
        "id": draft.id,
        "action": action,
        "fields": fields or {},
        "at": at,
        "digest": digest(draft),
    }


def always(item: Item) -> bool:
    return True


def test_items_follow_the_latest_decision() -> None:
    question = "Does § 171.1 apply to a person who marks a box?"
    decisions = latest(
        [
            decided(A, "approve"),
            decided(B, "edit", {"question": question}),
            decided(C, "approve"),
            decided(C, "reject"),
        ]
    )
    built, counts = build([A, B, C], decisions, [], always)
    assert [item.id for item in built] == [A.id, B.id]
    assert built[0].question == A.question
    assert built[1].question == question
    assert counts == Counter({"kept": 2, "rejected": 1})


def test_the_page_decisions_are_what_build_reads() -> None:
    decision = Decision(A.id, "approve", {}, "2026-11-20T10:00:00+00:00", digest(A))
    built, _ = build([A], latest([asdict(decision)]), [], always)
    assert [item.id for item in built] == [A.id]


def test_an_undecided_kept_draft_stops_the_build() -> None:
    unkept = replace(C, kept=False)
    with pytest.raises(ValueError, match="1 undecided"):
        build([A, B, unkept], latest([decided(A, "approve")]), [], always)


def test_a_decision_on_another_version_of_the_draft_does_not_count() -> None:
    older = decided(A, "approve") | {"digest": "an older draft's"}
    with pytest.raises(ValueError, match="1 undecided"):
        build([A], latest([older]), [], always)


def test_an_edited_date_or_evidence_is_checked_again() -> None:
    checked: list[str] = []

    def recheck(item: Item) -> bool:
        checked.append(item.id)
        return item.id != A.id

    decisions = latest(
        [
            decided(A, "edit", {"letter_date": "2020-03-03"}),
            decided(B, "edit", {"evidence": ["171.1(b)"]}),
            decided(C, "edit", {"question": "Does § 171.1 apply to a carrier?"}),
        ]
    )
    built, counts = build([A, B, C], decisions, [], recheck)
    assert [item.id for item in built] == [B.id, C.id]
    assert checked == [A.id, B.id]
    assert counts["dropped on recheck"] == 1
    assert built[0].evidence == ("171.1(b)",)


def test_items_carry_who_wrote_and_verified_them() -> None:
    built, _ = build([A], latest([decided(A, "approve")]), [], always)
    assert (built[0].written_by, built[0].verified) == (
        "PHMSA, extractor 1",
        "owner, 2026-11-20",
    )


def test_the_owners_unanswerable_questions_join_the_items() -> None:
    built, counts = build([A], latest([decided(A, "approve")]), [OWNED], always)
    assert [item.id for item in built] == [A.id, "U-1"]
    assert counts == Counter({"kept": 1, "the owner's": 1})


def test_a_decision_that_breaks_a_gold_rule_stops_the_build() -> None:
    with pytest.raises(ValueError, match=r"99-0001-Q1: answer:"):
        build([A], latest([decided(A, "edit", {"answer": "maybe"})]), [], always)


def test_items_are_built_written_and_read_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    dev = tmp_path / "eval" / "dev"
    write_drafts(dev / "drafts.jsonl", [A, B])
    lines = [decided(A, "approve"), decided(B, "reject")]
    (dev / "decisions.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
    )
    write_items(dev / "unanswerable.jsonl", [OWNED])
    assert items.main(["--split", "dev"]) == 0
    assert [item.id for item in load_items(dev / "items.jsonl")] == [A.id, "U-1"]
    out = capsys.readouterr().out
    assert "by type, lowest first: lookup 1, unanswerable 1" in out
    assert items.main(["--split", "dev", "--freeze"]) == 1


def test_an_edited_question_is_built_from_the_draft_kept_without_it() -> None:
    # The page keeps a draft whose question the owner rewrote without its question.
    question = "Does § 171.1 apply to a person who marks a box?"
    blank = replace(B, question="")
    decision = decided(blank, "edit", {"question": question})
    built, _ = build([blank], latest([decision]), [], always)
    assert built[0].question == question


@pytest.mark.parametrize(
    ("drafts", "owned"),
    [([replace(A, split="heldout")], OWNED), ([A], replace(OWNED, split="heldout"))],
)
def test_items_of_another_split_are_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    drafts: list[Draft],
    owned: Item,
) -> None:
    monkeypatch.chdir(tmp_path)
    dev = tmp_path / "eval" / "dev"
    write_drafts(dev / "drafts.jsonl", drafts)
    line = json.dumps(decided(drafts[0], "approve")) + "\n"
    (dev / "decisions.jsonl").write_text(line, encoding="utf-8")
    write_items(dev / "unanswerable.jsonl", [owned])
    assert items.main(["--split", "dev"]) == 1
    assert "another split" in capsys.readouterr().out
    assert not (dev / "items.jsonl").exists()


def test_held_out_items_need_the_owners_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # From an empty folder, so each refusal comes before any file is read.
    monkeypatch.chdir(tmp_path)
    assert items.main(["--split", "heldout"]) == 2
    assert items.main(["--split", "heldout", "--freeze"]) == 2
    assert unanswerable.main([]) == 2
