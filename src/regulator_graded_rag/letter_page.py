# Author: Nicola Antonello
"""Read a PHMSA interpretation letter page: its layout, fields and response text.

The regulator's site has shown its letters in two layouts, measured on 2026-11-14 in the
Internet Archive's captures of letter 20-0003:

- "article", the current one: an article whose class holds
  node--type-interpretation-response, one p per field labelled by a strong ("Response
  Publish Date:" with a time element whose datetime attribute is ISO, "Company Name:",
  "Individual Name:"), then a p whose strong reads "Response text:", then the letter's
  paragraphs until the next h2: p elements, or in some captures div elements holding
  no block of their own (25 letters' captures of 2026, measured on 2026-11-15);
- "content-wall", from 2020-2021: a section with id content-wall, the same labels in a b
  at the start of a td (the publish date as MM-DD-YYYY), and the letter's p paragraphs
  inside the td whose b reads "Response text:".

A page in neither layout gives no LetterPage, never an empty one; skeleton() and
signature() describe such a page by its tags, ids and classes, never by its text.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Literal

Layout = Literal["article", "content-wall"]

ARTICLE_CLASS = "node--type-interpretation-response"
CONTENT_WALL_ID = "content-wall"
PUBLISHED = "Response Publish Date:"
COMPANY = "Company Name:"
INDIVIDUAL = "Individual Name:"
RESPONSE = "Response text:"
# The content-wall layout's publish date: MM-DD-YYYY in the captures of 2020-2021,
# M/D/YYYY in the design's notes.
_WALL_DATES = ("%m-%d-%Y", "%m/%d/%Y")

# Elements that never have an end tag.
_VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta"}
    | {"source", "track", "wbr"}
)
# HTML lets these end tags be left out: an open element (the key) ends when one of the
# start tags in its value opens.
_ENDED_BY = {
    "p": frozenset(
        {"address", "article", "aside", "blockquote", "details", "div", "dl"}
        | {"fieldset", "figcaption", "figure", "footer", "form", "header", "hgroup"}
        | {"h1", "h2", "h3", "h4", "h5", "h6", "hr", "main", "menu", "nav", "ol"}
        | {"p", "pre", "section", "table", "ul"}
    ),
    "li": frozenset({"li"}),
    "td": frozenset({"td", "th", "tr"}),
    "th": frozenset({"td", "th", "tr"}),
    "tr": frozenset({"tr"}),
}


@dataclass(frozen=True)
class LetterPage:
    layout: Layout
    publish_date: date | None
    company: str
    individual: str
    paragraphs: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n".join(self.paragraphs)


@dataclass
class _Element:
    tag: str
    attrs: dict[str, str]
    children: list[_Element | str] = field(default_factory=list)

    @property
    def classes(self) -> list[str]:
        return self.attrs.get("class", "").split()

    def elements(self) -> Iterator[_Element]:
        """This element and every element inside it, in document order."""
        stack = [self]
        while stack:
            element = stack.pop()
            yield element
            stack += reversed([c for c in element.children if isinstance(c, _Element)])

    def text(self) -> str:
        """Its text, with br read as a space and whitespace collapsed."""
        pieces: list[str] = []
        stack: list[_Element | str] = [self]
        while stack:
            node = stack.pop()
            if isinstance(node, str):
                pieces.append(node)
            elif node.tag == "br":
                pieces.append(" ")
            else:
                stack += reversed(node.children)
        return " ".join("".join(pieces).split())


class _Tree(HTMLParser):
    """An element tree, built the way HTML closes the elements a page leaves open."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)  # entities come back decoded
        self.root = _Element("#document", {})
        self._open = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        while tag in _ENDED_BY.get(self._open[-1].tag, ()):
            self._open.pop()
        element = _Element(tag, {name: value or "" for name, value in attrs})
        self._open[-1].children.append(element)
        if tag not in _VOID:
            self._open.append(element)

    def handle_endtag(self, tag: str) -> None:
        # An end tag closes the nearest open element it names, and any left open inside
        # it; one that names no open element is ignored.
        for i in range(len(self._open) - 1, 0, -1):
            if self._open[i].tag == tag:
                del self._open[i:]
                return

    def handle_data(self, data: str) -> None:
        self._open[-1].children.append(data)


def _tree(html: str) -> _Element:
    parser = _Tree()
    parser.feed(html)
    parser.close()
    return parser.root


def _container(root: _Element) -> tuple[Layout, _Element] | None:
    for element in root.elements():
        if element.tag == "article" and ARTICLE_CLASS in element.classes:
            return "article", element
        if element.tag == "section" and element.attrs.get("id") == CONTENT_WALL_ID:
            return "content-wall", element
    return None


def _first(root: _Element, tag: str) -> _Element | None:
    """The first element with this tag at or inside root, in document order."""
    return next((e for e in root.elements() if e.tag == tag), None)


def _fields(container: _Element, block: str, label_tag: str) -> dict[str, _Element]:
    """Each block element whose first label element holds a label, by that label."""
    found: dict[str, _Element] = {}
    for element in container.elements():
        if element.tag == block and (label := _first(element, label_tag)) is not None:
            found.setdefault(label.text(), element)
    return found


def _value(element: _Element, label: str) -> str:
    """The element's text after its label."""
    return element.text().removeprefix(label).strip()


def _article_date(element: _Element | None) -> date | None:
    stamp = _first(element, "time") if element else None
    if stamp is None:
        return None
    try:
        return date.fromisoformat(stamp.attrs.get("datetime", "")[:10])
    except ValueError:
        return None


def _wall_date(element: _Element | None) -> date | None:
    value = _value(element, PUBLISHED) if element else ""
    for form in _WALL_DATES:
        try:
            return datetime.strptime(value, form).date()
        except ValueError:
            continue
    return None


def _is_paragraph(element: _Element) -> bool:
    """A p, or a div that holds no p or div of its own."""
    if element.tag == "p":
        return True
    inner = (e for e in element.elements() if e is not element)
    return element.tag == "div" and not any(e.tag in ("p", "div") for e in inner)


def _paragraphs_after(container: _Element, start: _Element) -> list[str]:
    """The text of every paragraph after start, up to the next h2."""
    texts: list[str] = []
    started = False
    for element in container.elements():
        if element is start:
            started = True
        elif started and element.tag == "h2":
            break
        elif started and _is_paragraph(element) and (text := element.text()):
            texts.append(text)
    return texts


def read_page(html: str) -> LetterPage | None:
    """The page's fields and response paragraphs; None for a page in neither layout."""
    found = _container(_tree(html))
    if found is None:
        return None
    layout, container = found
    if layout == "article":
        fields = _fields(container, "p", "strong")
        published = _article_date(fields.get(PUBLISHED))
        response = fields.get(RESPONSE)
        paragraphs = _paragraphs_after(container, response) if response else []
    else:
        fields = _fields(container, "td", "b")
        published = _wall_date(fields.get(PUBLISHED))
        response = fields.get(RESPONSE)
        paragraphs = [
            text
            for e in (response.elements() if response else ())
            if e.tag == "p" and (text := e.text())
        ]
    if not paragraphs:
        return None
    company, individual = (fields.get(k) for k in (COMPANY, INDIVIDUAL))
    return LetterPage(
        layout,
        published,
        _value(company, COMPANY) if company else "",
        _value(individual, INDIVIDUAL) if individual else "",
        tuple(paragraphs),
    )


def _describe(element: _Element) -> str:
    """The element's tag, then its id and classes as a CSS selector writes them."""
    ident = f"#{element.attrs['id']}" if element.attrs.get("id") else ""
    return element.tag + ident + "".join(f".{c}" for c in element.classes)


def skeleton(html: str, limit: int = 150) -> str:
    """One line per start tag inside main (or body), indented by depth; never any text."""
    root = _tree(html)
    top = _first(root, "main") or _first(root, "body") or root
    lines: list[str] = []
    stack = [
        (child, 0) for child in reversed(top.children) if isinstance(child, _Element)
    ]
    while stack and len(lines) < limit:
        element, depth = stack.pop()
        lines.append("  " * depth + _describe(element))
        stack += [
            (child, depth + 1)
            for child in reversed(element.children)
            if isinstance(child, _Element)
        ]
    return "\n".join(lines)


def signature(html: str) -> str:
    """The page's layout, or "unknown" with the element that holds "Response text:"."""
    root = _tree(html)
    found = _container(root)
    if found is not None:
        return found[0]
    holder = next(
        (
            e
            for e in root.elements()
            if any(isinstance(c, str) and RESPONSE in c for c in e.children)
        ),
        None,
    )
    return f"unknown: {_describe(holder)}" if holder else "unknown: no response text"
