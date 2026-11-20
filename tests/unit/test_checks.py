# Author: Nicola Antonello
from dataclasses import replace

import pytest

from regulator_graded_rag.checks import (
    Reason,
    context_after,
    context_before,
    pair_of,
    reasons,
    ticks,
)
from regulator_graded_rag.drafts import Draft
from regulator_graded_rag.letter_page import LetterPage

QUESTION = "Is it the case that the marking must be durable?"
ANSWER = (
    "The answer is yes. The marking must be durable in accordance with § 172.401(a)(2)."
    " The mark stays on the package."
)
OPENING = (
    "This letter is in response to your email requesting clarification of the"
    " Hazardous Materials Regulations (HMR; 49 CFR Parts 171-180)."
)
DRAFT = Draft(
    id="99-0001-Q1",
    letter="99-0001",
    number=1,
    numbered=True,
    question=QUESTION,
    rewritten=True,
    answer="yes",
    evidence=("172.401(a)(2)",),
    outside=(),
    type="lookup",
    letter_date="2020-06-01",
    date_source="letter",
    source="https://web.archive.org/web/20260101000000/https://www.phmsa.dot.gov/99-0001",
    split="dev",
    drift={"172.401(a)(2)": "unchanged"},
    kept=True,
    flags=(),
)


def letter(*paragraphs: str, company: str = "", individual: str = "") -> LetterPage:
    return LetterPage(
        "article",
        None,
        company,
        individual,
        ("June 1, 2020", "Dear Ms. Doe:", OPENING, *paragraphs),
    )


PAGE = letter(f"Q1. {QUESTION}", f"A1. {ANSWER}")


def kinds(draft: Draft, page: LetterPage | None) -> list[str]:
    return [reason.kind for reason in reasons(draft, page)]


def test_a_clean_draft_has_no_reason() -> None:
    assert reasons(DRAFT, PAGE) == []


@pytest.mark.parametrize(
    ("flag", "kind"),
    [
        ("picture", "shown"),
        ("not rewritten", "not rewritten"),
        ("known difference", "known difference"),
        ("date from the publish field", "date from the publish field"),
        ("outside the corpus", "outside the corpus"),
        ("scrubbed", "scrubbed"),
        ("answer continues", "answer continues"),
    ],
)
def test_each_judgment_flag_is_a_reason(flag: str, kind: str) -> None:
    draft = replace(DRAFT, flags=(flag,), outside=("26 CFR 1.1",))
    assert kinds(draft, PAGE) == [kind]


def test_a_flag_that_is_no_judgment_is_no_reason() -> None:
    draft = replace(DRAFT, flags=("dates differ", "unnumbered"))
    assert reasons(draft, PAGE) == []


def test_the_outside_reason_names_the_rules() -> None:
    draft = replace(
        DRAFT, flags=("outside the corpus",), outside=("26 CFR 1.1", "Part 40")
    )
    [reason] = reasons(draft, PAGE)
    assert "outside Parts 171-180: 26 CFR 1.1, Part 40." in reason.ask


def test_an_unanswerable_draft_needs_the_owners_search() -> None:
    draft = replace(DRAFT, type="unanswerable", answer="", evidence=("x",))
    [reason] = reasons(draft, PAGE)
    assert reason.kind == "unanswerable"
    assert reason.ask.startswith("Search the corpus first.")


@pytest.mark.parametrize(
    ("question", "answer", "kind"),
    [
        (
            (
                "You also provide examples of a variety of placards and ask if they are in"
                " compliance with § 172.516(c)(5)."
            ),
            (
                "The answer is yes. The examples you provided meet the intent of §"
                " 172.516(c)(5)."
            ),
            "shown",
        ),
        (
            (
                "Is it the case that the transport vehicle in the photographs provided is"
                " subject to the placarding requirements of Part 172, Subpart F of the HMR?"
            ),
            "The answer is no. The vehicle is not placarded.",
            "shown",
        ),
        (
            QUESTION,
            (
                "The answer is yes. Section 8(a) of DOT-SP 15146 stipulates that a person"
                " who is not a holder of the special permit may reoffer the package. The"
                " package is defined in § 171.8."
            ),
            "document",
        ),
        (
            (
                "Is it the case that your understanding of the definition of Division 2.2 is"
                " correct in that there appears to be three criteria, which must all be"
                " met, to qualify as Division 2.2? You state the criteria are:"
            ),
            ANSWER,
            "colon",
        ),
        (
            (
                "Is it the case that the shipment of PCB waste in your scenario meets the"
                " HMR definition of a hazardous waste?"
            ),
            ANSWER,
            "pointer",
        ),
        (
            (
                "Is it the case that the shipment of PCB waste in your scenario is subject"
                " to the HMR, including training requirements of Part 172, Subpart H?"
            ),
            ANSWER,
            "pointer",
        ),
    ],
)
def test_the_six_needed_changes_get_a_reason(
    question: str, answer: str, kind: str
) -> None:
    page = letter(f"Q1. {question}", f"A1. {answer}")
    draft = replace(DRAFT, question=question)
    assert kind in kinds(draft, page)


def test_for_example_is_not_something_sent() -> None:
    answer = (
        "The answer is yes. For example, a drum is a packaging under § 172.401(a)(2)."
    )
    page = letter(f"Q1. {QUESTION}", f"A1. {answer}")
    assert "shown" not in kinds(DRAFT, page)


def test_a_special_permit_sentence_is_the_reasons_sentence() -> None:
    answer = "The answer is yes. The holder of DOT-SP 15146 may ship. Else § 172.401."
    page = letter(f"Q1. {QUESTION}", f"A1. {answer}")
    reason = next(r for r in reasons(DRAFT, page) if r.kind == "document")
    assert reason.sentence == "The holder of DOT-SP 15146 may ship."


def test_a_pointer_with_its_context_in_the_question_is_no_reason() -> None:
    question = (
        "You describe a cylinder of oxygen. Is it the case that these cylinders need a"
        " mark?"
    )
    page = letter(f"Q1. {question}", f"A1. {ANSWER}")
    assert reasons(replace(DRAFT, question=question), page) == []


def test_such_as_is_no_pointer() -> None:
    question = "Is it the case that a hazmat such as a gas needs a mark?"
    page = letter(f"Q1. {question}", f"A1. {ANSWER}")
    assert reasons(replace(DRAFT, question=question), page) == []


def test_a_name_from_the_salutation_in_the_question_is_a_reason() -> None:
    question = "Ms. Doe asks whether the marking must be durable?"
    page = letter(f"Q1. {question}", f"A1. {ANSWER}")
    [reason] = reasons(replace(DRAFT, question=question), page)
    assert reason == Reason(
        "name", "The question holds a name from the letter: remove it.", "Doe"
    )


def test_every_name_in_a_salutation_is_checked() -> None:
    page = LetterPage(
        "article",
        None,
        "",
        "",
        (
            "June 1, 2020",
            "Dear Messrs. Doe and Roe:",
            OPENING,
            f"Q1. {QUESTION}",
            "A1. Yes.",
        ),
    )
    draft = replace(DRAFT, question="Is it the case that Roe may mark it?")
    assert [r.sentence for r in reasons(draft, page)] == ["Roe"]


def test_the_requesters_surname_and_company_are_names() -> None:
    page = letter(
        f"Q1. {QUESTION}", f"A1. {ANSWER}", individual="Jane Smith", company="Acme"
    )
    for question, phrase in (
        ("Is it the case that Smith may mark it?", "Smith"),
        ("Is it the case that Acme may mark it?", "Acme"),
    ):
        draft = replace(DRAFT, question=question)
        [reason] = reasons(draft, page)
        assert (reason.kind, reason.sentence) == ("name", phrase)


def test_a_name_is_matched_as_a_whole_word_and_in_case() -> None:
    page = letter(f"Q1. {QUESTION}", f"A1. {ANSWER}", individual="Jane Doe")
    draft = replace(DRAFT, question="Is it the case that a doer may mark it?")
    assert reasons(draft, page) == []


def test_a_blank_question_is_checked_as_the_letters_question() -> None:
    question = "Is it the case that your scenario needs a mark?"
    page = letter(f"Q1. {question}", f"A1. {ANSWER}")
    assert "pointer" in kinds(replace(DRAFT, question=""), page)


def test_a_missing_letter_is_a_reason() -> None:
    [reason] = reasons(DRAFT, None)
    assert reason.kind == "no letter"
    assert reason.ask.startswith("The letter's page is missing")


def test_ticks_confirm_the_verdict_each_label_and_no_name() -> None:
    got = ticks(DRAFT, PAGE)
    assert all(ok for ok, _ in got)
    assert len(got) == 1 + len(DRAFT.evidence) + 1
    assert any("The answer is yes." in text for _, text in got)


def test_a_label_not_in_the_answer_gets_no_tick() -> None:
    answer = "The answer is yes. See § 173.421."
    page = letter(f"Q1. {QUESTION}", f"A1. {answer}")
    draft = replace(DRAFT, evidence=("173.425",))
    assert [ok for ok, _ in ticks(draft, page) if not ok] == [False]


def test_pair_of_finds_the_drafts_number() -> None:
    pair = pair_of(replace(DRAFT, number=1), PAGE)
    assert pair is not None and pair.question == QUESTION
    assert pair_of(replace(DRAFT, number=2), PAGE) is None


def test_context_before_keeps_the_requesters_facts() -> None:
    opening = (
        "This letter is in response to your May 24, 2019, email requesting"
        " clarification of the Hazardous Materials Regulations (HMR; 49 CFR Parts"
        " 171-180) applicable to cryogenic liquids. You state that you transport"
        " multiple 180 L cylinders at 22 psig by highway. Specifically, you ask for"
        " clarification regarding the use of the exceptions for cryogenic liquids as"
        " provided in § 173.320."
    )
    page = replace(
        letter(f"Q1. {QUESTION}", f"A1. {ANSWER}"),
        paragraphs=(
            "June 1, 2020",
            "Dear Ms. Doe:",
            opening,
            f"Q1. {QUESTION}",
            "A1. Yes.",
        ),
    )
    assert (
        context_before(DRAFT, page)
        == "You state that you transport multiple 180 L cylinders at 22 psig by highway."
    )


def test_context_before_takes_the_scenario_after_a_colon() -> None:
    opening = (
        "This letter is in response to your email. Specifically, you provide the"
        " following scenario:"
    )
    page = LetterPage(
        "article",
        None,
        "",
        "",
        (
            "June 1, 2020",
            "Dear Ms. Doe:",
            opening,
            "A truck carries 3 drums of paint.",
            "We have paraphrased and answered your questions as follows:",
            f"Q1. {QUESTION}",
            f"A1. {ANSWER}",
        ),
    )
    assert context_before(DRAFT, page) == "A truck carries 3 drums of paint."


def test_context_after_completes_a_question_ending_with_a_colon() -> None:
    page = letter(
        "Q1. Is it the case that there are criteria? You state the criteria are:",
        "(1) one; (2) two; (3) three.",
        "A1. The answer is no, under § 172.401(a)(2).",
    )
    assert context_after(DRAFT, page) == "(1) one; (2) two; (3) three."


def test_context_is_scrubbed() -> None:
    opening = (
        "This letter is in response to your email. Jane Doe states that she ships"
        " paint."
    )
    page = LetterPage(
        "article",
        None,
        "",
        "Jane Doe",
        ("June 1, 2020", "Dear Ms. Doe:", opening, f"Q1. {QUESTION}", "A1. Yes."),
    )
    assert context_before(DRAFT, page) == "[name] states that she ships paint."


def test_a_definition_label_gets_its_tick() -> None:
    answer = (
        "The answer is no. In accordance with § 171.8, a hazardous waste is defined as"
        " a material that is subject to the Hazardous Waste Manifest Requirements."
    )
    page = letter(f"Q1. {QUESTION}", f"A1. {answer}")
    draft = replace(DRAFT, evidence=("171.8(Hazardous%20waste)",), answer="no")
    assert (True, "The answer cites 171.8(Hazardous%20waste)") in ticks(draft, page)


def test_a_section_range_member_gets_its_tick() -> None:
    answer = "The answer is yes. See §§ 173.1 through 173.3."
    page = letter(f"Q1. {QUESTION}", f"A1. {answer}")
    draft = replace(DRAFT, evidence=("173.2",))
    got = ticks(draft, page, units=("173.1", "173.2", "173.3"))
    assert (True, "The answer cites 173.2") in got
