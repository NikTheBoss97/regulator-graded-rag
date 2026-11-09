# Author: Nicola Antonello
import hashlib
from pathlib import Path

import pytest

from regulator_graded_rag.manifest import CorpusFile, check_bytes, load_manifest

ABC_SHA256 = hashlib.sha256(b"abc").hexdigest()
NAME = "CFR-2025-title49-vol2-part171.xml"
URL = f"https://www.govinfo.gov/content/pkg/CFR-2025-title49-vol2/xml/{NAME}"
GOOD = f'''\
edition = "2025"
revised = "2025-10-01"

[[files]]
name = "{NAME}"
url = "{URL}"
size = 3
sha256 = "{ABC_SHA256}"
licence = "public domain (17 U.S.C. 105)"
'''


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "manifest.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_manifest_lists_each_file(tmp_path: Path) -> None:
    manifest = load_manifest(write(tmp_path, GOOD))
    assert (manifest.edition, manifest.revised) == ("2025", "2025-10-01")
    assert manifest.files == (
        CorpusFile(NAME, URL, 3, ABC_SHA256, "public domain (17 U.S.C. 105)"),
    )
    assert (manifest.passages, manifest.version) == (None, None)


def test_manifest_reads_the_expected_passages(tmp_path: Path) -> None:
    text = GOOD + f'\n[passages]\ncount = 2\nversion = "{"0" * 64}"\n'
    manifest = load_manifest(write(tmp_path, text))
    assert (manifest.passages, manifest.version) == (2, "0" * 64)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (f'/{NAME}"', '/CFR-2025-title49-vol2-part172.xml"', "end with"),
        ("https://www.govinfo.gov/", "https://example.com/", "govinfo"),
        (ABC_SHA256, "abc", "sha256"),
        ("size = 3", "size = 0", "size"),
    ],
)
def test_manifest_rejects_a_bad_entry(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        load_manifest(write(tmp_path, GOOD.replace(old, new)))


def test_manifest_rejects_a_file_listed_twice(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="twice"):
        load_manifest(write(tmp_path, GOOD + GOOD[GOOD.index("[[files]]") :]))


def test_check_bytes_names_the_difference() -> None:
    entry = CorpusFile(NAME, URL, 3, ABC_SHA256, "public domain (17 U.S.C. 105)")
    assert check_bytes(entry, b"abc") is None
    assert check_bytes(entry, b"abcd") == "size 4 differs from the manifest's 3"
    assert check_bytes(entry, b"abd") == (
        f"SHA-256 {hashlib.sha256(b'abd').hexdigest()} differs from the manifest's {ABC_SHA256}"
    )
