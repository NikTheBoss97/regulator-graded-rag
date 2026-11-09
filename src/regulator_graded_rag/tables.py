# Author: Nicola Antonello
"""Read one GPOTABLE: its caption, column labels, rows and notes (ADR-0017).

A column's label joins the header levels above it. The first row of a table can hold the
column numbers the rules cite, such as "(7)": those prefix the labels instead of becoming
a row. Rows keep every cell the XML gives, empty ones included, and rows with no text are
counted and dropped. Any element the reader does not know stops the build.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from regulator_graded_rag.xml_text import UnknownElement, normalize, render_inline

COLUMN_NUMBER = re.compile(r"\(\d+[A-Za-z]?\)")


@dataclass(frozen=True)
class Row:
    cells: tuple[str, ...]
    page: int  # the printed page the row starts on


@dataclass(frozen=True)
class Table:
    caption: tuple[str, ...]  # the title and the description, in order
    labels: tuple[str, ...]
    rows: tuple[Row, ...]
    notes: tuple[tuple[str, int], ...]  # each note with the page it starts on
    columns: int
    column_number_rows: int
    empty_rows: int


def _text(el: ET.Element, depth: int) -> tuple[str, tuple[int, ...]]:
    rendered = render_inline(el, depth)
    return normalize(rendered.text), rendered.pages


def column_labels(boxhd: ET.Element | None, depth: int) -> tuple[str, ...]:
    """One label per leaf CHED: its ancestors' texts and its own, joined by spaces.

    depth is the BOXHD's depth. A CHED is a leaf when the next one is not deeper.
    """
    if boxhd is None:
        return ()
    heads: list[tuple[int, str]] = []
    for ched in boxhd:
        if ched.tag != "CHED":
            raise UnknownElement(f"<{ched.tag}> in a table header")
        heads.append((int(ched.attrib["H"]), _text(ched, depth + 1)[0]))
    labels: list[str] = []
    stack: list[tuple[int, str]] = []
    for i, (level, text) in enumerate(heads):
        stack = [*(head for head in stack if head[0] < level), (level, text)]
        following = heads[i + 1][0] if i + 1 < len(heads) else 0
        if following <= level:
            labels.append(" ".join(t for _, t in stack if t))
    return tuple(labels)


def read_table(table: ET.Element, depth: int, page: int) -> tuple[Table, int]:
    """The table, and the printed page after it; depth is the table's own depth."""
    caption: list[str] = []
    labels: tuple[str, ...] = ()
    rows: list[Row] = []
    notes: list[tuple[str, int]] = []
    column_number_rows = empty_rows = 0
    first_row = True
    for child in table:
        if child.tag in ("TTITLE", "TDESC"):
            text, pages = _text(child, depth + 1)
            page = pages[-1] if pages else page
            if text:
                caption.append(text)
        elif child.tag == "BOXHD":
            labels = column_labels(child, depth + 1)
        elif child.tag == "TNOTE":
            start = page
            text, pages = _text(child, depth + 1)
            page = pages[-1] if pages else page
            if text:
                notes.append((text, start))
        elif child.tag == "ROW":
            cells: list[str] = []
            row_page: int | None = None
            for cell in child:
                if cell.tag == "PRTPAGE":
                    page = int(cell.attrib["P"])
                elif cell.tag == "ENT":
                    row_page = page if row_page is None else row_page
                    text, pages = _text(cell, depth + 2)
                    page = pages[-1] if pages else page
                    cells.append(text)
                else:
                    raise UnknownElement(f"<{cell.tag}> in a table row")
            is_first, first_row = first_row, False
            if is_first and cells and all(COLUMN_NUMBER.fullmatch(c) for c in cells):
                prefixed = [f"{n} {label}" for n, label in zip(cells, labels)]
                labels = (*prefixed, *labels[len(cells) :])
                column_number_rows += 1
            elif not any(cells):
                empty_rows += 1
            else:
                rows.append(Row(tuple(cells), page if row_page is None else row_page))
        else:
            raise UnknownElement(f"<{child.tag}> in a table")
    built = Table(
        tuple(caption),
        labels,
        tuple(rows),
        tuple(notes),
        int(table.attrib["COLS"]),
        column_number_rows,
        empty_rows,
    )
    return built, page
