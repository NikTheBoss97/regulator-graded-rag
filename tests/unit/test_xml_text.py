# Author: Nicola Antonello
import pyexpat
import xml.etree.ElementTree as ET

import pytest

from regulator_graded_rag.xml_text import (
    Rendered,
    UnknownElement,
    normalize,
    render_inline,
    undo_indent,
)


def el(*lines: str) -> ET.Element:
    return ET.fromstring("\n".join(lines))


def test_inserted_indentation_is_removed() -> None:
    assert undo_indent("\n" + " " * 20 + "Federal law", 20) == "Federal law"
    assert undo_indent("5101 \n" + " " * 20, 20) == "5101 "
    assert undo_indent("\n" + " " * 16, 20) == ""


def test_an_original_space_after_the_indentation_is_kept() -> None:
    assert undo_indent("\n" + " " * 21 + "Requirements", 20) == " Requirements"


def test_text_without_line_breaks_is_unchanged() -> None:
    assert undo_indent(" (a) ", 20) == " (a) "
    assert undo_indent(None, 20) == ""


def test_unexpected_indentation_is_refused() -> None:
    with pytest.raises(ValueError, match="indentation"):
        undo_indent("\n" + " " * 24 + "x", 20)
    with pytest.raises(ValueError, match="line break"):
        undo_indent("a\nb", 20)


def test_inline_spacing_follows_the_source() -> None:
    p = el(
        "<P>",
        "    (49 U.S.C. 5101 ",
        '    <E T="03">et seq.</E>',
        "    ) directs",
        "</P>",
    )
    assert render_inline(p, depth=0).text == "(49 U.S.C. 5101 et seq.) directs"


def test_superscripts_are_marked_so_exponents_keep_their_value() -> None:
    cell = el("<ENT>", "    8.0 × 10", '    <E T="51">−1</E>', "</ENT>")
    assert render_inline(cell, depth=0).text == "8.0 × 10^−1"
    cell = el("<ENT>", "    2.2 × 10", "    <SU>1</SU>", "</ENT>")
    assert render_inline(cell, depth=0).text == "2.2 × 10^1"


def test_subscripts_join_their_formula() -> None:
    cell = el(
        "<ENT>",
        "    Arsenic acid H",
        '    <E T="52">3</E>',
        "    AsO",
        '    <E T="52">4</E>',
        "</ENT>",
    )
    assert render_inline(cell, depth=0).text == "Arsenic acid H3AsO4"


def test_a_fraction_after_a_digit_gets_a_space() -> None:
    fp = el("<FP>", "    2 = 1", "    <FR>1/2</FR>", "     Radii", "</FP>")
    assert render_inline(fp, depth=0).text == "2 = 1 1/2 Radii"
    p = el("<P>", "    border measuring ", "    <FR>1/2</FR>", "    -inch", "</P>")
    assert render_inline(p, depth=0).text == "border measuring 1/2-inch"


def test_a_line_break_inside_a_cell_becomes_a_space() -> None:
    ched = el("<CHED>", "    Current OMB", "    <LI>control No.</LI>", "</CHED>")
    assert render_inline(ched, depth=0).text == "Current OMB control No."


def test_a_page_break_adds_no_text_and_reports_its_page() -> None:
    p = el("<P>", "    a non-", '    <PRTPAGE P="55"/>', "    gelatin dynamite", "</P>")
    assert render_inline(p, depth=0) == Rendered("a non-gelatin dynamite", (55,))


def test_unknown_inline_element_is_refused() -> None:
    with pytest.raises(UnknownElement, match="BLINK"):
        render_inline(el("<P>", "    a", "    <BLINK>b</BLINK>", "</P>"), depth=0)


def test_normalize_collapses_typographic_spaces_and_drops_soft_hyphens() -> None:
    assert normalize("§\u2009171.1\u2003 Purpose.\n") == "§ 171.1 Purpose."
    assert normalize("colder than \u00ad−90 °C") == "colder than −90 °C"


def test_expat_is_new_enough_for_untrusted_xml() -> None:
    assert pyexpat.version_info >= (2, 7, 2)
