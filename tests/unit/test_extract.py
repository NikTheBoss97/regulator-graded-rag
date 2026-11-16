# Author: Nicola Antonello
from dataclasses import replace
from datetime import date

import pytest

from regulator_graded_rag.extract import (
    Pair,
    direct,
    letter_date,
    mentions_picture,
    pairs,
    verdict,
)
from regulator_graded_rag.letter_page import LetterPage

NUMBERED = (
    "Reference No. 99-0001",
    "Dear Ms. Roe:",
    "We have paraphrased and answered your questions as follows:",
    'Q1. You ask if the "#" symbol may be displayed on your package.',
    'A1. The answer is no. According to § 172.301(a), the number follows "UN".',
    "Q2. You ask whether the 12 mm height applies.",
    "A2. The answer is yes, under § 172.301(a)(1).",
    "Q3. You ask how to mark a package.",
    "A3. Section 172.301 describes the marking.",
    "Q4. You ask whether a tank needs placards.",
    "Sincerely,",
)
SINGLE = (
    "This letter is in response to your email requesting clarification of the HMR.",
    (
        "You state that the bins hold no hazardous materials. You ask whether the bins may"
        " keep the mark."
    ),
    "Yes. In accordance with § 172.303(b)(1), the prohibition does not apply.",
)


def test_numbered_questions_pair_with_their_answers() -> None:
    got = pairs(NUMBERED)
    assert [(p.number, p.numbered) for p in got] == [(1, True), (2, True), (3, True)]
    assert got[0].answer.startswith("The answer is no.")


def test_a_question_without_its_answer_gives_no_pair() -> None:
    assert 4 not in [p.number for p in pairs(NUMBERED)]
    repeated = (
        "Q1. You ask whether X.",
        "A1. Yes.",
        "Q1. You ask whether Y.",
        "A1. No.",
    )
    assert pairs(repeated) == []


def test_a_sentence_starting_with_a_number_is_not_an_answer() -> None:
    # Beyond the plan's list: "A 2.5 kg cylinder" must not read as answer A2.
    paragraphs = ("Q2. You ask whether a cylinder may be used.", "A 2.5 kg cylinder.")
    assert pairs(paragraphs) == []


def test_a_single_unnumbered_question_pairs_with_the_next_paragraph() -> None:
    assert pairs(SINGLE) == [Pair(1, SINGLE[1], SINGLE[2], numbered=False)]


def test_two_unnumbered_questions_give_no_pair() -> None:
    assert pairs((SINGLE[1], SINGLE[2], SINGLE[1], SINGLE[2])) == []


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("The answer is no. According to § 172.301(a), ...", "no"),
        ("The answer is yes, provided the package is marked.", "yes"),
        ("The answer to your question is yes.", "yes"),
        ("Yes. In accordance with § 172.303(b)(1), ...", "yes"),
        ("No; the HMR do not apply.", "no"),
        ("Your understanding is correct.", None),
        ("See answer A1.", None),
        ("In general, the answer is no.", None),
        ("Not necessarily.", None),
    ],
)
def test_only_an_answer_that_starts_with_yes_or_no_has_a_verdict(
    answer: str, expected: str | None
) -> None:
    assert verdict(answer) == expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            'You ask if the "#" symbol may be displayed on your package.',
            'Is it the case that the "#" symbol may be displayed on your package?',
        ),
        (
            "You state that the tank is empty. You ask whether it must be placarded.",
            "You state that the tank is empty. Is it the case that it must be placarded?",
        ),
        (
            "You ask for confirmation that the battery meets § 173.185(b)(5).",
            "Is it the case that the battery meets § 173.185(b)(5)?",
        ),
        (
            (
                "You provide photos of a package and ask whether the marking complies with"
                " § 172.301(a)."
            ),
            (
                "You provide photos of a package. Is it the case that the marking complies"
                " with § 172.301(a)?"
            ),
        ),
        (
            "Specifically, you ask whether the bins may keep the mark.",
            "Is it the case that the bins may keep the mark?",
        ),
        (
            (
                "You ask whether the battery is excepted. In the configuration, cells are"
                " packed apart."
            ),
            (
                "Is it the case that the battery is excepted? In the configuration, cells are"
                " packed apart."
            ),
        ),
        ("May a shipper offer the package?", "May a shipper offer the package?"),
        ("You ask will a nurse tank meet the definition.", None),
        # Beyond the plan's list: an abbreviation is not a sentence's end, and a rule
        # that could garble a question gives none, so the draft is flagged instead.
        (
            "You ask whether the U.S. Department of Transportation requires it.",
            "Is it the case that the U.S. Department of Transportation requires it?",
        ),
        ("You ask whether X is allowed. You further ask whether Y is.", None),
        ("In your letter you ask whether the tank is empty.", None),
        # Two questions in one, as in dev letter 19-0130: the draft is flagged.
        (
            "You ask whether a leg is by vessel and, if so, whether Part 176 applies.",
            None,
        ),
        ("You ask whether X is allowed and, if not, whether Y is.", None),
        (
            "You ask whether a leg is by vessel and—if so—whether Part 176 applies.",
            None,
        ),
        (
            "You ask whether a package if not marked may be shipped.",
            "Is it the case that a package if not marked may be shipped?",
        ),
        # A quoted ending keeps its quote but not its period (dev letter 21-0020);
        # a quotation's own mark, and an abbreviation's period, stay.
        (
            'You ask whether it is an "unsafe condition."',
            'Is it the case that it is an "unsafe condition"?',
        ),
        (
            'You ask whether the label must read "Is it flammable?"',
            'Is it the case that the label must read "Is it flammable?"?',
        ),
        (
            'You ask whether it must bear the word "DANGER!"',
            'Is it the case that it must bear the word "DANGER!"?',
        ),
        (
            'You ask whether it may be marked "MADE IN U.S."',
            'Is it the case that it may be marked "MADE IN U.S."?',
        ),
    ],
)
def test_the_fixed_rule_makes_a_direct_question(
    question: str, expected: str | None
) -> None:
    assert direct(question) == expected


def test_the_letters_own_date_comes_before_the_publish_date() -> None:
    page = LetterPage(
        "article",
        date(2026, 3, 13),
        "",
        "",
        ("March 12, 2026", "Reference No. 25-0059"),
    )
    assert letter_date(page) == (date(2026, 3, 12), "letter")
    undated = replace(page, paragraphs=("Reference No. 25-0059",))
    assert letter_date(undated) == (date(2026, 3, 13), "published")
    assert letter_date(replace(page, publish_date=None, paragraphs=("x",))) == (
        None,
        "none",
    )


def test_pictures_and_samples_are_noticed() -> None:
    assert mentions_picture("You provide photos of the package.")
    assert mentions_picture("x", "a sample bottle")
    assert not mentions_picture("The marking reads UN1993.")
    # What the requester showed or sent, as in dev letters 25-0074 and 25-0087, needs
    # the owner's look too.
    assert mentions_picture("The shipping paper, as shown in your incoming email, x.")
    assert mentions_picture("the test report example included with your email")
    assert not mentions_picture("The placard is the one shown in § 172.555.")


@pytest.mark.parametrize(
    "opening",
    [
        "This is in response to your email",
        "This responds to your letter",
        "This letter is in response to your email",
    ],
)
def test_the_letters_opening_sentence_is_not_part_of_the_question(
    opening: str,
) -> None:
    paragraphs = (
        (
            f"{opening} requesting clarification of the HMR. You ask whether the bins"
            " may keep the mark."
        ),
        "Yes. In accordance with § 172.303(b)(1), the prohibition does not apply.",
    )
    [pair] = pairs(paragraphs)
    assert pair.question == "You ask whether the bins may keep the mark."


@pytest.mark.parametrize(
    "asking",
    [
        # An opening that asks the question itself stays, or no question is left.
        "This responds to your letter in which you ask whether the bins may keep it.",
        # A first sentence that starts with "This" but opens no letter stays.
        "This cylinder holds propane. You ask whether the bins may keep the mark.",
    ],
)
def test_a_first_sentence_that_is_not_the_letters_opening_stays(asking: str) -> None:
    answer = "Yes. In accordance with § 172.303(b)(1), the prohibition does not apply."
    [pair] = pairs((asking, answer))
    assert pair.question == asking


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # Review: a condition before the clause defines the question, so it stays;
        # only a discourse marker such as "Therefore," goes.
        (
            "For an approved explosive, you ask whether it may be shipped.",
            "For an approved explosive, is it the case that it may be shipped?",
        ),
        (
            "Therefore, you ask whether it may be shipped.",
            "Is it the case that it may be shipped?",
        ),
        (
            "In the case of a cylinder, you ask whether it may be shipped.",
            "In the case of a cylinder, is it the case that it may be shipped?",
        ),
        # Starting like a pointer to a letter does not make a phrase one.
        (
            "In your scenario, where the tank is empty, you ask whether it may be shipped.",
            (
                "In your scenario, where the tank is empty, is it the case that it may be"
                " shipped?"
            ),
        ),
        (
            "In connection with shipments by vessel, you ask whether it may be shipped.",
            (
                "In connection with shipments by vessel, is it the case that it may be"
                " shipped?"
            ),
        ),
        # A pointer with more after it is no longer only a pointer, so all of it stays.
        (
            "In your letter about empty tanks, you ask whether it may be shipped.",
            "In your letter about empty tanks, is it the case that it may be shipped?",
        ),
        # A pointer to another question stays: it tells the owner the question leans
        # on that one (dev letter 24-0010).
        (
            "In connection to question Q1, you ask whether it may be shipped.",
            "In connection to question Q1, is it the case that it may be shipped?",
        ),
    ],
)
def test_a_condition_before_the_question_stays(
    question: str, expected: str | None
) -> None:
    assert direct(question) == expected


@pytest.mark.parametrize(
    "pointer",
    [
        "In your most recent letter",  # dev letter 23-0034
        "In your letter",
        "In your email dated May 5, 2019",
    ],
)
def test_a_pointer_to_the_requesters_letter_goes(pointer: str) -> None:
    question = f"{pointer}, you ask whether it may be shipped."
    assert direct(question) == "Is it the case that it may be shipped?"


def test_an_answer_runs_to_the_next_question() -> None:
    # The owner's ruling of 2026-11-16: an answer's later paragraphs belong to it.
    paragraphs = (
        "Q1. You ask whether X is allowed.",
        "A1. The answer is yes. See § 172.301(a).",
        "Thus, under § 180.415, it applies.",
        "Q2. You ask whether Y is allowed.",
        "A2. No.",
        "I hope this information is helpful.",
        "Sincerely,",
    )
    first, second = pairs(paragraphs)
    assert first.answer == (
        "The answer is yes. See § 172.301(a).\nThus, under § 180.415, it applies."
    )
    assert first.continues and not second.continues and second.answer == "No."


def test_a_single_answer_runs_to_the_closing() -> None:
    paragraphs = (
        *SINGLE,
        "Thus, § 172.303(b)(2) applies too.",
        "I hope this information is helpful.",
        "Sincerely,",
    )
    [pair] = pairs(paragraphs)
    assert pair.continues and pair.answer.endswith("applies too.")


@pytest.mark.parametrize(
    "context",
    [
        "You ask about shipments by vessel under §§ 171.23 and 171.25.",
        "Your ask about shipments by vessel under § 171.25.",
        "You describe Product 2 as a gel classed under § 173.120.",
        "You also mention in your request that you ship a bottle under § 173.225.",
    ],
)
def test_an_answer_stops_where_the_requester_speaks_again(context: str) -> None:
    # A paragraph in the requester's voice opens the next question's context, as in
    # dev letter 23-0066, so its citations are not this answer's.
    paragraphs = (
        "Q1. You ask whether X is allowed.",
        "A1. The answer is yes. See § 172.301(a).",
        context,
        "Q2. You ask whether Y is allowed.",
        "A2. No.",
    )
    first, _ = pairs(paragraphs)
    assert first.answer == "The answer is yes. See § 172.301(a)."
    assert not first.continues


@pytest.mark.parametrize(
    "advice",
    [
        "You may use the ERG under § 172.602(b)(3)(iii).",
        "You should be aware that § 175.10 also applies.",
        "You are free to follow § 173.24 voluntarily.",
    ],
)
def test_phmsas_advice_to_the_requester_stays_in_the_answer(advice: str) -> None:
    paragraphs = (*SINGLE, advice, "I hope this information is helpful.")
    [pair] = pairs(paragraphs)
    assert pair.continues and pair.answer.endswith(advice)
