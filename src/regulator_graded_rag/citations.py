# Author: Nicola Antonello
"""The sections an answer cites, as evidence labels, and the item's type (ADR-0021).

A citation is read only after a marker ("§", "§§", "Section", "49 CFR"), as one of
"paragraph (b) of § 173.24", or as an appendix ("Appendix B to Part 172"). A list after a
marker keeps its sections ("§§ 172.504 and 172.516") and its paragraphs of one section
("§§ 173.24(b) and (c)"). A range gives every member: paragraphs along the CFR's levels
((a), (1), (i), (A)), sections in the corpus's order. A bare paragraph after a deeper one
replaces the level of its kind, so "§ 173.115(b)(1) and (2)" gives (b)(2). Sections of
Parts 171-180 become labels in the gold format;
other parts' citations are kept as written, since an answer citing only those makes an
unanswerable item. A §171.8 citation whose sentence names a definition becomes eCFR's key
for that definition, so the drift check compares that definition alone (owner,
2026-11-16).
"""

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from urllib.parse import unquote

from regulator_graded_rag.ecfr import UnitText
from regulator_graded_rag.review import Record

# A hyphenated section such as 178.345-1, but not the hyphen of 178.69-178.71.
_REST = r"\d+[a-z]?(?:-\d+(?!\d|\.\d))?"
_SECTION = rf"(\d{{3}})\.({_REST})"
_CHAIN = r"(?:\([0-9A-Za-z]+\))+"
_LIST_SEP = r"(?:,\s*(?:(?:and|or)\s+)?|(?:and|or)\s+)"
_RANGE_SEP = r"(?:[-–—]|through)\s*"
_MARKER = re.compile(r"§§?|\bsections?\b|\b49\s*CFR\b(?:\s*§§?)?", re.IGNORECASE)
_STEP = re.compile(
    rf"\s*(?:(?P<range>{_RANGE_SEP})|{_LIST_SEP})?"
    rf"(?:(?P<part>\d{{3}})\.(?P<rest>{_REST})(?P<chain>{_CHAIN})?|(?P<bare>{_CHAIN}))",
    re.IGNORECASE,
)
_PARAGRAPH_OF = re.compile(
    rf"\bparagraphs?\s+({_CHAIN}(?:\s*(?:{_RANGE_SEP}|{_LIST_SEP})\s*{_CHAIN})*)\s+of\s+"
    rf"(?:§§?\s*|section\s+)?{_SECTION}",
    re.IGNORECASE,
)
_DESIGNATOR = re.compile(r"\(([0-9A-Za-z]+)\)")
# The CFR's paragraph levels: (a), (1), (i), (A), then (1) and (i) again in italics.
_LEVEL_KINDS = ("lower", "digit", "roman", "upper", "digit", "roman")
_ROMAN = re.compile(r"(?=[ivxl]+$)(?:xl|l?x{0,3})(?:ix|iv|v?i{0,3})")
_NUMERALS = ((40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"))
_LONGEST_RANGE = 30
_APPENDIX = re.compile(
    r"\bappendix\s+([A-Z])\s+to\s+(?:subpart\s+([A-Z])\s+of\s+)?part\s+(\d{3})\b",
    re.IGNORECASE,
)
_PART = re.compile(r"\bparts?\s+(\d{3})\b(?!\s*[-–]\s*\d)", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.;])\s+")
_KEY_CHARACTERS = re.compile(r"[^0-9A-Za-z .\-]")
DEFINITIONS_UNIT = "171.8"

# Where a sentence citing §171.8 names the definition it means, measured on the dev
# letters on 2026-11-16. A quoted term in any of these slots counts; an unquoted one
# counts only when eCFR defines it, since nothing else marks where it ends.
_ARTICLE = r"(?:(?:a|an|the)\s+)?"
_QUOTE = r"[\"“]([^\"”]+)[\"”]"
_CITED = r"(?:§\s*|section\s+)171\.8\b(?:\s+of\s+the\s+HMR)?"
_TERM_AFTER = re.compile(
    r"\bdefinitions?\s+of\s+"
    + _ARTICLE
    + r"|\bthe\s+term\s+"
    + r"|\bdefines\s+"
    + _ARTICLE
    + r"|\b(?:as\s+(?:currently\s+)?defined\s+in|in\s+accordance\s+with)\s+"
    + _CITED
    + r",\s*"
    + _ARTICLE,
    re.IGNORECASE,
)
_TERM_BEFORE = re.compile(
    r",?\s+(?:is|are)\s+defined\b|,?\s+as\s+(?:currently\s+)?defined\b"
    r"|\s*(?:[—–]|\(\s*see\b)\s*(?:see\s+|defined\s+in\s+)?(?:§|section)",
    re.IGNORECASE,
)
_QUOTED_AFTER = re.compile(
    _QUOTE + r"(?:\s*(?:,|and|or)\s*" + _ARTICLE + _QUOTE + r")*"
)
_KNOWN: dict[tuple[str, ...], re.Pattern[str]] = {}


def _known(definitions: Mapping[str, str]) -> re.Pattern[str]:
    """One pattern for every defined term, longest first, compiled once per table."""
    terms = tuple(sorted(definitions, key=len, reverse=True))
    if terms not in _KNOWN:
        alternatives = "|".join(re.escape(term) for term in terms) or r"(?!)"
        _KNOWN[terms] = re.compile(rf"(?:{alternatives})\b", re.IGNORECASE)
    return _KNOWN[terms]


def _named_terms(sentence: str, definitions: Mapping[str, str]) -> list[str]:
    """The definitions a sentence names, by the slots above."""
    known = _known(definitions)
    terms: list[str] = []
    for slot in _TERM_AFTER.finditer(sentence):
        if quoted := _QUOTED_AFTER.match(sentence, slot.end()):
            terms += re.findall(_QUOTE, quoted[0])
        elif term := known.match(sentence, slot.end()):
            terms.append(term[0])
    for slot in _TERM_BEFORE.finditer(sentence):
        before = sentence[: slot.start()].rstrip()
        if before.endswith(('"', "”")):
            opening = max(before.rfind('"', 0, -1), before.rfind("“"))
            if opening >= 0:
                terms.append(before[opening + 1 : -1])
            continue
        for start in range(max(0, len(before) - 80), len(before)):
            if (start == 0 or not before[start - 1].isalnum()) and known.fullmatch(
                before, start
            ):
                terms.append(before[start:])
                break
    # A quoted term eCFR defines counts wherever it stands in the sentence.
    terms += [
        quoted
        for quoted in re.findall(_QUOTE, sentence)
        if quoted.strip(" ,.;:").lower() in definitions
    ]
    return list(dict.fromkeys(term.strip(" ,.;:") for term in terms))


@dataclass(frozen=True)
class Cited:
    corpus: tuple[str, ...]
    outside: tuple[str, ...]


def _in_corpus(part: str) -> bool:
    return 171 <= int(part) <= 180


def _kinds(token: str) -> frozenset[str]:
    """The paragraph levels a designator can be: "i" is a letter or a roman numeral."""
    if token.isdigit():
        return frozenset({"digit"})
    if len(token) == 1 and token.isupper():
        return frozenset({"upper"})
    kinds = {"lower"} if len(token) == 1 and token.islower() else set()
    if _ROMAN.fullmatch(token):
        kinds.add("roman")
    return frozenset(kinds)


def _kind_at(level: int) -> str:
    return _LEVEL_KINDS[level % len(_LEVEL_KINDS)]


def _attach(chain: list[str], tokens: list[str]) -> list[str] | None:
    """A bare designator after a chain replaces the deepest level of its kind, or
    continues the chain one level down; None when it can do neither."""
    kinds = _kinds(tokens[0])
    for level in range(len(chain) - 1, -1, -1):
        if _kind_at(level) in kinds:
            return chain[:level] + tokens
    return chain + tokens if _kind_at(len(chain)) in kinds else None


def _roman_value(token: str) -> int:
    values = {"i": 1, "v": 5, "x": 10, "l": 50}
    total = 0
    for i, letter in enumerate(token):
        later = values[token[i + 1]] if i + 1 < len(token) else 0
        total += -values[letter] if values[letter] < later else values[letter]
    return total


def _roman(value: int) -> str:
    numeral = ""
    for size, letters in _NUMERALS:
        while value >= size:
            numeral, value = numeral + letters, value - size
    return numeral


def _sequence(start: str, end: str, kind: str) -> list[str]:
    """The designators from start to end of one level, inclusive; empty when the two do
    not make a range."""
    if kind == "digit":
        values = [str(n) for n in range(int(start), int(end) + 1)]
    elif kind == "roman":
        values = [_roman(n) for n in range(_roman_value(start), _roman_value(end) + 1)]
    else:
        values = [chr(n) for n in range(ord(start), ord(end) + 1)]
    return values if 1 < len(values) <= _LONGEST_RANGE else []


def _paragraph_range(chain: list[str], tokens: list[str]) -> list[list[str]]:
    """The chains of a range from chain to tokens, without its start: "(ii)-(vii)"
    after (g)(2)(ii) gives (g)(2)(iii) to (g)(2)(vii)."""
    end = _attach(chain, tokens)
    if end is None:
        return []
    differ = [level for level, (a, b) in enumerate(zip(chain, end)) if a != b]
    if len(end) != len(chain) or differ != [len(end) - 1]:
        return [end]
    values = _sequence(chain[-1], end[-1], _kind_at(len(end) - 1))
    return [chain[:-1] + [value] for value in values[1:]] or [end]


def _section_range(start: str, end: str, units: Sequence[str]) -> list[str]:
    """The sections of a range after start, in the corpus's order."""
    if start in units and end in units:
        i, j = units.index(start), units.index(end)
        if 0 < j - i <= _LONGEST_RANGE:
            return list(units[i + 1 : j + 1])
    return [end]


def _label(section: str, chain: Sequence[str]) -> str:
    return section + "".join(f"({token})" for token in chain)


def _walk(text: str, position: int, units: Sequence[str]) -> list[str]:
    """The labels of the list that starts at position."""
    labels: list[str] = []
    section, chain = "", list[str]()
    while step := _STEP.match(text, position):
        ranged = step["range"] is not None
        if step["part"]:
            target = f"{step['part']}.{step['rest']}"
            tokens = _DESIGNATOR.findall(step["chain"] or "")
            if ranged and section and not chain and not tokens:
                labels += _section_range(section, target, units)
            else:
                labels.append(_label(target, tokens))
            section, chain = target, tokens
        elif section:
            tokens = _DESIGNATOR.findall(step["bare"])
            if ranged:
                found = _paragraph_range(chain, tokens)
            else:
                attached = _attach(chain, tokens)
                found = [] if attached is None else [attached]
            if not found:
                break
            labels += [_label(section, each) for each in found]
            chain = found[-1]
        else:
            break
        position = step.end()
    return labels


def _labels(text: str, units: Sequence[str] = ()) -> list[str]:
    """Every section label the text cites, in order, of any part."""
    labels: list[str] = []
    taken: list[tuple[int, int]] = []
    for match in _PARAGRAPH_OF.finditer(text):
        labels += _walk(f"{match[2]}.{match[3]}{match[1]}", 0, units)
        taken.append(match.span())
    for marker in _MARKER.finditer(text):
        if not any(start <= marker.start() < end for start, end in taken):
            labels += _walk(text, marker.end(), units)
    return labels


def _key(term: str, definitions: Mapping[str, str]) -> str:
    known = definitions.get(term.lower())
    if known is not None:
        return known
    cleaned = " ".join(_KEY_CHARACTERS.sub("", term).split())
    return (cleaned[:1].upper() + cleaned[1:]).replace(" ", "%20")


def _definitions_named(text: str, definitions: Mapping[str, str]) -> list[str]:
    """The §171.8 definitions named in sentences that cite §171.8, as labels."""
    labels: list[str] = []
    for sentence in _SENTENCE_END.split(text):
        if DEFINITIONS_UNIT in _labels(sentence):
            keys = [
                _key(term, definitions) for term in _named_terms(sentence, definitions)
            ]
            labels += [f"{DEFINITIONS_UNIT}({key})" for key in keys if key]
    return labels


def cite(text: str, definitions: Mapping[str, str], units: Sequence[str] = ()) -> Cited:
    """The text's citations: labels in Parts 171-180, and the others as written. units,
    the corpus's units in order, lets a range of sections give every member."""
    corpus: set[str] = set()
    outside: set[str] = set()
    for label in _labels(text, units):
        (corpus if _in_corpus(label.split(".")[0]) else outside).add(label)
    named = _definitions_named(text, definitions)
    if named:
        corpus.discard(DEFINITIONS_UNIT)
        corpus.update(named)
    for match in _APPENDIX.finditer(text):
        subpart = f"subpt{match[2].upper()}." if match[2] else ""
        label = f"{match[3]}.{subpart}app{match[1].upper()}"
        (corpus if _in_corpus(match[3]) else outside).add(label)
    for match in _PART.finditer(text):
        if not _in_corpus(match[1]):
            outside.add(f"Part {match[1]}")
    return Cited(tuple(sorted(corpus)), tuple(sorted(outside)))


def definitions(edition: Mapping[str, UnitText]) -> dict[str, str]:
    """The edition's §171.8 definitions: each key's term, lower-case with spaces, mapped
    to the key as eCFR writes it ("hazmat employee" to "Hazmat%20employee"). A key
    naming two terms ("Gross weight or Gross mass") answers to each, unless that name is
    a key of its own or names two keys."""
    unit = edition.get(DEFINITIONS_UNIT)
    if unit is None:
        return {}
    prefix = f"{DEFINITIONS_UNIT}("
    terms: dict[str, str] = {}
    either: defaultdict[str, set[str]] = defaultdict(set)
    for key in unit.paragraphs:
        inner = key.removeprefix(prefix)
        if key.startswith(prefix) and inner.endswith(")") and "(" not in inner:
            term = inner[:-1]
            terms[unquote(term).lower()] = term
            names = re.split(r"\s+or\s+", unquote(term))
            for name in names if len(names) > 1 else ():
                either[name.lower()].add(term)
    for name, keys in either.items():
        if name not in terms and len(keys) == 1:
            terms[name] = next(iter(keys))
    return terms


def table_units(passages: Iterable[Record]) -> frozenset[str]:
    """The units whose table-row passages outnumber their text passages."""
    rows: Counter[str] = Counter()
    texts: Counter[str] = Counter()
    for passage in passages:
        unit = passage["id"].rsplit(":", 1)[0]
        (rows if passage["kind"] == "row" else texts)[unit] += 1
    return frozenset(unit for unit, n in rows.items() if n > texts[unit])


def item_type(cited: Cited, tables: AbstractSet[str]) -> str:
    """The first type that applies: unanswerable, table, multi_passage, lookup."""
    if not cited.corpus:
        return "unanswerable"
    units = {label.split("(")[0] for label in cited.corpus}
    if units & tables:
        return "table"
    return "multi_passage" if len(units) >= 2 else "lookup"
