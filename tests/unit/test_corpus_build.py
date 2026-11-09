# Author: Nicola Antonello
import hashlib
import io
import json
import runpy
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

import regulator_graded_rag.passages as passages_module
from regulator_graded_rag import parse_checks
from regulator_graded_rag.manifest import CorpusFile, Manifest
from regulator_graded_rag.passages import (
    build_corpus,
    build_file,
    corpus_version,
    main,
    write_passages,
)


def granule(number: str, text: str) -> bytes:
    return (
        f"<CFRGRANULE><PART><SECTION><SECTNO>§ {number}</SECTNO><SUBJECT>S.</SUBJECT>"
        f"<P>{text}</P></SECTION></PART></CFRGRANULE>"
    ).encode()


def entry(name: str, data: bytes) -> CorpusFile:
    return CorpusFile(
        name,
        f"https://www.govinfo.gov/x/{name}",
        len(data),
        hashlib.sha256(data).hexdigest(),
        "public domain (17 U.S.C. 105)",
    )


def test_files_are_built_in_manifest_order(tmp_path: Path) -> None:
    b, a = granule("172.1", "b"), granule("171.1", "a")
    (tmp_path / "b.xml").write_bytes(b)
    (tmp_path / "a.xml").write_bytes(a)
    manifest = Manifest(
        "2025", "2025-10-01", (entry("b.xml", b), entry("a.xml", a)), None, None
    )
    keys = [
        u.unit.key for build in build_corpus(manifest, tmp_path) for u in build.units
    ]
    assert keys == ["172.1", "171.1"]


def test_build_refuses_a_file_that_does_not_match_the_manifest(tmp_path: Path) -> None:
    data = granule("171.1", "a")
    (tmp_path / "a.xml").write_bytes(data + b" ")
    manifest = Manifest("2025", "2025-10-01", (entry("a.xml", data),), None, None)
    with pytest.raises(ValueError, match="regulator_graded_rag.fetch"):
        build_corpus(manifest, tmp_path)


def test_the_corpus_version_changes_exactly_when_an_id_or_a_text_changes() -> None:
    (p,) = [
        p
        for u in build_file("t.xml", granule("171.1", "a b")).units
        for p in u.passages
    ]
    version = corpus_version([p])
    assert len(version) == 64 and corpus_version([p]) == version
    assert corpus_version([replace(p, body=("a c",))]) != version
    assert corpus_version([replace(p, id="171.1:2")]) != version
    assert corpus_version([replace(p, page=99, source="other.xml")]) == version


def test_passages_are_written_as_json_lines_with_lf(tmp_path: Path) -> None:
    passages = [
        p for u in build_file("t.xml", granule("171.1", "a")).units for p in u.passages
    ]
    out = tmp_path / "parsed" / "passages.jsonl"
    write_passages(out, passages)
    data = out.read_bytes()
    assert b"\r" not in data and data.endswith(b"\n")
    assert json.loads(data) == {
        "id": "171.1:1",
        "kind": "text",
        "source": "t.xml",
        "page": 0,
        "text": "§ 171.1 S.\na",
    }


def test_main_compares_the_build_with_the_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = granule("171.1", "a")
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "a.xml").write_bytes(data)
    f = entry("a.xml", data)
    version = corpus_version(
        [p for u in build_file("a.xml", data).units for p in u.passages]
    )
    base = (
        f'edition = "2025"\nrevised = "2025-10-01"\n\n[[files]]\nname = "{f.name}"\nurl = "{f.url}"\n'
        f'size = {f.size}\nsha256 = "{f.sha256}"\nlicence = "{f.licence}"\n'
    )
    manifest = tmp_path / "manifest.toml"
    args = [
        "--manifest",
        str(manifest),
        "--raw",
        str(tmp_path / "raw"),
        "--out",
        str(tmp_path / "out.jsonl"),
    ]
    manifest.write_text(
        base + f'\n[passages]\ncount = 1\nversion = "{version}"\n', encoding="utf-8"
    )
    assert main(args) == 0 and "matches the manifest" in capsys.readouterr().out
    manifest.write_text(
        base + f'\n[passages]\ncount = 1\nversion = "{"0" * 64}"\n', encoding="utf-8"
    )
    assert main(args) == 1 and "differs from the manifest" in capsys.readouterr().out


def test_a_failure_prints_on_any_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Windows encodes a piped stdout as cp1252, which has no minus sign.
    data = (
        "<CFRGRANULE><PART><APPENDIX><EAR>Pt. 1" + chr(0x2212) + "2</EAR><HD>App.</HD>"
        "<P>a</P></APPENDIX></PART></CFRGRANULE>"
    ).encode()
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "a.xml").write_bytes(data)
    f = entry("a.xml", data)
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        f'edition = "2025"\nrevised = "2025-10-01"\n\n[[files]]\nname = "{f.name}"\n'
        f'url = "{f.url}"\nsize = {f.size}\nsha256 = "{f.sha256}"\nlicence = "{f.licence}"\n',
        encoding="utf-8",
    )
    console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)
    raw, out = str(tmp_path / "raw"), str(tmp_path / "out.jsonl")
    assert main(["--manifest", str(manifest), "--raw", raw, "--out", out]) == 1
    console.flush()
    assert b"FAILED: cannot read an appendix key" in console.buffer.getvalue()


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_the_command_hands_the_checks_the_package_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # python -m runs passages.py as __main__, a second copy of the module; the build must
    # still use the package's own types, the ones the checks import.
    data = granule("171.1", "a")
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "a.xml").write_bytes(data)
    f = entry("a.xml", data)
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        f'edition = "2025"\nrevised = "2025-10-01"\n\n[[files]]\nname = "{f.name}"\n'
        f'url = "{f.url}"\nsize = {f.size}\nsha256 = "{f.sha256}"\nlicence = "{f.licence}"\n',
        encoding="utf-8",
    )
    seen: list[bool] = []

    def spy(builds: Sequence[passages_module.FileBuild]) -> list[str]:
        seen.append(all(isinstance(b, passages_module.FileBuild) for b in builds))
        return []

    monkeypatch.setattr(parse_checks, "check_build", spy)
    raw, out = str(tmp_path / "raw"), str(tmp_path / "out.jsonl")
    argv = ["passages", "--manifest", str(manifest), "--raw", raw, "--out", out]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as stop:
        runpy.run_module("regulator_graded_rag.passages", run_name="__main__")
    assert (stop.value.code, seen) == (0, [True])
