# Author: Nicola Antonello
from datetime import date

from regulator_graded_rag.drift import check, compare, parse_citation
from regulator_graded_rag.ecfr import (
    EDITION_DAY,
    Cache,
    UnitText,
    characters,
    parse_units,
)
from regulator_graded_rag.parse_checks import reference_characters
from regulator_graded_rag.passages import FileBuild, Unit

# Units whose eCFR text differs from the corpus's, each with the owner's dated ruling.
# Plan 2c brings an item citing one of them to the owner, flagged.
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


def govinfo(unit: Unit) -> tuple[str, str]:
    """The unit's rule characters without its footnotes, and the footnotes' characters.

    A section's footnotes sit in different places, so each FTNT element's characters are
    taken out of the text one element at a time, in order.
    """
    text = characters(reference_characters(unit))
    notes = []
    for footnote in (e for top in unit.body for e in top.iter("FTNT")):
        note = characters("".join(footnote.itertext()))
        if note and (at := text.find(note)) >= 0:
            text = text[:at] + text[at + len(note) :]
            notes.append(note)
    return text, "".join(notes)


def test_ecfr_on_the_edition_day_is_the_corpus(
    corpus_build: list[FileBuild], ecfr_edition: dict[str, UnitText]
) -> None:
    units = {u.unit.key: u.unit for b in corpus_build for u in b.units}
    differ = []
    for key, unit in units.items():
        text, notes = govinfo(unit)
        e = ecfr_edition.get(key)
        if key not in KNOWN_DIFFERENCES and (
            e is None or (characters(e.text), characters(e.footnotes)) != (text, notes)
        ):
            differ.append(key)
    assert differ == []
    # Units eCFR keeps that the corpus has as reserved.
    assert len(set(ecfr_edition) - set(units)) == 28


def outcomes(day: date, cache: Cache, *labels: str) -> list[str]:
    result = check([parse_citation(x) for x in labels], day, cache)
    return [result[parse_citation(x)] for x in labels]


def test_known_drift_outcomes(ecfr_cache: Cache) -> None:
    # Measured on 2026-11-14, when the plan was written.
    assert outcomes(
        date(2018, 1, 2),
        ecfr_cache,
        "173.185(a)(1)(i)",
        "173.185(a)",
        "173.185(c)(4)(v)",
    ) == ["unchanged", "changed", "missing"]
    assert outcomes(
        date(2020, 6, 1), ecfr_cache, "173.150(b)(2)", "173.150(c)", "173.150"
    ) == ["unchanged", "changed", "changed"]


def test_a_section_never_amended_since_2017_is_unchanged(ecfr_cache: Cache) -> None:
    assert outcomes(date(2017, 6, 1), ecfr_cache, "171.3") == ["unchanged"]


def test_paragraphs_with_content_outside_their_div_are_compared_whole(
    ecfr_edition: dict[str, UnitText],
) -> None:
    # Measured on 2026-11-15: §172.400's label table follows paragraph (b)'s div, and
    # §176.63 marks its paragraphs on p elements; both compare by the whole section.
    assert "172.400(b)" in ecfr_edition["172.400"].loose
    assert ecfr_edition["176.63"].paragraphs == {}
    assert (
        compare(parse_citation("176.63(e)"), ecfr_edition, ecfr_edition) == "unchanged"
    )


def test_section_pages_match_the_part_pages(
    ecfr_cache: Cache, ecfr_edition: dict[str, UnitText]
) -> None:
    for section in ("173.185", "172.101", "180.407", "178.337-10"):
        page = ecfr_cache.page(EDITION_DAY, section.split(".")[0], section)
        assert parse_units(page)[section] == ecfr_edition[section]
