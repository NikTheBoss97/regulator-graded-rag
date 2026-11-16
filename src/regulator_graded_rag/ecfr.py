# Author: Nicola Antonello
"""Read eCFR's rendered pages of Title 49 into units, paragraphs and comparable text.

Usage: python -m regulator_graded_rag.ecfr [--day YYYY-MM-DD] [--cache DIR], from the
repository root, fetches the ten part pages (Parts 171-180) for a day, by default the
edition's day, 1 October 2025.

eCFR serves the text of any day since 2017. Its renderer, measured on 2026-11-14 and
2026-11-15, answers a part or section request with a redirect to its canonical address,
then with HTML in which a unit is a div.section whose id is the section number, or a
div.appendix with an id such as Appendix-A-to-Subpart-C-of-Part-178, and every paragraph
is a div with an id such as p-173.185(a)(1)(i), nested inside its parent paragraph's div.
A unit's rule text leaves out its heading, the amendment citations, editorial notes,
footnotes (kept apart), table heads and captions, and a first row of column numbers, the
same text the corpus's parse checks read from the XML. A page is fetched once and kept,
because eCFR's text for a past day does not change.
"""

import argparse
import os
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from regulator_graded_rag.fetch import FetchError, Get, http_get
from regulator_graded_rag.html_tree import Element, parse
from regulator_graded_rag.polite import Paced
from regulator_graded_rag.tables import COLUMN_NUMBER

RENDERER = "https://www.ecfr.gov/api/renderer/v1/content/enhanced"
EDITION_DAY = date(2025, 10, 1)
PARTS = tuple(str(p) for p in range(171, 181))
ECFR_INTERVAL = 1.0
DEFAULT_CACHE = Path("eval/ecfr")
APPENDIX_ID = re.compile(r"Appendix-([A-Z])-to-(?:Subpart-([A-Z])-of-)?Part-(\d+)")
# Units whose eCFR text differs from the corpus's, each with the owner's dated ruling.
# A draft citing one of them is flagged for the owner's check.
KNOWN_DIFFERENCES: dict[str, str] = {
    "180.209": (
        "eCFR shows Table 1 to paragraph (a) twice, while the printed edition (page"
        " 335) and the corpus show it once, with the same 16 rows; eCFR is wrong, a"
        " known difference (owner, 2026-11-15)"
    ),
    "180.407": (
        "eCFR prints the heading of paragraph (g)(1) as 'Test Procedure—', while the"
        " printed edition (page 360) and the corpus read 'Test procedure.'; eCFR is"
        " wrong, a known difference (owner, 2026-11-15)"
    ),
}
_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
# Text from different blocks is joined with a space.
_BLOCKS = frozenset({"p", "div", "td", "th", "tr", "li"}) | _HEADINGS
_LEFT_OUT = frozenset({"citation", "editorial-note", "seal-block", "footnote"})
_FOOTNOTE_NUMBER = re.compile(r"\[(\d+)\]")


class PageMissing(FetchError):
    """eCFR holds no such page on that day (HTTP 404): the unit did not exist then."""


def page_url(day: date, part: str, section: str | None = None) -> str:
    url = f"{RENDERER}/{day.isoformat()}/title-49?part={part}"
    return f"{url}&section={section}" if section else url


def unit_key(div_class: str, div_id: str) -> str | None:
    """The passage builder's key for a unit div, or None for any other div."""
    classes = div_class.split()
    if "section" in classes:
        return div_id or None
    match = APPENDIX_ID.fullmatch(div_id) if "appendix" in classes else None
    if match is None:
        return None
    letter, subpart, part = match.groups()
    return f"{part}.subpt{subpart}.app{letter}" if subpart else f"{part}.app{letter}"


@dataclass(frozen=True)
class UnitText:
    key: str
    text: str
    footnotes: str
    paragraphs: Mapping[str, str]  # each paragraph's text with its subparagraphs'
    # Paragraphs a citation cannot be compared by alone: one followed by content outside
    # it before the next paragraph starts, such as a table eCFR places after its div, and
    # one whose id sits on an element other than a div.
    loose: frozenset[str] = frozenset()
    # The file names of the figures, in order: "" for the unit, and by paragraph.
    figures: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


# Not rule content, so they make no paragraph loose: the amendment citations, the
# editorial notes and the header of a footnote box.
_NOT_RULES = frozenset({"citation", "editorial-note", "seal-block"})


def _loose(unit: Element) -> frozenset[str]:
    """The paragraphs whose content is not all inside their own div."""
    heading = next(
        (e for e in unit.elements() if e is not unit and e.tag in _HEADINGS), None
    )
    loose: set[str] = set()
    ended: list[str] = []  # paragraphs that ended since the last paragraph began
    stack: list[Element | str | tuple[str]] = list(reversed(unit.children))
    while stack:
        node = stack.pop()
        if isinstance(node, tuple):
            ended.append(node[0])
        elif isinstance(node, str):
            if node.strip():
                loose.update(ended)
        elif node is heading or _NOT_RULES & set(node.classes):
            continue
        else:
            if node.tag == "img":
                loose.update(ended)
            name = node.attrs.get("id", "")
            if name.startswith("p-") and node.tag != "div":
                loose.add(name[2:])
            elif name.startswith("p-"):
                ended.clear()
                stack.append(
                    (name[2:],)
                )  # popped once the paragraph's children are out
            stack += reversed(node.children)
    return frozenset(loose)


def _figures(unit: Element) -> dict[str, tuple[str, ...]]:
    """The file names of the figures in the unit, "" first, then in each paragraph."""

    def names(root: Element) -> tuple[str, ...]:
        return tuple(
            e.attrs.get("src", "").rsplit("/", 1)[-1]
            for e in root.elements()
            if e.tag == "img"
        )

    found = {"": names(unit)} if names(unit) else {}
    for e in unit.elements():
        name = e.attrs.get("id", "")
        if e.tag == "div" and name.startswith("p-") and (inside := names(e)):
            found[name[2:]] = inside
    return found


def _left_out(unit: Element) -> set[int]:
    """The ids of the elements inside the unit whose text is not rule text."""
    inside = [e for e in unit.elements() if e is not unit]
    heading = next((e for e in inside if e.tag in _HEADINGS), None)
    skip = {id(heading)} if heading is not None else set()
    for element in inside:
        if element.tag in ("thead", "caption") or _LEFT_OUT & set(element.classes):
            skip.add(id(element))
        elif element.tag == "tbody":
            row = next((c for c in _children(element) if c.tag == "tr"), None)
            cells = [c for c in _children(row) if c.tag in ("td", "th")] if row else []
            if cells and all(
                COLUMN_NUMBER.fullmatch(_squeeze(c.text())) for c in cells
            ):
                skip.add(id(row))
    return skip


def _children(element: Element) -> list[Element]:
    return [c for c in element.children if isinstance(c, Element)]


def _squeeze(text: str) -> str:
    return "".join(text.split())


def _text(root: Element, skip: set[int]) -> str:
    """root's text without the skipped elements, a space between blocks, collapsed."""
    pieces: list[str] = []
    stack: list[Element | str] = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            pieces.append(node)
        elif id(node) in skip:
            continue
        elif node.tag == "br":
            pieces.append(" ")
        else:
            if node.tag in _BLOCKS:
                pieces.append(" ")
                stack.append(
                    " "
                )  # the space after the block, once its children are out
            stack += reversed(node.children)
    return " ".join("".join(pieces).split())


def _paragraphs(unit: Element, skip: set[int]) -> dict[str, str]:
    """Each paragraph's text, by its id without "p-".

    A cited paragraph must be unambiguous. The official §178.55 prints its paragraph
    (i) twice, word for word, so a paragraph whose copies all read the same is kept
    once, and one whose copies differ is left out: a citation of it finds nothing.
    """
    copies: dict[str, set[str]] = {}
    for e in unit.elements():
        if e.tag == "div" and e.attrs.get("id", "").startswith("p-"):
            copies.setdefault(e.attrs["id"][2:], set()).add(_text(e, skip))
    return {name: texts.pop() for name, texts in copies.items() if len(texts) == 1}


def parse_units(html: str) -> dict[str, UnitText]:
    """Every unit on the page; a unit that appears twice is refused."""
    units: dict[str, UnitText] = {}
    for div in parse(html).elements():
        if div.tag != "div":
            continue
        key = unit_key(" ".join(div.classes), div.attrs.get("id", ""))
        if key is None:
            continue
        if key in units:
            raise ValueError(f"{key} appears twice in the page")
        skip = _left_out(div)
        footnotes = [_text(e, set()) for e in div.elements() if "footnote" in e.classes]
        units[key] = UnitText(
            key,
            _text(div, skip),
            " ".join(footnotes),
            _paragraphs(div, skip),
            _loose(div),
            _figures(div),
        )
    return units


def characters(text: str) -> str:
    """The form compared with GovInfo's: U+2044 read as "/", "[n]" as n, and no "§",
    soft hyphen or whitespace."""
    text = _FOOTNOTE_NUMBER.sub(r"\1", text.replace("\u2044", "/"))
    return _squeeze(text).replace("§", "").replace("\u00ad", "")


class Cache:
    """eCFR's pages, fetched once into root/{day}/{part}.html or .../{part}/{section}.html."""

    def __init__(self, root: Path, get: Get) -> None:
        self.root = root
        self._get = get

    def path(self, day: date, part: str, section: str | None = None) -> Path:
        folder = self.root / day.isoformat()
        return folder / part / f"{section}.html" if section else folder / f"{part}.html"

    def page(self, day: date, part: str, section: str | None = None) -> str:
        """The page's HTML: one redirect within the renderer is followed, as eCFR sends
        each request to its canonical address, and a 404 raises PageMissing."""
        path = self.path(day, part, section)
        if not path.is_file():
            url = page_url(day, part, section)
            response = self._get(url)
            location = response.location or ""
            same_day = f"{RENDERER}/{day.isoformat()}/title-49?"
            if 300 <= response.status < 400 and location.startswith(same_day):
                response = self._get(location)
            if response.status == 404:
                raise PageMissing(f"{url}: HTTP 404")
            if 300 <= response.status < 400:
                raise FetchError(f"{url}: redirected to {response.location}")
            if response.status != 200:
                raise FetchError(f"{url}: HTTP {response.status}")
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_name(f"{path.name}.part")
            partial.write_bytes(response.body)
            os.replace(partial, path)
        return path.read_bytes().decode("utf-8")


def _paced_get() -> Get:
    return Paced(lambda url: http_get(url, accept_gzip=True), interval=ECFR_INTERVAL)


def default_cache() -> Cache:
    return Cache(DEFAULT_CACHE, _paced_get())


def edition_units(cache: Cache) -> dict[str, UnitText]:
    """The ten parts' units on the edition's day, merged."""
    units: dict[str, UnitText] = {}
    for part in PARTS:
        for key, unit in parse_units(cache.page(EDITION_DAY, part)).items():
            if key in units:
                raise ValueError(f"{key} appears in two parts")
            units[key] = unit
    return units


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.ecfr",
        description="Fetch eCFR's ten part pages of Title 49 for a day, once each.",
    )
    parser.add_argument("--day", type=date.fromisoformat, default=EDITION_DAY)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args(argv)
    cache = Cache(args.cache, _paced_get())
    for i, part in enumerate(PARTS, start=1):
        prefix = f"[{i}/{len(PARTS)} {time.strftime('%H:%M:%S')}] part {part}"
        path = cache.path(args.day, part)
        outcome = "present" if path.is_file() else "fetched"
        try:
            cache.page(args.day, part)
        except FetchError as err:
            print(f"{prefix}: FAILED: {err}", flush=True)
            return 1
        print(f"{prefix}: {outcome} ({path.stat().st_size:,} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
