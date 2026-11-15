# Author: Nicola Antonello
from regulator_graded_rag.ecfr import EDITION_DAY, Cache, UnitText, parse_units


def test_section_pages_match_the_part_pages(
    ecfr_cache: Cache, ecfr_edition: dict[str, UnitText]
) -> None:
    for section in ("173.185", "172.101", "180.407", "178.337-10"):
        page = ecfr_cache.page(EDITION_DAY, section.split(".")[0], section)
        assert parse_units(page)[section] == ecfr_edition[section]
