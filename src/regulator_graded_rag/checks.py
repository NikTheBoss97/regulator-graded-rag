# Author: Nicola Antonello
"""What the owner must judge in each gold-question draft, by fixed rules (ADR-0022).

A draft with no reason is accepted by code and covered by a random audit; a draft with
one or more goes to the owner, each with what to look at. The reasons are cheap, shallow
patterns: they find drafts to look at, and decide nothing. The letter's own paragraphs
give the draft's context, scrubbed of the page's names.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from regulator_graded_rag.citations import cite
from regulator_graded_rag.drafts import Draft
from regulator_graded_rag.extract import (
    _ANSWER,
    _QUESTION,
    _RESPONSE,
    Pair,
    _sentences,
    asks,
    mentions_picture,
    pairs,
    verdict,
)
from regulator_graded_rag.letter_page import LetterPage
from regulator_graded_rag.scrub import scrub

CHECKS: Final = "1"

_ASKS = {
    "no letter": (
        "The letter's page is missing or unreadable: check the draft against the"
        " letter in the archive."
    ),
    "unanswerable": (
        "Search the corpus first. If nothing in Parts 171-180 answers the question,"
        " write what you searched under Evidence and save the edit; if something does,"
        " reject it."
    ),
    "shown": "Does the verdict depend on something shown or sent? If so, reject.",
    "document": (
        "The answer names another document. Does the verdict depend on it? If so,"
        " reject."
    ),
    "outside the corpus": (
        "The answer also cites rules outside Parts 171-180: {outside}. Is the deciding"
        " rule in Parts 171-180? If not, reject."
    ),
    "answer continues": (
        "The answer's later paragraphs add citations: keep only those of PHMSA's"
        " answer to this question."
    ),
    "colon": (
        "The question ends with a colon: add the letter's next paragraph, or reject."
    ),
    "pointer": (
        "The question points at something it does not say: add the letter's context,"
        " or reject."
    ),
    "name": "The question holds a name from the letter: remove it.",
    "not rewritten": (
        "No fixed rule rewrote the question: check that it reads as a question on its"
        " own."
    ),
    "known difference": (
        "eCFR's text differs from the edition's for a cited section: compare the cited"
        " paragraphs by eye."
    ),
    "date from the publish field": (
        "The letter's first line is not a date, so its publish date is used: confirm"
        " it."
    ),
    "scrubbed": "Names, emails or phone numbers were removed: check that none is left.",
}
# The flags that are reasons themselves, in the order the owner reads them.
_FLAG_KINDS = (
    "not rewritten",
    "known difference",
    "date from the publish field",
    "scrubbed",
)
_SENT = re.compile(
    r"\b(?:you|requester)\s+(?:also\s+)?(?:provide[ds]?|sent|send|enclose[ds]?|"
    r"attach(?:ed)?|submit(?:ted)?)\b[^.?!]{0,80}?\bexamples?\b"
    r"|\bexamples?\b[^.?!]{0,40}?\b(?:you\s+)?(?:provided|sent|enclosed|attached|"
    r"submitted)\b",
    re.IGNORECASE,
)
_DOCUMENT = re.compile(
    r"\bspecial\s+permits?\b|\bDOT-SP\b|\bSP[-\s]?\d|\bapprovals?\b"
    r"|\bletters?\s+of\s+interpretation\b|\breference\s+(?:no\.?|numbers?)"
    r"|\bexemptions?\b",
    re.IGNORECASE,
)
_POINTER = re.compile(
    r"\b(?:these|those|this|such(?!\s+as\b)|said|the\s+above|aforementioned)\b"
    r"|\byour\s+(?:scenario|situation|example|configuration|design|proposal|"
    r"procedure|process)\b",
    re.IGNORECASE,
)
_SALUTATION = re.compile(r"^\s*Dear\b")
_TITLED = re.compile(r"\b(?:Mr|Ms|Mrs|Dr)\.?\s+([A-Z][\w'’-]+)")
_MESSRS = re.compile(r"\bMessrs\.?\s+([^:]+)")
_NAME_WORD = re.compile(r"[A-Z][\w'’-]*")
_OPENING = re.compile(r"^This (?:letter|is in response|responds)\b")
_DEFINITION = re.compile(r"171\.8\((.+)\)")
_SECTION_171_8 = re.compile(r"(?:§§?|\bsections?)\s*171\.8\b", re.IGNORECASE)
_CLARIFYING = re.compile(r"\bclarification\b|\bparaphrased\b", re.IGNORECASE)


@dataclass(frozen=True)
class Reason:
    kind: str
    ask: str
    sentence: str = ""


def pair_of(draft: Draft, page: LetterPage) -> Pair | None:
    """The letter's pair whose number is the draft's."""
    return next((p for p in pairs(page.paragraphs) if p.number == draft.number), None)


def opening(page: LetterPage) -> str:
    """The paragraph that starts "This letter", "This is in response" or "This
    responds", or an empty string."""
    return next((p for p in page.paragraphs if _OPENING.match(p)), "")


def _scrubbed(text: str, page: LetterPage) -> str:
    return scrub(text, page.company, page.individual).text


def _kept(sentences: list[str]) -> list[str]:
    """The sentences that state facts: not the response sentence, an asking clause, a
    request for clarification, a "paraphrased" sentence or a lead-in ending in a colon."""
    return [
        s
        for s in sentences
        if not (
            _RESPONSE.match(s)
            or asks(s)
            or _CLARIFYING.search(s)
            or s.rstrip().endswith(":")
        )
    ]


def context_before(draft: Draft, page: LetterPage) -> str:
    """The requester's facts from the letter's opening, scrubbed; when the opening ends
    with a colon, the paragraphs after it up to the first question as well."""
    start = next((i for i, p in enumerate(page.paragraphs) if _OPENING.match(p)), None)
    if start is None:
        return ""
    taken = [page.paragraphs[start]]
    if taken[0].rstrip().endswith(":"):
        for paragraph in page.paragraphs[start + 1 :]:
            if _QUESTION.match(paragraph):
                break
            taken.append(paragraph)
    texts = (" ".join(_kept(_sentences(paragraph))) for paragraph in taken)
    return _scrubbed("\n".join(text for text in texts if text), page)


def context_after(draft: Draft, page: LetterPage) -> str:
    """The paragraphs between the draft's question and its answer, scrubbed."""
    paragraphs = page.paragraphs
    asked = next(
        (i for i, p in enumerate(paragraphs) if _number(_QUESTION, p) == draft.number),
        None,
    )
    given = next(
        (i for i, p in enumerate(paragraphs) if _number(_ANSWER, p) == draft.number),
        None,
    )
    if asked is None or given is None or given <= asked:
        return ""
    return _scrubbed("\n".join(paragraphs[asked + 1 : given]), page)


def _number(pattern: re.Pattern[str], paragraph: str) -> int | None:
    match = pattern.match(paragraph)
    return int(match[1]) if match else None


def _sentence_matching(pattern: re.Pattern[str], text: str) -> str | None:
    return next((s for s in _sentences(text) if pattern.search(s)), None)


def _surnames(page: LetterPage) -> list[str]:
    """The names to keep out of a question: every surname of the salutation, the
    requester's last name and the company, longest check first."""
    names: list[str] = []
    salutation = next((p for p in page.paragraphs if _SALUTATION.match(p)), "")
    names += _TITLED.findall(salutation)
    if messrs := _MESSRS.search(salutation):
        names += _NAME_WORD.findall(messrs[1])
    last = page.individual.split()[-1].strip(".,") if page.individual.split() else ""
    if len(last) >= 3:
        names.append(last)
    if page.company.strip():
        names.append(page.company.strip())
    return list(dict.fromkeys(names))


def _named(question: str, page: LetterPage) -> str | None:
    for name in _surnames(page):
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", question):
            return name
    return None


def reasons(draft: Draft, page: LetterPage | None) -> list[Reason]:
    """Every reason the owner must look at the draft, in a fixed order, at most one per
    kind. A draft with none is accepted by code and covered by the audit."""
    pair = pair_of(draft, page) if page is not None else None
    question = draft.question or (pair.question if pair else "")
    answer = pair.answer if pair else ""
    found: list[Reason] = []

    def add(kind: str, sentence: str = "") -> None:
        ask = _ASKS[kind].format(outside=", ".join(draft.outside))
        found.append(Reason(kind, ask, sentence))

    if page is None:
        add("no letter")
    if draft.type == "unanswerable":
        add("unanswerable")
    if "picture" in draft.flags or mentions_picture(question, answer):
        add("shown")
    elif sent := _sentence_matching(_SENT, question) or _sentence_matching(
        _SENT, answer
    ):
        add("shown", sent)
    if document := _sentence_matching(_DOCUMENT, question) or _sentence_matching(
        _DOCUMENT, answer
    ):
        add("document", document)
    if "outside the corpus" in draft.flags:
        add("outside the corpus")
    if "answer continues" in draft.flags:
        add("answer continues")
    if question.rstrip().endswith(":"):
        add("colon")
    if len(_sentences(question)) == 1 and (pointer := _POINTER.search(question)):
        add("pointer", pointer[0])
    if page is not None and (name := _named(question, page)):
        add("name", name)
    found += [Reason(k, _ASKS[k]) for k in _FLAG_KINDS if k in draft.flags]
    return found


def _cited(label: str, cited: Sequence[str], answer: str) -> bool:
    """Whether the answer cites the label. A definition label, "171.8(Term)", needs the
    answer to cite § 171.8 and hold the term (the key's "%20" read as spaces)."""
    if label in cited:
        return True
    match = _DEFINITION.fullmatch(label)
    if match is None:
        return False
    term = match[1].replace("%20", " ").lower()
    return bool(_SECTION_171_8.search(answer)) and term in answer.lower()


def ticks(
    draft: Draft, page: LetterPage | None, units: Sequence[str] = ()
) -> list[tuple[bool, str]]:
    """What code confirmed about the draft, each with whether it holds: the verdict,
    every evidence label in the answer, and that the question holds no name. units, the
    corpus's units in order, lets a range of sections give every member."""
    if page is None:
        return []
    pair = pair_of(draft, page)
    checked: list[tuple[bool, str]] = []
    if draft.type != "unanswerable":
        first = _sentences(pair.answer)[0] if pair else ""
        said = verdict(pair.answer) if pair else None
        checked.append((said == draft.answer, f'PHMSA\'s answer starts "{first}"'))
        cited = cite(pair.answer, {}, units).corpus if pair else ()
        text = pair.answer if pair else ""
        checked += [
            (_cited(label, cited, text), f"The answer cites {label}")
            for label in draft.evidence
        ]
    question = draft.question or (pair.question if pair else "")
    checked.append((_named(question, page) is None, "The question holds no name"))
    return checked
