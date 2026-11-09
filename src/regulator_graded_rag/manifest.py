# Author: Nicola Antonello
"""The corpus manifest: the files that make the corpus, and the bytes each must have.

corpus/manifest.toml names each file of the edition with its URL, size, SHA-256 and
licence, and, once the passage builder has run, the passage count and corpus version
they give (ADR-0006). No downloaded file is parsed until its bytes match its entry.
"""

import hashlib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

# Commands run from the repository root.
DEFAULT_MANIFEST = Path("corpus/manifest.toml")
DEFAULT_RAW = Path("corpus/raw")
GOVINFO = "https://www.govinfo.gov/"
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class CorpusFile:
    name: str
    url: str
    size: int
    sha256: str
    licence: str


@dataclass(frozen=True)
class Manifest:
    edition: str
    revised: str
    files: tuple[CorpusFile, ...]
    passages: int | None
    version: str | None


def _entry_problem(entry: CorpusFile) -> str | None:
    if not entry.url.startswith(GOVINFO):
        return f"url must start with {GOVINFO}"
    if not entry.url.endswith(f"/{entry.name}"):
        return f"url must end with /{entry.name}"
    if not _SHA256.fullmatch(entry.sha256):
        return "sha256 must be 64 lowercase hex characters"
    if entry.size <= 0:
        return "size must be positive"
    if not entry.licence.strip():
        return "licence is empty"
    return None


def load_manifest(path: Path) -> Manifest:
    """Read a manifest and check every entry; a problem raises ValueError."""
    with path.open("rb") as file:
        data = tomllib.load(file)
    files: list[CorpusFile] = []
    for item in data["files"]:
        entry = CorpusFile(
            item["name"], item["url"], item["size"], item["sha256"], item["licence"]
        )
        if problem := _entry_problem(entry):
            raise ValueError(f"{entry.name}: {problem}")
        if any(f.name == entry.name for f in files):
            raise ValueError(f"{entry.name} is listed twice")
        files.append(entry)
    count: int | None = None
    version: str | None = None
    if "passages" in data:
        count = data["passages"].get("count")
        version = data["passages"].get("version")
        if not (
            isinstance(count, int)
            and count > 0
            and isinstance(version, str)
            and _SHA256.fullmatch(version)
        ):
            raise ValueError(
                "[passages] needs a positive count and a version of 64 lowercase hex"
                " characters"
            )
    return Manifest(data["edition"], data["revised"], tuple(files), count, version)


def check_bytes(entry: CorpusFile, data: bytes) -> str | None:
    """None when the bytes have the entry's size and SHA-256; otherwise what differs."""
    if len(data) != entry.size:
        return f"size {len(data)} differs from the manifest's {entry.size}"
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry.sha256:
        return f"SHA-256 {digest} differs from the manifest's {entry.sha256}"
    return None
