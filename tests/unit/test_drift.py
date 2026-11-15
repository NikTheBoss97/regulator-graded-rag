# Author: Nicola Antonello
from datetime import date
from pathlib import Path

import pytest

from regulator_graded_rag.drift import Citation, check, compare, parse_citation
from regulator_graded_rag.ecfr import Cache, UnitText
from regulator_graded_rag.fetch import Response
from tests.unit.test_ecfr import PAGE


def units(a: str, b: str) -> dict[str, UnitText]:
    return {"173.9": UnitText("173.9", f"{a} {b}", "", {"173.9(a)": a, "173.9(b)": b})}


def test_citations_are_parsed() -> None:
    assert parse_citation("§ 173.185(c)(1)(iii)") == Citation("173.185", "(c)(1)(iii)")
    assert parse_citation("178.337-10") == Citation("178.337-10")
    assert parse_citation("172.appA") == Citation("172.appA")
    with pytest.raises(ValueError, match="Part 107"):
        parse_citation("Part 107")


def test_outcomes() -> None:
    then, edition = units("(a) Old.", "(b) Same."), units("(a) New.", "(b) Same.")
    assert compare(Citation("173.9", "(b)"), then, edition) == "unchanged"
    assert compare(Citation("173.9", "(a)"), then, edition) == "changed"
    assert compare(Citation("173.9"), then, edition) == "changed"
    assert compare(Citation("173.9", "(c)"), then, edition) == "missing"
    assert compare(Citation("173.10"), then, edition) == "missing"


def test_a_paragraph_absent_on_one_day_only_is_missing() -> None:
    then = units("(a) Same.", "(b) Same.")
    edition = {"173.9": UnitText("173.9", "(a) Same.", "", {"173.9(a)": "(a) Same."})}
    assert compare(Citation("173.9", "(b)"), then, edition) == "missing"


def test_a_loose_paragraph_is_compared_by_its_whole_section() -> None:
    # The owner's ruling of 2026-11-15: content outside the cited paragraph that
    # follows it, such as a table, makes the whole section the comparison.
    def unit(table: str) -> dict[str, UnitText]:
        text = f"(b) Same, and the following table: {table}"
        loose = frozenset({"173.9(b)"})
        return {"173.9": UnitText("173.9", text, "", {"173.9(b)": "(b) Same."}, loose)}

    cited = Citation("173.9", "(b)")
    assert compare(cited, unit("Old row."), unit("New row.")) == "changed"
    assert compare(cited, unit("Old row."), unit("Old row.")) == "unchanged"


def test_a_changed_figure_changes_its_paragraph() -> None:
    # The owner's ruling of 2026-11-15: figures are compared by file name.
    def unit(figure: str) -> dict[str, UnitText]:
        figures = {"": (figure,), "173.9(a)": (figure,)}
        return {
            "173.9": UnitText(
                "173.9", "(a) A.", "", {"173.9(a)": "(a) A."}, figures=figures
            )
        }

    assert (
        compare(Citation("173.9", "(a)"), unit("ER1.gif"), unit("ER2.gif")) == "changed"
    )
    assert compare(Citation("173.9"), unit("ER1.gif"), unit("ER2.gif")) == "changed"
    assert (
        compare(Citation("173.9", "(a)"), unit("ER1.gif"), unit("ER1.gif"))
        == "unchanged"
    )


def test_a_section_absent_on_the_letters_day_is_missing(tmp_path: Path) -> None:
    def get(url: str) -> Response:
        if "/2017-06-01/" in url:
            return Response(404, "text/html", b"Not found")
        return Response(200, "text/html", PAGE.encode())

    cited = Citation("173.9", "(a)")
    assert check([cited], date(2017, 6, 1), Cache(tmp_path, get)) == {cited: "missing"}
