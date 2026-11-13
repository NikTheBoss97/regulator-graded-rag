# Author: Nicola Antonello
import json
from pathlib import Path

import pytest

from regulator_graded_rag.passages import version_of
from regulator_graded_rag.review import Record, choose, main, pdf_url, sheet


def pool(unit: str, kind: str, n: int, start: int) -> list[Record]:
    part = unit.split(".")[0]
    return [
        Record(
            id=f"{unit}:{i}",
            kind=kind,
            source=f"CFR-2025-title49-vol2-part{part}.xml",
            page=100 + i,
            text=f"{unit} {kind} {i}",
        )
        for i in range(start, start + n)
    ]


RECORDS: list[Record] = [
    *pool("172.101", "row", 30, 1),
    *pool("172.102", "text", 10, 1),
    *pool("172.102", "row", 10, 11),
    *pool("173.62", "row", 10, 1),
    Record(
        id="173.319:1",
        kind="row",
        source="CFR-2025-title49-vol2-part173.xml",
        page=763,
        text="§ 173.319 C.\nTable 1 to § 173.319(d)(2)—Pressure",
    ),
    *pool("173.435", "row", 10, 1),
    Record(
        id="173.435:99",
        kind="row",
        source="CFR-2025-title49-vol2-part173.xml",
        page=794,
        text="§ 173.435 T.\nSymbol of radionuclide: Rb(nat)",
    ),
    Record(
        id="176.708:6",
        kind="row",
        source="CFR-2025-title49-vol2-part176.xml",
        page=905,
        text="§ 176.708 S.\nTable IV\nSum of transport indexes of the packages: 0.6 to 1",
    ),
    Record(
        id="178.348-2:3",
        kind="row",
        source="CFR-2025-title49-vol3-part178.xml",
        page=310,
        text="§ 178.348-2 M.\nTable I\n10 or less: .100",
    ),
]


def test_the_sample_is_drawn_by_the_seed_and_holds_the_known_quirks() -> None:
    chosen = choose(RECORDS, seed=2025)
    assert [r["id"] for r in chosen] == [r["id"] for r in choose(RECORDS, seed=2025)]
    assert [r["id"] for r in chosen] != [r["id"] for r in choose(RECORDS, seed=1)]
    assert len(chosen) == 25
    quirks = {"173.435:99", "173.319:1", "176.708:6", "178.348-2:3"}
    assert quirks <= {r["id"] for r in chosen}


def test_seed_2025_draws_the_same_sample_on_every_platform() -> None:
    # Pinned, so CI on Linux checks the draw made on Windows, in file order. A Python
    # release that changed random.sample would fail here too.
    assert [r["id"] for r in choose(RECORDS, seed=2025)] == [
        "172.101:1",
        "172.101:3",
        "172.101:6",
        "172.101:16",
        "172.101:17",
        "172.101:18",
        "172.101:21",
        "172.101:27",
        "172.102:2",
        "172.102:4",
        "172.102:10",
        "172.102:16",
        "172.102:17",
        "173.62:1",
        "173.62:2",
        "173.62:7",
        "173.62:10",
        "173.319:1",
        "173.435:1",
        "173.435:2",
        "173.435:4",
        "173.435:7",
        "173.435:99",
        "176.708:6",
        "178.348-2:3",
    ]


def test_pdf_links_name_the_volume_and_section() -> None:
    assert pdf_url("173.435", "CFR-2025-title49-vol2-part173.xml") == (
        "https://www.govinfo.gov/content/pkg/CFR-2025-title49-vol2/pdf/CFR-2025-title49-vol2-sec173-435.pdf"
    )
    assert pdf_url("178.348-2", "CFR-2025-title49-vol3-part178.xml").endswith(
        "/CFR-2025-title49-vol3/pdf/CFR-2025-title49-vol3-sec178-348-2.pdf"
    )


def test_the_sheet_shows_each_passage_with_an_open_verdict() -> None:
    text = sheet(choose(RECORDS, seed=2025), RECORDS, version="ab" * 32, seed=2025)
    assert text.startswith("<!-- Author: Nicola Antonello -->\n")
    assert text.count("- [ ] Matches the printed page") == 25
    assert "Symbol of radionuclide: Rb(nat)" in text and "ab" * 32 in text


def test_the_sheet_sends_each_passage_to_its_page_of_the_section_pdf() -> None:
    text = sheet(choose(RECORDS, seed=2025), RECORDS, version="ab" * 32, seed=2025)
    # 172.101's first passage is on page 101, so its passage on page 116 is on page 16.
    assert (
        "Printed page 116 of volume 2: page 16 of [the section PDF]"
        "(https://www.govinfo.gov/content/pkg/CFR-2025-title49-vol2/pdf/"
        "CFR-2025-title49-vol2-sec172-101.pdf)."
    ) in text.splitlines()


def write_inputs(tmp_path: Path, version: str) -> tuple[Path, Path]:
    passages = tmp_path / "passages.jsonl"
    lines = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in RECORDS)
    passages.write_bytes(lines.encode("utf-8"))
    manifest = tmp_path / "manifest.toml"
    manifest.write_bytes(
        (
            'edition = "2025"\nrevised = "2025-10-01"\n\n[[files]]\nname = "a.xml"\n'
            f'url = "https://www.govinfo.gov/x/a.xml"\nsize = 1\nsha256 = "{"0" * 64}"\n'
            'licence = "public domain (17 U.S.C. 105)"\n\n'
            f'[passages]\ncount = {len(RECORDS)}\nversion = "{version}"\n'
        ).encode()
    )
    return passages, manifest


def test_main_writes_the_sheet_for_the_manifest_version(tmp_path: Path) -> None:
    version = version_of((r["id"], r["text"]) for r in RECORDS)
    passages, manifest = write_inputs(tmp_path, version)
    out = tmp_path / "parse-review.md"
    args = ["--passages", str(passages), "--manifest", str(manifest), "--out", str(out)]
    assert main(args) == 0
    data = out.read_bytes()
    assert b"\r" not in data and data.count(b"- [ ] Matches the printed page") == 25
    assert version.encode() in data


def test_main_refuses_passages_the_manifest_does_not_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    passages, manifest = write_inputs(tmp_path, "0" * 64)
    out = tmp_path / "parse-review.md"
    args = ["--passages", str(passages), "--manifest", str(manifest), "--out", str(out)]
    assert main(args) == 1
    assert not out.exists()
    assert "differ from the manifest" in capsys.readouterr().out


def test_main_keeps_an_existing_sheet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    version = version_of((r["id"], r["text"]) for r in RECORDS)
    passages, manifest = write_inputs(tmp_path, version)
    out = tmp_path / "parse-review.md"
    out.write_bytes(b"- [x] Matches the printed page\n")
    args = ["--passages", str(passages), "--manifest", str(manifest), "--out", str(out)]
    assert main(args) == 1
    assert out.read_bytes() == b"- [x] Matches the printed page\n"
    assert "--force" in capsys.readouterr().out


def test_force_replaces_an_existing_sheet(tmp_path: Path) -> None:
    version = version_of((r["id"], r["text"]) for r in RECORDS)
    passages, manifest = write_inputs(tmp_path, version)
    out = tmp_path / "parse-review.md"
    out.write_bytes(b"- [x] Matches the printed page\n")
    args = ["--passages", str(passages), "--manifest", str(manifest), "--out", str(out)]
    assert main([*args, "--force"]) == 0
    assert out.read_bytes().count(b"- [ ] Matches the printed page") == 25
