# Author: Nicola Antonello
import pytest

from regulator_graded_rag.passages import (
    Passage,
    appendix_key,
    build_file,
    section_key,
)
from regulator_graded_rag.xml_text import UnknownElement


def part(*body: str, first_page: int = 10) -> bytes:
    """A Part file shaped like GovInfo's, without the pretty-printing."""
    return (
        "<CFRGRANULE><FDSYS><VOL>2</VOL></FDSYS><PART><HD>PART 171</HD>"
        "<CONTENTS><SECTNO>§ 171.1</SECTNO><SUBJECT>A contents entry.</SUBJECT></CONTENTS>"
        f'<SUBPART><HD>Subpart A</HD><PRTPAGE P="{first_page}"/>{"".join(body)}</SUBPART>'
        "</PART></CFRGRANULE>"
    ).encode()


def section(number: str, subject: str, *body: str) -> str:
    return f"<SECTION><SECTNO>§ {number}</SECTNO><SUBJECT>{subject}</SUBJECT>{''.join(body)}</SECTION>"


def words(n: int) -> str:
    return " ".join(["word"] * n)


def passages_of(data: bytes) -> list[Passage]:
    return [p for unit in build_file("test.xml", data).units for p in unit.passages]


def test_paragraphs_merge_up_to_the_limit() -> None:
    data = part(section("171.1", "Purpose.", *[f"<P>{words(100)}</P>"] * 3))
    assert [(p.id, len(" ".join(p.body).split())) for p in passages_of(data)] == [
        ("171.1:1", 200),
        ("171.1:2", 100),
    ]


def test_every_passage_starts_with_its_heading() -> None:
    (p,) = passages_of(
        part(
            section(
                "171.1", "Purpose and scope.", "<P>(a) Text.</P>", "<P>(b) More.</P>"
            )
        )
    )
    assert p.text == "§ 171.1 Purpose and scope.\n(a) Text.\n(b) More."


def test_a_passage_never_crosses_a_section() -> None:
    data = part(
        section("171.1", "One.", "<P>a b</P>"), section("171.2", "Two.", "<P>c d</P>")
    )
    assert [(p.id, p.body) for p in passages_of(data)] == [
        ("171.1:1", ("a b",)),
        ("171.2:1", ("c d",)),
    ]


def test_a_long_paragraph_is_split_at_sentence_ends() -> None:
    sentence = f"Rule {words(98)} end."
    passages = passages_of(
        part(section("171.1", "S.", f"<P>{' '.join([sentence] * 4)}</P>"))
    )
    assert [len(" ".join(p.body).split()) for p in passages] == [200, 200]
    assert all(" ".join(p.body).endswith("end.") for p in passages)


def test_a_sentence_over_the_limit_stays_whole() -> None:
    (p,) = passages_of(part(section("171.1", "S.", f"<P>Rule {words(300)}.</P>")))
    assert len(p.body[0].split()) == 301


@pytest.mark.parametrize("cited", ["Test No. 431", "49 U.S.C. 5101"])
def test_a_long_paragraph_never_splits_inside_a_citation(cited: str) -> None:
    text = f"Start {words(245)} under {cited} {words(100)} end."
    (p,) = passages_of(part(section("173.137", "S.", f"<P>{text}</P>")))
    assert p.body == (text,)


def test_publisher_citations_and_editorial_notes_are_left_out() -> None:
    data = part(
        section(
            "171.1",
            "S.",
            "<P>Rule text.</P>",
            "<CITA>[Amdt. 171-1, 1 FR 1, Jan. 1, 2000]</CITA>",
            "<EDNOTE><HD>Editorial Note:</HD><P>See the List of CFR Sections Affected.</P></EDNOTE>",
        )
    )
    assert [p.body for p in passages_of(data)] == [("Rule text.",)]


def test_the_words_left_out_are_counted() -> None:
    # The build reports the words it leaves out (ADR-0017). As in the real files, a
    # line break separates the note's heading from its paragraph.
    data = part(
        section(
            "171.1",
            "S.",
            "<P>Rule text.</P>",
            "<CITA>[Amdt. 171-1, 1 FR 1, Jan. 1, 2000]</CITA>",
            "<EDNOTE><HD>Editorial Note:</HD>\n"
            "<P>See the List of CFR Sections Affected.</P></EDNOTE>",
        )
    )
    assert build_file("t.xml", data).counts["apparatus words"] == 8 + 9


def test_notes_extracts_examples_and_leader_work_are_read_in_order() -> None:
    data = part(
        section(
            "171.1",
            "S.",
            "<P>(a) First.</P>",
            "<NOTE><HD>Note 1 to paragraph (a):</HD><P>Noted.</P></NOTE>",
            "<EXTRACT><HD>Code/Special Provisions</HD><FP>1 This material.</FP></EXTRACT>",
            "<EXAMPLE><HD>Examples.</HD><P>An example.</P></EXAMPLE>",
            "<LDRWK><FL-2>Longitudinal</FL-2><LDRFIG>7G</LDRFIG></LDRWK>",
        )
    )
    assert passages_of(data)[0].body == (
        "(a) First.",
        "Note 1 to paragraph (a):",
        "Noted.",
        "Code/Special Provisions",
        "1 This material.",
        "Examples.",
        "An example.",
        "Longitudinal 7G",
    )


def test_images_and_formulas_add_no_text_but_keep_their_captions() -> None:
    build = build_file(
        "t.xml",
        part(
            section(
                "171.1",
                "S.",
                "<P>See the figure.</P>",
                '<GPH SPAN="2" DEEP="300"><GID>ER01JA20.000</GID><TCAP>Figure 1</TCAP></GPH>',
                '<MATH DEEP="40" SPAN="1"><MID>ER01JA20.001</MID></MATH>',
            )
        ),
    )
    assert build.units[0].passages[0].body == ("See the figure.", "Figure 1")
    assert (build.counts["images"], build.counts["formulas"]) == (1, 1)


def test_a_unit_with_only_a_heading_gets_one_passage() -> None:
    build = build_file(
        "t.xml",
        part(
            "<SECTION><SECTNO>§ 179.100-1</SECTNO>"
            "<SUBJECT>Tanks built under these specifications shall comply.</SUBJECT></SECTION>"
        ),
    )
    assert [(p.id, p.text) for u in build.units for p in u.passages] == [
        (
            "179.100-1:1",
            "§ 179.100-1 Tanks built under these specifications shall comply.",
        )
    ]
    assert build.counts["heading-only units"] == 1


def test_reserved_units_get_no_passage_and_are_counted() -> None:
    build = build_file(
        "t.xml",
        part(
            "<SECTION><SECTNO>§ 171.11</SECTNO><RESERVED>[Reserved]</RESERVED></SECTION>",
            "<APPENDIX><RESERVED>Appendixes E-G to Part 173 [Reserved]</RESERVED></APPENDIX>",
        ),
    )
    assert (build.units, build.counts["reserved units"]) == ((), 2)


def test_appendices_are_units_keyed_by_part_and_letter() -> None:
    (p,) = passages_of(
        part(
            "<APPENDIX><EAR>Pt. 178, Subpt. C, App. A</EAR>"
            '<HD SOURCE="HED">Appendix A to Subpart C of Part 178—Illustrations</HD><P>Text.</P></APPENDIX>'
        )
    )
    assert (p.id, p.text) == (
        "178.subptC.appA:1",
        "Appendix A to Subpart C of Part 178—Illustrations\nText.",
    )


def test_unit_keys() -> None:
    assert section_key("§\u2009173.304a") == "173.304a"
    assert section_key("§ 178.337-10") == "178.337-10"
    assert appendix_key("Pt. 172, App. A") == "172.appA"
    with pytest.raises(ValueError, match="Appendix A"):
        appendix_key("Appendix A")


def test_each_passage_records_the_printed_page_it_starts_on() -> None:
    data = part(
        section(
            "171.1",
            "S.",
            f"<P>{words(200)}</P>",
            '<PRTPAGE P="11"/>',
            f"<P>{words(200)}</P>",
        )
    )
    assert [p.page for p in passages_of(data)] == [10, 11]


def test_page_breaks_in_parts_left_out_still_count() -> None:
    data = part(
        section(
            "171.1",
            "S.",
            "<P>a</P>",
            '<EDNOTE><HD>Editorial Note:</HD><P>See <PRTPAGE P="11"/>the list.</P></EDNOTE>',
        ),
        section("171.2", "T.", "<P>b</P>"),
    )
    assert [p.page for p in passages_of(data)] == [10, 11]


def test_an_unknown_element_in_a_heading_names_its_unit() -> None:
    with pytest.raises(UnknownElement, match="BLINK.*171.1"):
        build_file("t.xml", part(section("171.1", "S. <BLINK>x</BLINK>", "<P>a</P>")))


def test_an_unknown_element_in_a_section_number_names_its_file() -> None:
    data = part(
        "<SECTION><SECTNO>§ 171.<BLINK>1</BLINK></SECTNO><SUBJECT>S.</SUBJECT></SECTION>"
    )
    with pytest.raises(UnknownElement, match="BLINK.*t.xml"):
        build_file("t.xml", data)


def test_unknown_element_stops_the_build() -> None:
    with pytest.raises(UnknownElement, match="BLINK.*171.1"):
        build_file("t.xml", part(section("171.1", "S.", "<BLINK>x</BLINK>")))


TABLE = (
    '<GPOTABLE COLS="3"><TTITLE>Table 1—Codes</TTITLE>'
    '<BOXHD><CHED H="1">Code</CHED><CHED H="1">Meaning</CHED><CHED H="1">Limit</CHED></BOXHD>'
    '<ROW><ENT I="01">IB1</ENT><ENT>Metal</ENT><ENT/></ROW>'
    '<ROW><ENT I="01">IB2</ENT><ENT>Plastic</ENT><ENT>5 L</ENT></ROW>'
    "<TNOTE>Note to the table.</TNOTE></GPOTABLE>"
)


def test_each_row_becomes_a_passage_with_its_labels() -> None:
    passages = passages_of(
        part(
            section(
                "172.102",
                "Special provisions.",
                "<P>Before.</P>",
                TABLE,
                "<P>After.</P>",
            )
        )
    )
    assert [(p.id, p.kind, p.body) for p in passages] == [
        ("172.102:1", "text", ("Before.",)),
        ("172.102:2", "row", ("IB1", "Metal")),
        ("172.102:3", "row", ("IB2", "Plastic", "5 L")),
        ("172.102:4", "text", ("Note to the table.",)),
        ("172.102:5", "text", ("After.",)),
    ]
    assert (
        passages[1].text
        == "§ 172.102 Special provisions.\nTable 1—Codes\nCode: IB1\nMeaning: Metal"
    )
    assert passages[2].labels == ("Code", "Meaning", "Limit")


def test_values_beyond_the_labelled_columns_keep_no_label() -> None:
    table = (
        '<GPOTABLE COLS="3"><BOXHD><CHED H="1">Pressure</CHED><CHED H="1">Density</CHED></BOXHD>'
        '<ROW><ENT I="01">17</ENT><ENT>52.8</ENT><ENT>6.60</ENT></ROW></GPOTABLE>'
    )
    build = build_file("t.xml", part(section("173.319", "S.", table)))
    assert (
        build.units[0].passages[0].text
        == "§ 173.319 S.\nPressure: 17\nDensity: 52.8\n6.60"
    )
    assert build.findings == ("173.319: a table with 3 columns has 2 column labels",)


def test_rows_are_counted() -> None:
    counts = build_file("t.xml", part(section("172.102", "S.", TABLE))).counts
    keys = ("tables", "rows", "row passages", "column-number rows", "empty rows")
    assert [counts[k] for k in keys] == [1, 2, 2, 0, 0]


def test_a_table_that_repeats_column_labels_is_reported() -> None:
    table = (
        '<GPOTABLE COLS="3"><BOXHD><CHED H="1">10 or less</CHED>'
        '<CHED H="1">10 or less</CHED><CHED H="1">Over 10</CHED></BOXHD>'
        '<ROW><ENT I="01">.100</ENT><ENT>.129</ENT><ENT>.157</ENT></ROW></GPOTABLE>'
    )
    build = build_file("t.xml", part(section("178.348-2", "S.", table)))
    assert build.findings == (
        "178.348-2: a table has 3 column labels, 2 of them distinct",
    )


def test_a_cell_that_may_span_columns_is_reported() -> None:
    table = (
        '<GPOTABLE COLS="2"><BOXHD><CHED H="1">Index</CHED><CHED H="1">Distance</CHED>'
        '</BOXHD><ROW><ENT I="01">Sum</ENT><ENT A="25">Cargo thickness</ENT></ROW>'
        "</GPOTABLE>"
    )
    build = build_file("t.xml", part(section("176.708", "S.", table)))
    assert build.findings == (
        '176.708: a table cell carries A="25", which the builder does not read',
    )
