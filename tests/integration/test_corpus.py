# Author: Nicola Antonello
import re
from collections import Counter
from pathlib import Path

from regulator_graded_rag.manifest import Manifest
from regulator_graded_rag.parse_checks import check_build
from regulator_graded_rag.passages import (
    FileBuild,
    Passage,
    UnitBuild,
    build_corpus,
    corpus_version,
)

COUNTS = {
    "units": 1069,
    "reserved units": 29,
    "heading-only units": 31,
    "tables": 215,
    "rows": 10350,
    "row passages": 10336,
    "column-number rows": 3,
    "empty rows": 11,
    "images": 125,
    "formulas": 32,
    "apparatus words": 27600,
}


def all_passages(builds: list[FileBuild]) -> list[Passage]:
    return [p for b in builds for u in b.units for p in u.passages]


def unit(builds: list[FileBuild], key: str) -> UnitBuild:
    return next(u for b in builds for u in b.units if u.unit.key == key)


def row(builds: list[FileBuild], key: str, needle: str) -> Passage:
    return next(
        p for p in unit(builds, key).passages if p.kind == "row" and needle in p.text
    )


def test_the_corpus_is_parts_171_to_180_of_the_2025_edition(
    manifest: Manifest, corpus_dir: Path
) -> None:
    assert [f.name for f in manifest.files] == [
        f"CFR-2025-title49-vol{2 if part <= 177 else 3}-part{part}.xml"
        for part in range(171, 181)
    ]
    assert (
        sum((corpus_dir / f.name).stat().st_size for f in manifest.files) == 9_266_626
    )


def test_every_parse_check_passes(corpus_build: list[FileBuild]) -> None:
    assert check_build(corpus_build) == []


def test_the_build_matches_the_manifest(
    manifest: Manifest, corpus_build: list[FileBuild]
) -> None:
    passages = all_passages(corpus_build)
    assert (len(passages), corpus_version(passages)) == (
        manifest.passages,
        manifest.version,
    )


def test_a_rebuild_gives_the_same_passages(
    manifest: Manifest, corpus_dir: Path, corpus_build: list[FileBuild]
) -> None:
    again = build_corpus(manifest, corpus_dir)
    assert corpus_version(all_passages(again)) == corpus_version(
        all_passages(corpus_build)
    )


def test_the_counts_match_the_xml(corpus_build: list[FileBuild]) -> None:
    counts = sum((b.counts for b in corpus_build), Counter[str]())
    assert {k: counts[k] for k in COUNTS} == COUNTS


def test_the_tables_whose_labels_may_mislead_are_reported(
    corpus_build: list[FileBuild],
) -> None:
    assert [f for b in corpus_build for f in b.findings] == [
        "173.301: a table has 2 column labels, 1 of them distinct",
        "173.319: a table with 6 columns has 5 column labels",
        "173.319: a table has 5 column labels, 3 of them distinct",
        "176.708: a table has 27 column labels, 10 of them distinct",
        '176.708: a table cell carries A="25", which the builder does not read',
        "178.275: a table has 4 column labels, 2 of them distinct",
        "178.348-2: a table has 15 column labels, 5 of them distinct",
        "178.348-2: a table has 15 column labels, 5 of them distinct",
    ]


def test_172_101_keeps_every_row_of_its_six_tables(
    corpus_build: list[FileBuild],
) -> None:
    rows = [p for p in unit(corpus_build, "172.101").passages if p.kind == "row"]
    assert len(rows) == 6384  # 6,386 rows, less the column-number row and one empty row


def test_hmt_rows_carry_their_column_numbers(corpus_build: list[FileBuild]) -> None:
    lines = row(corpus_build, "172.101", "proper shipping names: Acetone\n").text.split(
        "\n"
    )
    for line in (
        "(3) Hazard class or Division: 3",
        "(4) Identification Numbers: UN1090",
        "(5) PG: II",
        "(7) Special provisions (§ 172.102): IB2, T4, TP1",
        "(8A) (8) Packaging (§ 173.***) Exceptions: 150",
        "(9B) (9) Quantity limitations (see §§ 173.27 and 175.75) Cargo aircraft only: 60 L",
    ):
        assert line in lines


def test_173_435_exponents_keep_their_value(corpus_build: list[FileBuild]) -> None:
    lines = row(
        corpus_build, "173.435", "Symbol of radionuclide: Ac-225 (a)"
    ).text.split("\n")
    assert "A1 (TBq): 8.0 × 10^−1" in lines and "A1 (Ci) ^b: 2.2 × 10^1" in lines
    for key in ("173.435", "173.436"):
        rows = [p for p in unit(corpus_build, key).passages if p.kind == "row"]
        assert len(rows) == 383
        assert [p.id for p in rows if re.search("× 10[0-9−]", p.text)] == []


def test_the_minus_tagged_apart_from_its_exponent_stays_visible(
    corpus_build: list[FileBuild],
) -> None:
    lines = row(corpus_build, "173.435", "Symbol of radionuclide: Rb(nat)").text.split(
        "\n"
    )
    assert "Specific activity (TBq/g): 6.7 × 10 −^10" in lines


def test_172_102_splits_its_long_block_into_short_passages(
    corpus_build: list[FileBuild],
) -> None:
    passages = unit(corpus_build, "172.102").passages
    text = [p for p in passages if p.kind == "text"]
    assert max(len(" ".join(p.body).split()) for p in text) <= 250
    assert sum(1 for p in passages if p.kind == "row") == 83
    assert any(
        b.startswith("1 This material is poisonous by inhalation")
        for p in text
        for b in p.body
    )
    vessel = "340 This entry applies only to the vessel transportation"
    assert sum(1 for p in text if any(vessel in b for b in p.body)) == 1


def test_173_62_keeps_its_explosives_table_while_its_packing_methods_are_images(
    corpus_build: list[FileBuild],
) -> None:
    u = unit(corpus_build, "173.62")
    assert sum(1 for p in u.passages if p.kind == "row") == 381
    assert row(corpus_build, "173.62", "ID#: UN0004").text.endswith(
        "ID#: UN0004\nPI: 112"
    )
    assert sum(1 for el in u.unit.body for _ in el.iter("GPH")) == 15


def test_spacing_follows_the_source(corpus_build: list[FileBuild]) -> None:
    first = unit(corpus_build, "171.1").passages[0]
    assert "(49 U.S.C. 5101 et seq.) directs the Secretary" in first.text


def test_a_section_that_is_only_a_heading_is_one_passage(
    corpus_build: list[FileBuild],
) -> None:
    (p,) = unit(corpus_build, "179.100-1").passages
    assert p.text.startswith("§ 179.100-1 Tanks built under these specifications")
