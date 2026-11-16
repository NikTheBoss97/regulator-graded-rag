# Author: Nicola Antonello
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from regulator_graded_rag.drafts import (
    draft_letter,
    drift_draft,
    load_drafts,
    main,
    with_drift,
    write_drafts,
)
from regulator_graded_rag.ecfr import Cache
from regulator_graded_rag.fetch import Response
from regulator_graded_rag.letter_page import LetterPage
from regulator_graded_rag.letters import Letter
from tests.unit.test_ecfr import PAGE as ECFR_PAGE

ORIGINAL = "https://www.phmsa.dot.gov/regulations/title49/interp/99-0001"
LETTER = Letter("99-0001", 2020, "20260101000000", ORIGINAL, "article", 100, "0" * 64)
DEFINITIONS = {"hazmat employee": "Hazmat%20employee"}
TABLES = frozenset({"172.101"})
PAGE = LetterPage(
    "article",
    date(2020, 3, 2),
    "Example Freight LLC",
    "Jane Roe",
    (
        "March 2, 2020",
        "Reference No. 99-0001",
        "Dear Ms. Roe:",
        "We have paraphrased and answered your questions as follows:",
        'Q1. You ask if Example Freight LLC may display the "#" symbol on its package.',
        'A1. The answer is no. According to § 172.301(a), the number follows "UN".',
        "Q2. You ask whether the 12 mm height applies.",
        "A2. The answer is yes, under § 172.301(a)(1).",
        "Q3. You ask how to mark a package.",
        "A3. Section 172.301 describes the marking.",
        "Q4. You ask whether a tank needs placards.",
        "Sincerely,",
    ),
)


def with_paragraphs(*paragraphs: str) -> LetterPage:
    return replace(PAGE, paragraphs=("March 2, 2020", *paragraphs))


def test_a_letter_gives_one_draft_per_qualifying_question() -> None:
    drafts = draft_letter(LETTER, PAGE, "dev", DEFINITIONS, TABLES)
    assert [d.id for d in drafts] == ["99-0001-Q1", "99-0001-Q2"]
    assert [d.answer for d in drafts] == ["no", "yes"]
    assert [d.evidence for d in drafts] == [("172.301(a)",), ("172.301(a)(1)",)]
    assert all(d.rewritten and d.question.startswith("Is it the case") for d in drafts)
    assert {d.source for d in drafts} == {
        f"https://web.archive.org/web/20260101000000/{ORIGINAL}"
    }
    assert {(d.letter_date, d.date_source, d.split) for d in drafts} == {
        ("2020-03-02", "letter", "dev")
    }


def test_personal_data_is_scrubbed_from_the_question() -> None:
    first = draft_letter(LETTER, PAGE, "dev", DEFINITIONS, TABLES)[0]
    assert "[company]" in first.question and "Example Freight" not in first.question
    assert "scrubbed" in first.flags


def test_an_unnumbered_question_is_q1_and_flagged() -> None:
    page = with_paragraphs(
        "This letter is in response to your email.",
        "You ask whether the bins may keep the mark.",
        "Yes. In accordance with § 172.303(b)(1), the prohibition does not apply.",
    )
    [draft] = draft_letter(LETTER, page, "dev", DEFINITIONS, TABLES)
    assert draft.id == "99-0001-Q1" and "unnumbered" in draft.flags


def test_a_question_without_a_rule_keeps_its_text_and_is_flagged() -> None:
    page = with_paragraphs(
        "Q1. You ask will a tank meet the definition.",
        "A1. The answer is no. See § 173.24.",
    )
    [draft] = draft_letter(LETTER, page, "dev", DEFINITIONS, TABLES)
    assert draft.question == "You ask will a tank meet the definition."
    assert not draft.rewritten and "not rewritten" in draft.flags


def test_outside_only_citations_make_an_unanswerable_candidate() -> None:
    page = with_paragraphs(
        "Q1. You ask whether a special permit is needed.",
        "A1. The answer is yes. See § 107.105.",
    )
    [draft] = draft_letter(LETTER, page, "dev", DEFINITIONS, TABLES)
    assert (draft.type, draft.answer, draft.kept) == ("unanswerable", "", True)
    assert "outside the corpus" in draft.flags and draft.evidence


def test_drift_outcomes_decide_whether_a_draft_is_kept() -> None:
    first = draft_letter(LETTER, PAGE, "dev", DEFINITIONS, TABLES)[0]
    assert with_drift(first, {"172.301(a)": "unchanged"}).kept
    assert not with_drift(first, {"172.301(a)": "changed"}).kept
    assert not with_drift(first, {"172.301(a)": "missing"}).kept
    assert with_drift(first, {"172.301(a)": "unchanged"}).drift == {
        "172.301(a)": "unchanged"
    }


def test_known_differences_are_flagged() -> None:
    page = with_paragraphs(
        "Q1. You ask whether the cylinder must be retested.",
        "A1. The answer is yes, under § 180.209(a).",
    )
    [draft] = draft_letter(LETTER, page, "dev", DEFINITIONS, TABLES)
    assert "known difference" in draft.flags


def test_the_date_and_its_source_are_flagged() -> None:
    # Beyond the plan's list: the owner confirms a date the page gives two ways.
    later = replace(PAGE, publish_date=date(2020, 5, 1))
    assert (
        "dates differ"
        in draft_letter(LETTER, later, "dev", DEFINITIONS, TABLES)[0].flags
    )
    undated = replace(later, paragraphs=PAGE.paragraphs[1:])
    first = draft_letter(LETTER, undated, "dev", DEFINITIONS, TABLES)[0]
    assert (first.letter_date, first.date_source) == ("2020-05-01", "published")
    assert "date from the publish field" in first.flags


def test_an_undated_letter_gives_no_drafts() -> None:
    page = replace(PAGE, publish_date=None, paragraphs=PAGE.paragraphs[1:])
    assert draft_letter(LETTER, page, "dev", DEFINITIONS, TABLES) == []


def test_held_out_drafts_need_the_owners_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # From an empty folder, so a guard moved below the inputs could never let this
    # test open a held-out letter.
    monkeypatch.chdir(tmp_path)
    assert main(["--split", "heldout"]) == 2


def test_the_drift_step_compares_the_letters_day_with_the_edition(
    tmp_path: Path,
) -> None:
    # Review: main's drift wiring had no test.
    asked: list[str] = []

    def get(url: str) -> Response:
        asked.append(url)
        page = ECFR_PAGE
        if "/2020-03-02/" in url:
            page = page.replace("(a) Rule a.", "(a) Rule a, as then worded.")
        return Response(200, "text/html", page.encode())

    first = draft_letter(LETTER, PAGE, "dev", DEFINITIONS, TABLES)[0]
    changed = replace(first, evidence=("173.9(a)",))
    # (a)(1) is its own paragraph; (b) is followed by a table, so it compares by
    # its whole section (owner, 2026-11-15), which did change.
    unchanged = replace(first, evidence=("173.9(a)(1)",))
    cache = Cache(tmp_path, get)
    assert not drift_draft(changed, cache).kept
    assert drift_draft(unchanged, cache).drift == {"173.9(a)(1)": "unchanged"}
    assert drift_draft(unchanged, cache).kept
    assert any("/2020-03-02/" in url for url in asked)


def test_an_unanswerable_draft_skips_the_drift_step(tmp_path: Path) -> None:
    def get(url: str) -> Response:
        raise AssertionError(f"fetched {url}")

    page = with_paragraphs(
        "Q1. You ask whether a special permit is needed.",
        "A1. The answer is yes. See § 107.105.",
    )
    [draft] = draft_letter(LETTER, page, "dev", DEFINITIONS, TABLES)
    assert drift_draft(draft, Cache(tmp_path, get)) == draft


def test_a_picture_mention_is_flagged() -> None:
    page = with_paragraphs(
        "Q1. You provide photos and ask whether the marking complies.",
        "A1. The answer is yes, under § 172.301(a).",
    )
    [draft] = draft_letter(LETTER, page, "dev", DEFINITIONS, TABLES)
    assert "picture" in draft.flags


def test_an_answer_that_continues_adds_its_citations_and_is_flagged() -> None:
    page = with_paragraphs(
        "Q1. You ask whether the cylinder may be refilled.",
        "A1. The answer is yes, under § 180.205(a).",
        "Thus, in accordance with § 180.415, it must be inspected.",
        "I hope this information is helpful.",
    )
    [draft] = draft_letter(LETTER, page, "dev", DEFINITIONS, TABLES)
    assert draft.evidence == ("180.205(a)", "180.415")
    assert "answer continues" in draft.flags


def test_an_unkept_draft_is_written_without_its_question(tmp_path: Path) -> None:
    # The owner's ruling of 2026-11-16: nobody checks an unkept draft's question, so
    # no letter text of it reaches git.
    first, second = draft_letter(LETTER, PAGE, "dev", DEFINITIONS, TABLES)
    kept = with_drift(first, {"172.301(a)": "unchanged"})
    dropped = with_drift(second, {"172.301(a)(1)": "changed"})
    path = tmp_path / "drafts.jsonl"
    write_drafts(path, [kept, dropped])
    assert load_drafts(path) == [kept, replace(dropped, question="")]


def test_drafts_survive_a_round_trip(tmp_path: Path) -> None:
    drafts = [
        with_drift(d, {label: "unchanged" for label in d.evidence})
        for d in draft_letter(LETTER, PAGE, "dev", DEFINITIONS, TABLES)
    ]
    path = tmp_path / "drafts.jsonl"
    write_drafts(path, drafts)
    assert load_drafts(path) == drafts
    data = path.read_bytes()
    assert b"\r" not in data and data.count(b"\n") == len(drafts)
