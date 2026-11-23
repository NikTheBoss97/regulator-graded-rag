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


def test_a_question_the_letter_does_not_hold_is_a_reason() -> None:
    draft = replace(DRAFT, id="99-0001-Q5", number=5)
    assert reasons(draft, PAGE) == [
        Reason(
            "no question",
            "The letter holds no question 5 for this draft: check it against the letter"
            " in the archive.",
        )
    ]


def test_a_verdict_the_answer_does_not_give_is_a_reason() -> None:
    answer = "The answer is no. A drum need not be marked under § 172.401(a)(2)."
    page = letter(f"Q1. {QUESTION}", f"A1. {answer}")
    assert reasons(DRAFT, page) == [
        Reason(
            "verdict",
            "The answer's first words do not give the draft's verdict: check the yes or"
            " no against the letter.",
        )
    ]
    # An unanswerable draft has no verdict to compare.
    assert kinds(replace(DRAFT, type="unanswerable", answer=""), page) == [
        "unanswerable"
    ]


def test_ticks_confirm_the_verdict_each_label_and_no_name() -> None:
    got = ticks(DRAFT, PAGE)
    assert all(ok for ok, _ in got)
    assert len(got) == 1 + len(DRAFT.evidence) + 1
    assert any("The answer is yes." in text for _, text in got)
    assert got[-1] == (
        True,
        "No name from the letter's salutation or name fields in the question",
    )


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


SCENARIO = "A truck carries 3 drums of paint by highway."
CLOSING = "If you have further questions, please contact this office."


@pytest.mark.parametrize(
    "rest",
    [
        # The reviewer's letter: its answer follows the scenario.
        (
            "The answer is yes. The drums must be marked under § 172.401(a)(2).",
            CLOSING,
            "Sincerely,",
            "Standards and Rulemaking Division",
        ),
        # The asking paragraph is the question, its other sentences included.
        (
            "You ask whether the drums must be marked. The drums hold paint.",
            "The answer is yes.",
            CLOSING,
        ),
        (CLOSING, "Sincerely,", "Standards and Rulemaking Division"),
        ("A1. Yes, under § 172.401(a)(2).", CLOSING),
    ],
)
def test_context_before_ends_where_the_letter_asks_answers_or_closes(
    rest: tuple[str, ...],
) -> None:
    opening = (
        "This letter is in response to your email. You describe the following scenario:"
    )
    page = LetterPage(
        "article",
        None,
        "",
        "",
        ("June 1, 2020", "Dear Ms. Doe:", opening, SCENARIO, *rest),
    )
    assert context_before(replace(DRAFT, numbered=False), page) == SCENARIO


def test_an_unnumbered_question_asked_in_the_opening_has_no_context_before() -> None:
    # An unnumbered question is the opening's sentences, so their facts are in it
    # already; a numbered question is not, so on the same page its draft keeps them.
    opening = (
        "This letter is in response to your email. You state that you ship drums of"
        " paint by highway. You ask whether the drums must be marked."
    )
    answer = "The answer is yes. The drums must be marked under § 172.401(a)(2)."
    page = LetterPage(
        "article",
        None,
        "",
        "",
        ("June 1, 2020", "Dear Ms. Doe:", opening, answer, CLOSING),
    )
    assert context_before(replace(DRAFT, numbered=False), page) == ""
    assert context_before(DRAFT, page) == (
        "You state that you ship drums of paint by highway."
    )


def test_context_after_completes_a_question_ending_with_a_colon() -> None:
    page = letter(
        "Q1. Is it the case that there are criteria? You state the criteria are:",
        "(1) one; (2) two; (3) three.",
        "A1. The answer is no, under § 172.401(a)(2).",
    )
    assert context_after(DRAFT, page) == "(1) one; (2) two; (3) three."


def test_context_after_ends_at_the_next_question() -> None:
    # The reviewer's letter lists Q1 and Q2 before A1 and A2.
    first = "Q1. Is it the case that there are criteria? You state the criteria are:"
    second = "Q2. Is it the case that a drum needs a label?"
    answers = (
        "A1. The answer is no, under § 172.401(a)(2).",
        "A2. The answer is yes, under § 172.400.",
    )
    assert context_after(DRAFT, letter(first, second, *answers)) == ""
    listed = letter(first, "(1) one; (2) two.", second, *answers)
    assert context_after(DRAFT, listed) == "(1) one; (2) two."


def test_context_replaces_a_surname_from_the_salutation() -> None:
    # The page's name fields are empty, so only the salutation names Ms. Roe.
    opening = (
        "This letter is in response to your email. You state that Ms. Roe ships drums"
        " by road."
    )
    page = LetterPage(
        "article",
        None,
        "",
        "",
        ("June 1, 2020", "Dear Ms. Roe:", opening, f"Q1. {QUESTION}", f"A1. {ANSWER}"),
    )
    assert (
        context_before(DRAFT, page) == "You state that Ms. [name] ships drums by road."
    )


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
    got = ticks(draft, page)
    assert (True, 'The answer cites § 171.8 and names "Hazardous waste"') in got


TOXIC = (
    "171.8(Material%20poisonous%20by%20inhalation%20or%20Material%20toxic%20by"
    "%20inhalation)"
)
TOXIC_TEXT = (
    'The answer cites § 171.8 and names "Material poisonous by inhalation or'
    ' Material toxic by inhalation"'
)


@pytest.mark.parametrize(
    "named", ["material poisonous by inhalation", "material toxic by inhalation"]
)
def test_a_two_name_definition_ticks_on_either_name(named: str) -> None:
    answer = f"The answer is yes. The tank holds a {named} as defined in § 171.8."
    page = letter(f"Q1. {QUESTION}", f"A1. {answer}")
    assert (True, TOXIC_TEXT) in ticks(replace(DRAFT, evidence=(TOXIC,)), page)


@pytest.mark.parametrize(
    "cites", ["as defined in 49 CFR 171.8", "as defined in §§ 171.1 and 171.8"]
)
def test_a_definition_ticks_however_the_answer_cites_171_8(cites: str) -> None:
    answer = f"The answer is yes. A hazmat employee, {cites}, must be trained."
    page = letter(f"Q1. {QUESTION}", f"A1. {answer}")
    draft = replace(DRAFT, evidence=("171.8(Hazmat%20employee)",))
    got = ticks(draft, page)
    assert (True, 'The answer cites § 171.8 and names "Hazmat employee"') in got


def test_a_definition_the_answer_does_not_name_gets_no_tick() -> None:
    page = letter(f"Q1. {QUESTION}", "A1. The answer is yes. See § 171.8.")
    draft = replace(DRAFT, evidence=("171.8(Hazmat%20employee)",))
    got = ticks(draft, page)
    assert (False, 'The answer cites § 171.8 and names "Hazmat employee"') in got


def test_a_section_range_member_gets_its_tick() -> None:
    answer = "The answer is yes. See §§ 173.1 through 173.3."
    page = letter(f"Q1. {QUESTION}", f"A1. {answer}")
    draft = replace(DRAFT, evidence=("173.2",))
    got = ticks(draft, page, units=("173.1", "173.2", "173.3"))
    assert (True, "The answer cites 173.2") in got
