# Author: Nicola Antonello
"""Split the regulation's sections and appendices into passages (ADR-0006, ADR-0017).

A text passage holds whole paragraphs of one unit, at most LIMIT words, after the unit's
heading; a longer paragraph splits at sentence ends. The publisher's amendment citations
and editorial notes are left out, and their words counted. An element the builder does
not know stops the build, so no text is dropped silently.
"""

import re
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Literal

from regulator_graded_rag.tables import read_table
from regulator_graded_rag.xml_text import UnknownElement, normalize, render_inline

LIMIT = 250
APPARATUS = frozenset({"CITA", "EDNOTE"})
# A sentence ends at . ? or !, before a capital, a digit, a parenthesis, a quote or §, but
# not inside the two citations the edition splits long paragraphs at: "Test No. 431" and
# "49 U.S.C. 5101".
SENTENCE_END = re.compile(r"(?<=[.?!])(?<!\bNo\.)(?<!U\.S\.C\.)\s+(?=[(“\"A-Z0-9§])")
TEXT_BLOCKS = frozenset(
    {"P", "FP", "HD", "APPRO", "SECAUTH", "LDRWK", "TCAP", "RESERVED"}
)
CONTAINERS = frozenset({"EXTRACT", "NOTE", "EXAMPLE", "FTNT", "GPH", "MATH"})
NO_TEXT = frozenset({"GID", "MID"})  # image file names
COUNT_KEYS = (
    "units",
    "reserved units",
    "heading-only units",
    "text passages",
    "row passages",
    "tables",
    "rows",
    "column-number rows",
    "empty rows",
    "images",
    "formulas",
    "long paragraphs",
    "apparatus words",
)
_APPENDIX = re.compile(r"Pt\. (\d+), (?:Subpt\. ([A-Z]+), )?App\. ([A-Z]+)")
_RESERVED_ONLY = frozenset({"SECTNO", "RESERVED", "PRTPAGE"})


@dataclass(frozen=True)
class Passage:
    id: str
    unit: str
    kind: Literal["text", "row"]
    source: str
    page: int
    heading: str
    body: tuple[str, ...]
    caption: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        """The heading, then the body; a row adds its caption and labels its values."""
        if self.kind == "text":
            return "\n".join((self.heading, *self.body))
        values = (
            f"{label}: {value}" if label else value
            for label, value in zip(self.labels, self.body, strict=True)
        )
        return "\n".join((self.heading, *self.caption, *values))


@dataclass(frozen=True)
class Unit:
    key: str
    heading: str
    depth: int
    body: tuple[ET.Element, ...]  # the unit's children, without its heading elements


@dataclass(frozen=True)
class UnitBuild:
    unit: Unit
    passages: tuple[Passage, ...]


@dataclass(frozen=True)
class FileBuild:
    source: str
    units: tuple[UnitBuild, ...]
    counts: Counter[str]
    findings: tuple[str, ...]


def section_key(sectno: str) -> str:
    """'§ 173.304a' gives '173.304a'."""
    return normalize(sectno).lstrip("§ ")


def appendix_key(ear: str) -> str:
    """'Pt. 178, Subpt. C, App. A' gives '178.subptC.appA'."""
    text = normalize(ear)
    match = _APPENDIX.fullmatch(text)
    if match is None:
        raise ValueError(f"cannot read an appendix key from {text!r}")
    part, subpart, letter = match.groups()
    return f"{part}.subpt{subpart}.app{letter}" if subpart else f"{part}.app{letter}"


@dataclass
class _Walk:
    """What the walk through one file carries: the printed page, counts and findings."""

    page: int
    counts: Counter[str] = field(default_factory=Counter)
    findings: list[str] = field(default_factory=list)

    def pages_in(self, el: ET.Element) -> None:
        """Set the page from every page marker in el, in document order."""
        for marker in el.iter("PRTPAGE"):
            self.page = int(marker.attrib["P"])


def _groups(texts: Iterable[tuple[str, int]]) -> Iterator[list[tuple[str, int]]]:
    """Consecutive texts with their pages, grouped while their words total <= LIMIT."""
    group: list[tuple[str, int]] = []
    words = 0
    for text, page in texts:
        n = len(text.split())
        if group and words + n > LIMIT:
            yield group
            group, words = [], 0
        group.append((text, page))
        words += n
    if group:
        yield group


class _UnitBuilder:
    """Turns one unit's blocks into passages, in reading order."""

    def __init__(self, source: str, unit: Unit, walk: _Walk) -> None:
        self.source = source
        self.unit = unit
        self.walk = walk
        self.passages: list[Passage] = []
        # Paragraphs not yet in a passage, each with the page it starts on.
        self.pending: list[tuple[str, int]] = []

    def add(
        self,
        kind: Literal["text", "row"],
        page: int,
        body: tuple[str, ...],
        caption: tuple[str, ...] = (),
        labels: tuple[str, ...] = (),
    ) -> None:
        """Append the unit's next passage, numbered from 1 in reading order."""
        key = self.unit.key
        n = len(self.passages) + 1
        heading = self.unit.heading
        self.passages.append(
            Passage(
                f"{key}:{n}",
                key,
                kind,
                self.source,
                page,
                heading,
                body,
                caption,
                labels,
            )
        )
        self.walk.counts[f"{kind} passages"] += 1

    def flush(self) -> None:
        """Merge the pending paragraphs into text passages."""
        run: list[tuple[str, int]] = []
        for text, page in self.pending:
            if len(text.split()) <= LIMIT:
                run.append((text, page))
                continue
            self._add_groups(run)
            run = []
            self.walk.counts["long paragraphs"] += 1
            for group in _groups((s, page) for s in SENTENCE_END.split(text)):
                self.add("text", page, (" ".join(s for s, _ in group),))
        self._add_groups(run)
        self.pending.clear()

    def _add_groups(self, paragraphs: list[tuple[str, int]]) -> None:
        for group in _groups(paragraphs):
            self.add("text", group[0][1], tuple(text for text, _ in group))

    def table(self, el: ET.Element, depth: int) -> None:
        """One passage per row with text; the notes become text passages after them."""
        self.flush()
        try:
            table, self.walk.page = read_table(el, depth, self.walk.page)
        except ValueError as err:
            raise type(err)(f"{err} in {self.unit.key}") from err
        counts = self.walk.counts
        counts["tables"] += 1
        counts["rows"] += len(el.findall("ROW"))
        counts["column-number rows"] += table.column_number_rows
        counts["empty rows"] += table.empty_rows
        for row in table.rows:
            values = [(i, value) for i, value in enumerate(row.cells) if value]
            labels = tuple(
                table.labels[i] if i < len(table.labels) else "" for i, _ in values
            )
            body = tuple(value for _, value in values)
            self.add("row", row.page, body, table.caption, labels)
        self.pending.extend(table.notes)
        self.flush()
        # Labels the rows may misplace, reported for the comparison with the printed page.
        key, labels = self.unit.key, table.labels
        if el.find("BOXHD") is not None and len(labels) != table.columns:
            self.walk.findings.append(
                f"{key}: a table with {table.columns} columns has"
                f" {len(labels)} column labels"
            )
        if len(set(labels)) < len(labels):
            self.walk.findings.append(
                f"{key}: a table has {len(labels)} column labels,"
                f" {len(set(labels))} of them distinct"
            )
        for cell in el.iter("ENT"):
            if "A" in cell.attrib:
                self.walk.findings.append(
                    f'{key}: a table cell carries A="{cell.attrib["A"]}",'
                    " which the builder does not read"
                )

    def render(self, el: ET.Element, depth: int) -> str:
        """el's normalized text; its page markers move the page on."""
        try:
            rendered = render_inline(el, depth)
        except ValueError as err:
            raise type(err)(f"{err} in {self.unit.key}") from err
        if rendered.pages:
            self.walk.page = rendered.pages[-1]
        return normalize(rendered.text)

    def block(self, el: ET.Element, depth: int) -> None:
        """Read one child of the unit, or of a container, at its depth."""
        tag = el.tag
        if tag in TEXT_BLOCKS:
            page = self.walk.page
            if text := self.render(el, depth):
                self.pending.append((text, page))
        elif tag in CONTAINERS:
            if tag == "GPH":
                self.walk.counts["images"] += 1
            elif tag == "MATH":
                self.walk.counts["formulas"] += 1
            for child in el:
                self.block(child, depth + 1)
        elif tag in APPARATUS or tag in NO_TEXT:
            if tag in APPARATUS:
                words = len("".join(el.itertext()).split())
                self.walk.counts["apparatus words"] += words
            self.walk.pages_in(el)
        elif tag == "PRTPAGE":
            self.walk.page = int(el.attrib["P"])
        elif tag == "GPOTABLE":
            self.table(el, depth)
        else:
            raise UnknownElement(f"<{tag}> in {self.unit.key}")


def _heading_text(el: ET.Element, depth: int, walk: _Walk, where: str) -> str:
    """A heading element's normalized text; an error names where the heading is."""
    try:
        rendered = render_inline(el, depth)
    except ValueError as err:
        raise type(err)(f"{err} in {where}") from err
    if rendered.pages:
        walk.page = rendered.pages[-1]
    return normalize(rendered.text)


def _build_unit(
    source: str, el: ET.Element, depth: int, walk: _Walk
) -> UnitBuild | None:
    """The passages of one SECTION or APPENDIX; None for a reserved one."""
    tags = {child.tag for child in el}
    if "RESERVED" in tags and tags <= _RESERVED_ONLY:
        walk.counts["reserved units"] += 1
        walk.pages_in(el)
        return None
    walk.counts["units"] += 1
    if el.tag == "SECTION":
        sectno, subject = el.find("SECTNO"), el.find("SUBJECT")
        if sectno is None or subject is None:
            raise ValueError(f"a section without SECTNO or SUBJECT in {source}")
        number = _heading_text(sectno, depth + 1, walk, source)
        key = section_key(number)
        heading = f"{number} {_heading_text(subject, depth + 1, walk, key)}"
        heads = (sectno, subject)
    else:
        ear, title = el.find("EAR"), el.find("HD")
        if ear is None or title is None:
            raise ValueError(f"an appendix without EAR or HD in {source}")
        key = appendix_key(_heading_text(ear, depth + 1, walk, source))
        heading = _heading_text(title, depth + 1, walk, key)
        heads = (ear, title)
    unit = Unit(
        key, heading, depth, tuple(c for c in el if all(c is not h for h in heads))
    )
    builder = _UnitBuilder(source, unit, walk)
    for child in unit.body:
        builder.block(child, depth + 1)
    builder.flush()
    if not builder.passages:
        builder.add("text", walk.page, ())
        walk.counts["heading-only units"] += 1
    return UnitBuild(unit, tuple(builder.passages))


def build_file(source: str, data: bytes) -> FileBuild:
    """The passages of one Part file. Only sections and appendices give passage text."""
    root = ET.fromstring(data)
    first = root.find(".//PRTPAGE")
    walk = _Walk(int(first.attrib["P"]) - 1 if first is not None else 0)
    units: list[UnitBuild] = []

    def visit(el: ET.Element, depth: int) -> None:
        if el.tag in ("SECTION", "APPENDIX"):
            built = _build_unit(source, el, depth, walk)
            if built is not None:
                units.append(built)
        elif el.tag == "PRTPAGE":
            walk.page = int(el.attrib["P"])
        else:
            for child in el:
                visit(child, depth + 1)

    visit(root, 0)
    return FileBuild(source, tuple(units), walk.counts, tuple(walk.findings))
