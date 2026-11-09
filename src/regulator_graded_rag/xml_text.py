# Author: Nicola Antonello
"""Render the regulation's XML markup as text, keeping the source's spacing (ADR-0017).

GovInfo pretty-prints its XML: every line break inside text was added by the publisher,
followed by 4 spaces per level of nesting (the root is level 0), and an original space
shows as one more space. This held for every text of the 2025 edition, so undoing it
exactly gives back the original spacing, where collapsing whitespace would turn
"5101 et seq.) directs" into "5101 et seq. ) directs". Anything else raises, rather than
joining or splitting words.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass

# Marks raised text: "8.0 × 10^−1". The source never contains "^".
SUPERSCRIPT = "^"
INLINE = frozenset({"E", "SU", "FR", "LI", "PRTPAGE", "FTREF", "FL-2", "LDRFIG"})
_RAISED_E = "51"
_SPACE_BEFORE = frozenset({"LI", "FL-2", "LDRFIG"})


class UnknownElement(ValueError):
    """An element the renderer or the builder does not know, so its text would be lost."""


@dataclass(frozen=True)
class Rendered:
    text: str
    pages: tuple[int, ...]  # the P of each PRTPAGE met, in order


def undo_indent(s: str | None, inner: int) -> str:
    """Remove the pretty-printer's line breaks from a text or tail.

    inner is the indentation of the lines inside the element that holds s. A trailing
    line break followed by inner or inner - 4 spaces (before a child, or before the
    closing tag) is removed; so is a leading one followed by inner spaces, or inner + 1
    when an original space follows.
    """
    if not s:
        return ""
    for spaces in (inner, inner - 4):
        if s.endswith("\n" + " " * spaces):
            s = s[: -(spaces + 1)]
            break
    if s.startswith("\n"):
        spaces = len(s) - 1 - len(s[1:].lstrip(" "))
        if spaces not in (inner, inner + 1):
            raise ValueError(
                f"unexpected indentation: {spaces} spaces where {inner} were expected"
                f" in {s[:60]!r}"
            )
        s = s[1 + inner :]
    if "\n" in s:
        raise ValueError(f"unexpected line break in {s[:60]!r}")
    return s


def render_inline(el: ET.Element, depth: int) -> Rendered:
    """The text of an element and its inline children; depth is el's depth (root 0)."""
    inner = 4 * (depth + 1)
    text = undo_indent(el.text, inner)
    pages: list[int] = []
    for child in el:
        if child.tag == "PRTPAGE":
            pages.append(int(child.attrib["P"]))
        elif child.tag in INLINE:
            part = render_inline(child, depth + 1)
            pages.extend(part.pages)
            if child.tag == "SU" or (child.tag == "E" and child.get("T") == _RAISED_E):
                text += SUPERSCRIPT
            elif child.tag in _SPACE_BEFORE or (
                child.tag == "FR" and text[-1:].isalnum()
            ):
                text += " "
            text += part.text
        else:
            raise UnknownElement(f"<{child.tag}>")
        text += undo_indent(child.tail, inner)
    return Rendered(text, tuple(pages))


def normalize(s: str) -> str:
    """Drop soft hyphens and turn each run of whitespace into one space."""
    return " ".join(s.replace("\u00ad", "").split())
