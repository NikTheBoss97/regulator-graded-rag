# Author: Nicola Antonello
import xml.etree.ElementTree as ET

import pytest

from regulator_graded_rag.tables import Row, read_table
from regulator_graded_rag.xml_text import UnknownElement

HMT = ET.fromstring(
    '<GPOTABLE COLS="4" OPTS="L2" CDEF="s">'
    "<BOXHD>"
    '<CHED H="1">Symbols</CHED><CHED H="1">Hazardous materials descriptions</CHED>'
    '<CHED H="1">(8)</CHED><CHED H="2">Packaging (§ 173.***)</CHED>'
    '<CHED H="3">Exceptions</CHED><CHED H="3">Non-bulk</CHED>'
    "</BOXHD>"
    '<ROW RUL="s"><ENT I="25">(1)</ENT><ENT>(2)</ENT><ENT>(8A)</ENT><ENT>(8B)</ENT></ROW>'
    '<ROW><ENT I="01"/><ENT>Acetone</ENT><ENT>150</ENT><ENT>202</ENT></ROW>'
    '<ROW><ENT I="01"/><ENT>Accellerene, see p-Nitrosodimethylaniline</ENT></ROW>'
    '<ROW><ENT I="22"> </ENT></ROW>'
    '<ROW><PRTPAGE P="11"/><ENT I="01"/><ENT>Acetyl bromide</ENT></ROW>'
    "</GPOTABLE>"
)


def test_header_levels_join_into_one_label_per_column() -> None:
    table, _ = read_table(HMT, depth=0, page=10)
    assert table.labels == (
        "(1) Symbols",
        "(2) Hazardous materials descriptions",
        "(8A) (8) Packaging (§ 173.***) Exceptions",
        "(8B) (8) Packaging (§ 173.***) Non-bulk",
    )
    assert (table.columns, table.column_number_rows) == (4, 1)


def test_short_rows_keep_their_cells_and_empty_rows_are_dropped() -> None:
    table, page = read_table(HMT, depth=0, page=10)
    assert table.rows == (
        Row(("", "Acetone", "150", "202"), 10),
        Row(("", "Accellerene, see p-Nitrosodimethylaniline"), 10),
        Row(("", "Acetyl bromide"), 11),
    )
    assert (table.empty_rows, page) == (1, 11)


def test_a_table_without_headers_has_no_labels() -> None:
    form = ET.fromstring(
        '<GPOTABLE COLS="2"><ROW EXPSTB="02"><ENT I="01">Built by Company</ENT></ROW></GPOTABLE>'
    )
    table, _ = read_table(form, depth=0, page=1)
    assert (table.labels, table.rows) == ((), (Row(("Built by Company",), 1),))


def test_titles_descriptions_and_notes_are_kept() -> None:
    table, _ = read_table(
        ET.fromstring(
            '<GPOTABLE COLS="1"><TTITLE>Table 1—IB Codes</TTITLE><TDESC>[Large packagings]</TDESC>'
            '<BOXHD><CHED H="1">IBC code</CHED></BOXHD><ROW><ENT I="01">IB1</ENT></ROW>'
            "<TNOTE><SU>1</SU> Refers to the group.</TNOTE></GPOTABLE>"
        ),
        depth=0,
        page=5,
    )
    assert table.caption == ("Table 1—IB Codes", "[Large packagings]")
    assert table.notes == (("^1 Refers to the group.", 5),)


def test_unknown_table_element_stops_the_build() -> None:
    with pytest.raises(UnknownElement, match="BLINK"):
        read_table(
            ET.fromstring('<GPOTABLE COLS="1"><BLINK/></GPOTABLE>'), depth=0, page=1
        )
