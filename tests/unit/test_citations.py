# Author: Nicola Antonello
import pytest

from regulator_graded_rag.citations import (
    Cited,
    cite,
    definitions,
    item_type,
    table_units,
)
from regulator_graded_rag.ecfr import UnitText
from regulator_graded_rag.review import Record

DEFINITIONS = {
    "hazmat employee": "Hazmat%20employee",
    "non-bulk packaging": "Non-bulk%20packaging",
}


@pytest.mark.parametrize(
    ("text", "corpus", "outside"),
    [
        ("According to § 172.301(a), the number follows.", ("172.301(a)",), ()),
        ("See §§ 172.504 and 172.516.", ("172.504", "172.516"), ()),
        ("Under §§ 173.24(b) and (c), it must.", ("173.24(b)", "173.24(c)"), ()),
        ("Paragraph (b) of § 173.24 requires it.", ("173.24(b)",), ()),
        ("The 49 CFR 175.75(c) exception applies.", ("175.75(c)",), ()),
        ("Appendix B to Part 172 lists it.", ("172.appB",), ()),
        (
            "A special permit under § 107.105 and Part 107.",
            (),
            ("107.105", "Part 107"),
        ),
        (
            'See the definition of "hazmat employee" in § 171.8.',
            ("171.8(Hazmat%20employee)",),
            (),
        ),
        (
            '"Non-bulk packaging" is defined in § 171.8 as a packaging.',
            ("171.8(Non-bulk%20packaging)",),
            (),
        ),
        (
            'See the definition of "hazmat employer" in § 171.8.',
            ("171.8(Hazmat%20employer)",),
            (),
        ),
        ("A person, as defined in § 171.8.", ("171.8",), ()),
        # Beyond the plan's list: "Section" as the marker, and curly quotes.
        ("Section 173.185(b) requires it.", ("173.185(b)",), ()),
        (
            "Under the definition of “hazmat employee” in § 171.8, it is.",
            ("171.8(Hazmat%20employee)",),
            (),
        ),
    ],
)
def test_citations_become_evidence_labels(
    text: str, corpus: tuple[str, ...], outside: tuple[str, ...]
) -> None:
    assert cite(text, DEFINITIONS) == Cited(corpus, outside)


TERMS = DEFINITIONS | {
    term.lower(): term.replace(" ", "%20")
    for term in (
        "Transport vehicle",
        "Marine pollutant",
        "Gross weight",
        "Cargo tank",
        "Motor vehicle",
        "Atmospheric gases",
        "Person",
        "Packaging",
    )
}


@pytest.mark.parametrize(
    ("text", "corpus"),
    [
        # Beyond the plan's two quoted forms: the ways dev answers name a definition,
        # measured on 2026-11-16. An unquoted term counts only when eCFR defines it.
        (
            "As defined in § 171.8, a hazmat employee is a person who loads packages.",
            ("171.8(Hazmat%20employee)",),
        ),
        (
            "A transport vehicle is defined in § 171.8 as a cargo-carrying vehicle.",
            ("171.8(Transport%20vehicle)",),
        ),
        (
            "No, unless it meets the definition of a marine pollutant (see § 171.8).",
            ("171.8(Marine%20pollutant)",),
        ),
        (
            (
                "Section 171.8 defines gross weight as the weight of a packaging plus its"
                " contents."
            ),
            ("171.8(Gross%20weight)",),
        ),
        (
            'The definition of a "cargo tank" as specified in § 171.8 is narrow.',
            ("171.8(Cargo%20tank)",),
        ),
        (
            'It refers to the term "motor vehicle" as defined in § 171.8.',
            ("171.8(Motor%20vehicle)",),
        ),
        ("A person, as defined in § 171.8, may do so.", ("171.8(Person)",)),
        ("See § 171.8 for the rules on packing.", ("171.8",)),
    ],
)
def test_definitions_named_in_other_forms(text: str, corpus: tuple[str, ...]) -> None:
    assert cite(text, TERMS).corpus == corpus


def test_the_editions_definitions_by_term() -> None:
    unit = UnitText(
        "171.8",
        "",
        "",
        {
            "171.8(Hazmat%20employee)": "x",
            "171.8(Hazmat%20employee)(1)": "y",
            "171.8(Aerosol)": "z",
        },
    )
    assert definitions({"171.8": unit}) == {
        "hazmat employee": "Hazmat%20employee",
        "aerosol": "Aerosol",
    }


def test_a_table_section_is_mostly_table_rows() -> None:
    def rec(id_: str, kind: str) -> Record:
        return {"id": id_, "kind": kind, "source": "t.xml", "page": 1, "text": "x"}

    passages = [
        rec("172.101:1", "text"),
        *(rec(f"172.101:{n}", "row") for n in (2, 3)),
        rec("171.8:1", "row"),
        *(rec(f"171.8:{n}", "text") for n in (2, 3)),
    ]
    assert table_units(passages) == {"172.101"}


@pytest.mark.parametrize(
    ("cited", "expected"),
    [
        (Cited((), ("Part 107",)), "unanswerable"),
        (Cited(("172.101(c)",), ()), "table"),
        (Cited(("172.301(a)", "172.504"), ()), "table"),
        (Cited(("172.301(a)", "172.301(b)"), ()), "lookup"),
        (Cited(("172.301(a)", "173.24"), ()), "multi_passage"),
        (Cited(("172.301(a)",), ("Part 107",)), "lookup"),
    ],
)
def test_the_first_type_that_applies(cited: Cited, expected: str) -> None:
    assert item_type(cited, {"172.101", "172.504"}) == expected


UNITS = (
    "178.68",
    "178.69",
    "178.70",
    "178.71",
    "178.72",
    "173.24",
    "173.24a",
    "173.24b",
)


@pytest.mark.parametrize(
    ("text", "corpus"),
    [
        # Review: a range gives every member, and a bare paragraph after a deeper one
        # replaces the level of its kind (the CFR's (a), (1), (i), (A) levels).
        (
            "Under § 178.601(g)(2)(ii)-(vii), it must.",
            tuple(f"178.601(g)(2)({r})" for r in ("ii", "iii", "iv", "v", "vi", "vii")),
        ),
        ("See §§ 178.69 through 178.71.", ("178.69", "178.70", "178.71")),
        ("See §§ 178.69-178.71.", ("178.69", "178.70", "178.71")),
        (
            "Under §§ 173.24(a) through (c), it must.",
            ("173.24(a)", "173.24(b)", "173.24(c)"),
        ),
        ("See § 173.115(b)(1) and (2).", ("173.115(b)(1)", "173.115(b)(2)")),
        (
            "Paragraphs (b)(1) and (2) of § 173.24 apply.",
            ("173.24(b)(1)", "173.24(b)(2)"),
        ),
        (
            "Paragraphs (a) through (c) of § 173.24 apply.",
            ("173.24(a)", "173.24(b)", "173.24(c)"),
        ),
        ("See § 178.345-1(c).", ("178.345-1(c)",)),
        (
            "See §§ 173.24 and 173.24a through 173.24b.",
            ("173.24", "173.24a", "173.24b"),
        ),
    ],
)
def test_ranges_and_bare_paragraphs_give_every_label(
    text: str, corpus: tuple[str, ...]
) -> None:
    assert cite(text, DEFINITIONS, UNITS).corpus == corpus


def test_or_definitions_answer_to_either_name() -> None:
    # Review: eCFR keys 18 definitions as "X or Y", and answers name one of them.
    unit = UnitText(
        "171.8",
        "",
        "",
        {
            "171.8(Gross%20weight%20or%20Gross%20mass)": "a",
            "171.8(Package%20or%20Outside%20Package)": "b",
            "171.8(Outside%20package)": "c",
            "171.8(Ab%20or%20Bc)": "d",
            "171.8(Bc%20or%20Cd)": "e",
        },
    )
    terms = definitions({"171.8": unit})
    assert terms["gross weight"] == terms["gross mass"]
    assert terms["gross mass"] == "Gross%20weight%20or%20Gross%20mass"
    assert terms["package"] == "Package%20or%20Outside%20Package"
    assert terms["outside package"] == "Outside%20package"
    assert "bc" not in terms
    text = "Section 171.8 defines gross weight as the weight of a packaging."
    assert cite(text, terms).corpus == ("171.8(Gross%20weight%20or%20Gross%20mass)",)


@pytest.mark.parametrize(
    ("text", "corpus"),
    [
        (
            'The HMR defines a "motor vehicle" in § 171.8 as a vehicle.',
            ("171.8(Motor%20vehicle)",),
        ),
        (
            'It applies to "atmospheric gases" such as nitrogen—see § 171.8—and helium.',
            ("171.8(Atmospheric%20gases)",),
        ),
        ('See the definition of "?" in § 171.8.', ("171.8",)),
    ],
)
def test_more_ways_to_name_a_definition(text: str, corpus: tuple[str, ...]) -> None:
    assert cite(text, TERMS).corpus == corpus
