# Author: Nicola Antonello
from datetime import date

from regulator_graded_rag.drift import check, parse_citation
from regulator_graded_rag.ecfr import EDITION_DAY, Cache, UnitText, parse_units


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


def test_section_pages_match_the_part_pages(
    ecfr_cache: Cache, ecfr_edition: dict[str, UnitText]
) -> None:
    for section in ("173.185", "172.101", "180.407", "178.337-10"):
        page = ecfr_cache.page(EDITION_DAY, section.split(".")[0], section)
        assert parse_units(page)[section] == ecfr_edition[section]
