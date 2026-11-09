# Author: Nicola Antonello
from dataclasses import replace

from regulator_graded_rag.parse_checks import check_build, check_unit
from regulator_graded_rag.passages import build_file

SAMPLE = (
    '<CFRGRANULE><PART><SUBPART><PRTPAGE P="10"/>'
    '<SECTION><SECTNO>§ 173.435</SECTNO><SUBJECT>Table of A<E T="52">1</E> values.</SUBJECT>'
    '<P>(a) The first rule (49 U.S.C. 5101 <E T="03">et seq.</E>) applies to 1<FR>1/2</FR> inch.</P>'
    '<P>(b) A second <PRTPAGE P="11"/>rule.</P>'
    '<GPOTABLE COLS="2"><BOXHD><CHED H="1">Symbol</CHED><CHED H="1">A<E T="52">1</E> (TBq)</CHED></BOXHD>'
    '<ROW><ENT I="25">(1)</ENT><ENT>(2)</ENT></ROW>'
    '<ROW><ENT I="01">Ac-225</ENT><ENT>8.0 × 10<E T="51">−1</E></ENT></ROW>'
    '<ROW><ENT I="01"> </ENT></ROW>'
    "<TNOTE><SU>a</SU> A note.</TNOTE></GPOTABLE>"
    "<CITA>[69 FR 3678, Jan. 26, 2004]</CITA>"
    "</SECTION></SUBPART></PART></CFRGRANULE>"
).encode()


def test_a_correct_build_passes_every_check() -> None:
    assert check_build([build_file("t.xml", SAMPLE)]) == []


def test_a_dropped_word_is_caught() -> None:
    (unit,) = build_file("t.xml", SAMPLE).units
    first = unit.passages[0]
    broken = replace(first, body=(first.body[0].replace("first ", ""), *first.body[1:]))
    problems = check_unit(unit.unit, (broken, *unit.passages[1:]))
    assert any(p.startswith("173.435: text differs") for p in problems)


def test_a_repeated_passage_is_caught() -> None:
    (unit,) = build_file("t.xml", SAMPLE).units
    problems = check_unit(unit.unit, (*unit.passages, unit.passages[-1]))
    assert any(p.startswith("173.435: text differs") for p in problems)
    assert any(p.startswith("173.435: passage IDs") for p in problems)


def test_a_lost_row_is_caught() -> None:
    (unit,) = build_file("t.xml", SAMPLE).units
    kept = tuple(p for p in unit.passages if p.kind != "row")
    assert (
        "173.435: 0 row passages for 3 rows (1 column-number, 1 empty)"
        in check_unit(unit.unit, kept)
    )


def test_a_unit_without_passages_is_caught() -> None:
    (unit,) = build_file("t.xml", SAMPLE).units
    assert check_unit(unit.unit, ()) == ["173.435: no passage"]


def test_duplicate_ids_across_files_are_caught() -> None:
    build = build_file("t.xml", SAMPLE)
    assert "duplicate passage ID 173.435:1" in check_build([build, build])


def test_problems_print_on_any_console() -> None:
    # Windows encodes a pipe as cp1252, so the quoted text must come out as ASCII.
    (unit,) = build_file("t.xml", SAMPLE).units
    text, row, note = unit.passages
    broken = replace(row, body=(row.body[0], row.body[1].replace("−", "")))
    problems = check_unit(unit.unit, (text, broken, note))
    assert problems and all(problem.isascii() for problem in problems)
