# Author: Nicola Antonello
"""Check the passages against the XML, read through a code path of their own (ADR-0006).

The renderer could lose a word and its output would still look plausible, so these checks
never call it: they read the raw text nodes of each unit. Every non-whitespace character
of a unit's rule text must land in its passages once and in order; every table row with
text must become one passage; IDs must count up from 1 in each unit and never repeat.
"""

import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterator, Sequence

from regulator_graded_rag.passages import APPARATUS, FileBuild, Passage, Unit
from regulator_graded_rag.tables import COLUMN_NUMBER

# Not rule text, or repeated in every row passage instead of in its body.
_LEFT_OUT = frozenset({"BOXHD", "TTITLE", "TDESC", "GID", "MID"}) | APPARATUS
_CONTEXT = 30


def _squeeze(text: str) -> str:
    """The non-whitespace characters, without soft hyphens."""
    return "".join(text.replace("\u00ad", "").split())


def _is_column_numbers(row: ET.Element) -> bool:
    cells = [_squeeze("".join(cell.itertext())) for cell in row.findall("ENT")]
    return bool(cells) and all(COLUMN_NUMBER.fullmatch(cell) for cell in cells)


def _tables(elements: Sequence[ET.Element]) -> Iterator[ET.Element]:
    """The GPOTABLEs among the elements and their descendants, outside left-out ones."""
    for el in elements:
        if el.tag in _LEFT_OUT:
            continue
        if el.tag == "GPOTABLE":
            yield el
        else:
            yield from _tables(list(el))


def _first_row_of_numbers(table: ET.Element) -> ET.Element | None:
    first = table.find("ROW")
    return first if first is not None and _is_column_numbers(first) else None


def reference_characters(unit: Unit) -> str:
    """Every non-whitespace character of the unit's rule text, in document order."""
    skipped = {
        id(row)
        for table in _tables(unit.body)
        if (row := _first_row_of_numbers(table)) is not None
    }
    pieces: list[str] = []

    def visit(el: ET.Element) -> None:
        if el.tag in _LEFT_OUT or id(el) in skipped:
            return
        pieces.append(el.text or "")
        for child in el:
            visit(child)
            pieces.append(child.tail or "")

    for el in unit.body:
        visit(el)
        pieces.append(el.tail or "")
    return _squeeze("".join(pieces))


def passage_characters(passages: Sequence[Passage]) -> str:
    """Every non-whitespace character of the passages' bodies, without the ^ markers."""
    return _squeeze("".join(b for p in passages for b in p.body).replace("^", ""))


def _row_counts(unit: Unit) -> tuple[int, int, int]:
    """ROW elements, column-number first rows and rows with no text, from the XML."""
    rows = numbers = empty = 0
    for table in _tables(unit.body):
        all_rows = table.findall("ROW")
        rows += len(all_rows)
        numbers += _first_row_of_numbers(table) is not None
        empty += sum(1 for row in all_rows if not _squeeze("".join(row.itertext())))
    return rows, numbers, empty


def check_unit(unit: Unit, passages: Sequence[Passage]) -> list[str]:
    """The unit's problems: IDs, then text, then rows; empty when it is right."""
    key = unit.key
    if not passages:
        return [f"{key}: no passage"]
    problems: list[str] = []
    if [p.id for p in passages] != [f"{key}:{n}" for n in range(1, len(passages) + 1)]:
        problems.append(
            f"{key}: passage IDs are not {key}:1 to {key}:{len(passages)} in order"
        )
    expected, found = reference_characters(unit), passage_characters(passages)
    if expected != found:
        i = next(
            (n for n, (a, b) in enumerate(zip(expected, found)) if a != b),
            min(len(expected), len(found)),
        )
        lo, hi = max(0, i - _CONTEXT), i + _CONTEXT
        problems.append(
            f"{key}: text differs from the XML at character {i}:"
            f" expected {expected[lo:hi]!a}, found {found[lo:hi]!a}"
        )
    rows, numbers, empty = _row_counts(unit)
    row_passages = sum(1 for p in passages if p.kind == "row")
    if row_passages != rows - numbers - empty:
        problems.append(
            f"{key}: {row_passages} row passages for {rows} rows"
            f" ({numbers} column-number, {empty} empty)"
        )
    return problems


def check_build(builds: Sequence[FileBuild]) -> list[str]:
    """Every unit's problems, then each passage ID used more than once."""
    problems = [
        problem
        for build in builds
        for unit in build.units
        for problem in check_unit(unit.unit, unit.passages)
    ]
    ids = Counter(p.id for b in builds for u in b.units for p in u.passages)
    problems += [f"duplicate passage ID {id_}" for id_, n in ids.items() if n > 1]
    return problems
