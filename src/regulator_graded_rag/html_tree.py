# Author: Nicola Antonello
"""An element tree for HTML pages, built with the standard library's parser.

html.parser reports tags one by one and builds no tree. parse() builds one the way a
browser closes the elements a page leaves open: a p ends where a block starts, an li at
the next li, a cell at the next cell or row, void elements such as br never hold
anything, and an end tag that names no open element is ignored.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser

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


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    children: list[Element | str] = field(default_factory=list)

    @property
    def classes(self) -> list[str]:
        return self.attrs.get("class", "").split()

    def elements(self) -> Iterator[Element]:
        """This element and every element inside it, in document order."""
        stack = [self]
        while stack:
            element = stack.pop()
            yield element
            stack += reversed([c for c in element.children if isinstance(c, Element)])

    def text(self) -> str:
        """Its text, with br read as a space and whitespace collapsed."""
        pieces: list[str] = []
        stack: list[Element | str] = [self]
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
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)  # entities come back decoded
        self.root = Element("#document", {})
        self._open = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        while tag in _ENDED_BY.get(self._open[-1].tag, ()):
            self._open.pop()
        element = Element(tag, {name: value or "" for name, value in attrs})
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


def parse(html: str) -> Element:
    """The page as a tree under a root element tagged "#document"."""
    parser = _Tree()
    parser.feed(html)
    parser.close()
    return parser.root


def first(root: Element, tag: str) -> Element | None:
    """The first element with this tag at or inside root, in document order."""
    return next((e for e in root.elements() if e.tag == tag), None)
