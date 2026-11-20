# Author: Nicola Antonello
"""A letter's questions, paired with their answers, by fixed rules (ADR-0007, ADR-0021).

PHMSA paraphrases each question it answers. A numbered question ("Q1. …") pairs with the
answer of the same number ("A1. …"); a letter with no numbered question may hold one
question ("You ask whether …"), answered by the paragraph after it. A pair counts only
when its answer starts with yes or no. The question becomes a direct one by a single
fixed rule, never a model: its asking clause becomes "Is it the case that", and that
sentence ends with "?". PHMSA's other words stay as written.
"""

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from regulator_graded_rag.letter_page import LetterPage

EXTRACTOR = "2"
Verdict = Literal["yes", "no"]
DateSource = Literal["letter", "published", "none"]

_QUESTION = re.compile(r"^\s*(?:Q\s?|Question\s+)(\d+)\s*[.:)](?!\d)\s*", re.IGNORECASE)
_ANSWER = re.compile(r"^\s*(?:A|Answer\s+)(\d+)\s*[.:)](?!\d)\s*", re.IGNORECASE)
_VERDICT = re.compile(
    r"^\s*(?:the\s+answer(?:\s+to\s+your\s+question)?\s+is\s+)?(yes|no)\b",
    re.IGNORECASE,
)
_YOU_ASK = re.compile(
    r"\byou\s+(?:also\s+|further\s+)?(?:ask|asked|inquire|inquired)\s+"
    r"(?:for\s+(?:additional\s+)?(?:clarification|confirmation)\s+(?:as\s+to\s+)?)?"
    r"(?:whether|if|that)\s+",
    re.IGNORECASE,
)
_AND_ASK = re.compile(r"\s+and\s+(?:also\s+)?ask\s+(?:whether|if)\s+", re.IGNORECASE)
# "X and, if so, whether Y", "…and, if not, …" or "…and—if so—…" asks a second
# question, which the yes or no may not answer.
_IF_SO = re.compile(r"\bif (?:so|not)\s*[,—–]", re.IGNORECASE)
_RESPONSE = re.compile(
    r"^This (?:letter )?(?:is in response to|responds to)\b", re.IGNORECASE
)
# The paragraphs that end an answer's last paragraphs: the letter's closing.
_CLOSING = re.compile(
    r"^\s*(?:I hope (?:that )?this information|If you have (?:any )?(?:further |"
    r"additional )?questions|If we can be of further|Please (?:contact|do not hesitate|"
    r"feel free)|Sincerely|Thank you for)",
    re.IGNORECASE,
)
# A later paragraph in the requester's voice ("You ask about…", "You describe…") opens
# the next question's context, so the answer before it has ended. PHMSA's own advice
# to the requester ("You may…", "You should…") stays in the answer.
_CONTEXT = re.compile(
    r"^\s*(?:your\s+ask|you\s+(?:also\s+|further\s+)?(?:ask(?:ed)?|described?|"
    r"mention(?:ed)?|noted?|stated?|indicated?|explain(?:ed)?|request(?:ed)?|"
    r"provided?|inquired?|wr(?:ite|ote)))\b",
    re.IGNORECASE,
)
# Words before a "you ask" clause that only join it to the text before. Any other
# comma-ended phrase, except a pointer to the requester's letter (_FRAMING), is a
# condition of the question and stays.
_DISCOURSE = frozenset(
    {
        "specifically",
        "therefore",
        "thus",
        "accordingly",
        "consequently",
        "finally",
        "lastly",
        "first",
        "second",
        "third",
        "next",
        "also",
        "further",
        "furthermore",
        "additionally",
        "moreover",
        "in addition",
    }
)
# A phrase that is only a pointer to the requester's letters frames the question, so
# it goes too: "In your most recent letter,", "In your email dated May 5, 2019,". The
# whole phrase must be the pointer, so a condition after it stays; a pointer to another
# question stays as well, since it tells the owner the question leans on that one.
_FRAMING = re.compile(
    r"in your (?:[\w-]+ ){0,3}(?:letter|e-?mail|request|inquiry|correspondence|"
    r"message)s?(?: dated [\w ]+ \d{1,2}, \d{4})?",
    re.IGNORECASE,
)
_PICTURE = re.compile(
    r"\b(?:pictures?|photo\w*|images?|attach\w*|enclos\w*|samples?|drawings?|"
    r"diagrams?|illustrat\w*|videos?|shown (?:in|on) your|included with your)\b",
    re.IGNORECASE,
)
# A sentence ends at ".", "?" or "!" (perhaps before a closing quote) followed by a
# space and a capital, a quote or "§"; these abbreviations end no sentence.
_BOUNDARY = re.compile(r"(?:(?<=[.?!])|(?<=[.?!][\"”’]))\s+(?=[A-Z\"“§])")
_ABBREVIATIONS = (
    "U.S.",
    "Mr.",
    "Ms.",
    "Mrs.",
    "Dr.",
    "Inc.",
    "Co.",
    "Corp.",
    "Ltd.",
    "St.",
    "Jr.",
    "Sr.",
    "e.g.",
    "i.e.",
    "vs.",
    "Ref.",
)


@dataclass(frozen=True)
class Pair:
    number: int
    question: str
    answer: str  # its paragraphs, joined by newlines
    numbered: bool
    continues: bool = False  # the answer has paragraphs after its first


def _sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for part in _BOUNDARY.split(text.strip()):
        if sentences and sentences[-1].endswith(_ABBREVIATIONS):
            sentences[-1] += " " + part
        else:
            sentences.append(part)
    return sentences


def asks(text: str) -> int:
    """How many asking clauses the text holds."""
    return len(_YOU_ASK.findall(text)) + len(_AND_ASK.findall(text))


def verdict(answer: str) -> Verdict | None:
    """yes or no when the answer starts with one, by the strict forms; otherwise None."""
    match = _VERDICT.match(answer)
    if match is None:
        return None
    return "yes" if match[1].lower() == "yes" else "no"


def _following(paragraphs: Sequence[str], start: int) -> list[str]:
    """The paragraphs after paragraphs[start] that still belong to its answer: up to
    the next question or answer, the requester's own words, or the letter's closing
    (owner, 2026-11-16)."""
    following: list[str] = []
    for paragraph in paragraphs[start + 1 :]:
        if (
            _QUESTION.match(paragraph)
            or _ANSWER.match(paragraph)
            or _CONTEXT.match(paragraph)
            or _CLOSING.match(paragraph)
        ):
            break
        following.append(paragraph)
    return following


def pairs(paragraphs: Sequence[str]) -> list[Pair]:
    """The letter's question and answer pairs. A numbered question without its answer,
    or a number used twice, gives no pair; a letter with no numbered question gives its
    one asking paragraph and the answer after it, when that answer has a verdict. An
    answer runs from its first paragraph to the next question, the requester's own
    words, or the closing."""
    questions: defaultdict[int, list[str]] = defaultdict(list)
    answers: defaultdict[int, list[tuple[int, str]]] = defaultdict(list)
    for index, paragraph in enumerate(paragraphs):
        if match := _QUESTION.match(paragraph):
            questions[int(match[1])].append(paragraph[match.end() :].strip())
        elif match := _ANSWER.match(paragraph):
            answers[int(match[1])].append((index, paragraph[match.end() :].strip()))
    if questions:
        found: list[Pair] = []
        for number, asked in sorted(questions.items()):
            given = answers.get(number, [])
            if len(asked) == 1 and len(given) == 1:
                index, first = given[0]
                more = _following(paragraphs, index)
                answer = "\n".join([first, *more])
                found.append(Pair(number, asked[0], answer, True, bool(more)))
        return found
    asking = [i for i, paragraph in enumerate(paragraphs) if asks(paragraph)]
    if len(asking) != 1 or asking[0] + 1 >= len(paragraphs):
        return []
    first = paragraphs[asking[0] + 1]
    if verdict(first) is None:
        return []
    more = _following(paragraphs, asking[0] + 1)
    sentences = _sentences(paragraphs[asking[0]])
    # The letter's opening sentence goes, unless it asks the question itself.
    if sentences and _RESPONSE.match(sentences[0]) and not asks(sentences[0]):
        sentences = sentences[1:]
    answer = "\n".join([first, *more])
    return [Pair(1, " ".join(sentences), answer, False, bool(more))]


def direct(question: str) -> str | None:
    """The question as a direct question, by the fixed rule; None when no rule applies,
    or when the text holds more than one asking clause or a second question ("…and, if
    so, whether…"), or words before a "you ask" clause that do not end in a comma. A
    discourse marker before the clause goes, as does a pointer to the requester's
    letter; any other comma-ended phrase is a condition and stays ("For X, is it the
    case that Y?")."""
    sentences = _sentences(question)
    count = asks(question)
    if count != 1 or _IF_SO.search(question):
        if count == 0 and question.rstrip().endswith("?"):
            return question
        return None
    for i, sentence in enumerate(sentences):
        you = _YOU_ASK.search(sentence)
        joined = _AND_ASK.search(sentence)
        if you is None and joined is None:
            continue
        match = you or joined
        assert match is not None
        before = sentence[: match.start()].strip()
        asked = sentence[match.end() :].rstrip()
        # The closing period goes, even inside a closing quote ('an "X."' ends 'an
        # "X"?'), but a quotation's own "?" or "!" and an abbreviation's period stay.
        if not asked.rstrip('"”’').endswith(_ABBREVIATIONS):
            asked = re.sub(r"\.(?=[\"”’]$)|[.?!]+$", "", asked).rstrip()
        if you is not None:
            if before and not before.endswith(","):
                return None
            phrase = before[:-1].strip()
            if (
                before
                and phrase.lower() not in _DISCOURSE
                and not _FRAMING.fullmatch(phrase)
            ):
                rewritten = f"{before} is it the case that {asked}?"
            else:
                rewritten = f"Is it the case that {asked}?"
        else:
            rewritten = f"{before}. Is it the case that {asked}?"
        return " ".join([*sentences[:i], rewritten, *sentences[i + 1 :]])
    return None


def letter_date(page: LetterPage) -> tuple[date | None, DateSource]:
    """The letter's own date, its first line, then the page's publish date."""
    if page.paragraphs:
        try:
            return datetime.strptime(page.paragraphs[0].strip(), "%B %d, %Y").date(), (
                "letter"
            )
        except ValueError:
            pass
    if page.publish_date is not None:
        return page.publish_date, "published"
    return None, "none"


def mentions_picture(*texts: str) -> bool:
    """Whether any text mentions a picture, photo, image, attachment, enclosure, sample,
    drawing, diagram, illustration or video, or something the requester showed or sent
    ("shown in your…", "included with your…"), for the owner to judge."""
    return any(_PICTURE.search(text) for text in texts)
