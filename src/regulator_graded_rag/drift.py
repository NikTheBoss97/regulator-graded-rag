# Author: Nicola Antonello
"""Whether a cited rule read the same on a letter's day as in the edition (ADR-0007).

A letter's answer holds only if the rules it cites did not change between the letter's
day and the edition's, 1 October 2025. A cited paragraph is compared together with its
subparagraphs, which eCFR nests inside it, and a citation of a whole section compares
the whole section and its footnotes. Figures are compared by their file names. A
paragraph whose content eCFR does not keep inside its div, such as a table placed after
it, or whose id is not on a div, is compared by its whole section (the owner's rulings
of 2026-11-15). A unit or paragraph absent on either day is "missing", and an item
citing it is dropped like a changed one.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal

from regulator_graded_rag.ecfr import (
    EDITION_DAY,
    Cache,
    PageMissing,
    UnitText,
    parse_units,
)

CITATION = re.compile(
    r"(\d{3}\.\d+[a-z]?(?:-\d+)?|\d{3}\.(?:subpt[A-Z]+\.)?app[A-Z])"
    r"((?:\([0-9A-Za-z%.\-]+\))*)"
)
Outcome = Literal["unchanged", "changed", "missing"]


@dataclass(frozen=True, order=True)
class Citation:
    unit: str
    paragraph: str = ""

    @property
    def label(self) -> str:
        return self.unit + self.paragraph


def parse_citation(text: str) -> Citation:
    match = CITATION.fullmatch(text.strip().removeprefix("§").strip())
    if match is None:
        raise ValueError(f"not a citation: {text!r}")
    return Citation(match[1], match[2])


def _whole(unit: UnitText) -> tuple[str, str, tuple[str, ...]]:
    return unit.text, unit.footnotes, unit.figures.get("", ())


def _paragraph(unit: UnitText, label: str) -> tuple[str, tuple[str, ...]] | None:
    text = unit.paragraphs.get(label)
    return None if text is None else (text, unit.figures.get(label, ()))


def compare(
    citation: Citation, then: Mapping[str, UnitText], edition: Mapping[str, UnitText]
) -> Outcome:
    """Text and figures' file names are compared. A paragraph whose content is not all
    inside its own div (loose) is compared by its whole unit, so it can never read
    unchanged while a table that belongs to it changed (owner, 2026-11-15)."""
    a, b = then.get(citation.unit), edition.get(citation.unit)
    if a is None or b is None:
        return "missing"
    label = citation.label
    if not citation.paragraph or label in a.loose or label in b.loose:
        return "unchanged" if _whole(a) == _whole(b) else "changed"
    pa, pb = _paragraph(a, label), _paragraph(b, label)
    if pa is None or pb is None:
        return "missing"
    return "unchanged" if pa == pb else "changed"


def check(
    citations: Iterable[Citation], day: date, cache: Cache
) -> dict[Citation, Outcome]:
    """Each citation's outcome between day and the edition's day.

    A section is read from its own page, an appendix from its part's page. A page eCFR
    does not hold on a day means the unit did not exist then.
    """
    pages: dict[tuple[date, str, str | None], dict[str, UnitText]] = {}

    def units(on: date, part: str, section: str | None) -> dict[str, UnitText]:
        if (on, part, section) not in pages:
            try:
                pages[on, part, section] = parse_units(cache.page(on, part, section))
            except PageMissing:
                pages[on, part, section] = {}
        return pages[on, part, section]

    outcomes: dict[Citation, Outcome] = {}
    for citation in citations:
        part = citation.unit.split(".")[0]
        section = None if ".app" in citation.unit else citation.unit
        outcomes[citation] = compare(
            citation, units(day, part, section), units(EDITION_DAY, part, section)
        )
    return outcomes
