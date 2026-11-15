# Author: Nicola Antonello
"""List the regulator's interpretation letters that the Internet Archive holds, and fetch them.

Usage: python -m regulator_graded_rag.letters [--list | --skeletons] [--letters PATH]
[--split PATH], from the repository root.

- --list reads the archive's index of PHMSA's letter pages (its CDX API), keeps every
  letter whose reference number is from 2017 on, and fetches each letter the manifest
  (eval/letters.jsonl) lacks or recorded as unreadable: of its captures, the newest that
  reads as a letter page, trying at most three, newest first. The manifest is rewritten
  after each letter, so a stopped run resumes where it stopped. Once the split exists the
  pool is frozen, and --list is refused.
- With no option, every letter in the manifest is checked against its recorded size and
  SHA-256, and a missing or changed file is fetched again from its recorded capture.
- --skeletons prints the structure, never the text, of the pages no capture could read.

Requests to the archive start at least 3 seconds apart (see polite). Until the split,
every letter file lives under eval/heldout/unsplit/, which is git-ignored and guarded like
the held-out split, because nobody reads a letter before the split is drawn. Nothing here
prints a letter's text: only reference numbers, years, sizes, layouts and page structure.
Exit code 0 when every letter is in the manifest with its bytes, 1 when one failed.
"""

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.parse
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from regulator_graded_rag.fetch import FetchError, Get, Response, http_get
from regulator_graded_rag.letter_page import read_page, signature, skeleton
from regulator_graded_rag.polite import Paced

CDX = "https://web.archive.org/cdx/search/cdx"
INDEX = {
    "url": "www.phmsa.dot.gov/regulations/title49/interp/*",
    "output": "json",
    "fl": "original,timestamp,mimetype,statuscode",
    "filter": "statuscode:200",
    "limit": "60000",
    "showResumeKey": "true",
}
LETTER_PATH = re.compile(r"/regulations/title49/interp/(\d{2})-(\d{4})/?$")
FIRST_YEAR = 2017
LAST_YEAR: int | None = (
    None  # no upper bound: 2026's letters are in the pool (ADR-0008)
)
ARCHIVE_INTERVAL = 3.0
TRIES = 3

# Commands run from the repository root.
DEFAULT_LETTERS = Path("eval/letters.jsonl")
UNSPLIT = Path("eval/heldout/unsplit")
DEV_LETTERS = Path("eval/letters/dev")
HELDOUT_LETTERS = Path("eval/heldout/letters")
SPLIT_FILE = Path("eval/split.jsonl")


@dataclass(frozen=True, order=True)
class Capture:
    id: str
    timestamp: str
    original: str

    @property
    def url(self) -> str:
        """The capture's original bytes, without the archive's toolbar."""
        return f"https://web.archive.org/web/{self.timestamp}id_/{self.original}"


@dataclass(frozen=True)
class Letter:
    id: str
    year: int
    capture: str
    original: str
    layout: str  # "" when no capture could be read as a letter page
    size: int
    sha256: str


def letter_year(letter_id: str) -> int:
    """The reference year, from the number's first two digits.

    They are read as POSIX reads a two-digit year: 69 to 99 are 1969 to 1999, so the
    letters numbered 96- to 99- are the 1990s', and 00 to 68 are 2000 to 2068.
    """
    two = int(letter_id[:2])
    return (1900 if two >= 69 else 2000) + two


def html_of(data: bytes) -> str:
    """A page's bytes as text for the parser; a byte that is not UTF-8 is replaced."""
    return data.decode("utf-8", errors="replace")


def index_pages(get: Get) -> Iterator[list[list[str]]]:
    """The archive's index, one page per request, each its header row and captures.

    A page with more after it ends with an empty row and a row holding only the resume
    key, which the next request passes on as resumeKey.
    """
    params = dict(INDEX)
    while True:
        response = get(f"{CDX}?{urllib.parse.urlencode(params)}")
        if response.status != 200:
            raise FetchError(f"the archive's index answered HTTP {response.status}")
        rows: list[list[str]] = json.loads(response.body)
        if len(rows) >= 2 and rows[-2] == [] and len(rows[-1]) == 1:
            params["resumeKey"] = rows[-1][0]
            yield rows[:-2]
        else:
            yield rows
            return


def read_index(
    pages: Iterable[Sequence[Sequence[str]]],
) -> tuple[dict[str, list[Capture]], Counter[str]]:
    """Each letter's HTML captures, oldest first, and what was left out and why."""
    captures: dict[str, list[Capture]] = {}
    counts: Counter[str] = Counter()
    for page in pages:
        if not page:
            continue
        header, *rows = page
        column = {name: i for i, name in enumerate(header)}
        for row in rows:
            original = row[column["original"]]
            parts = urllib.parse.urlsplit(original)
            match = LETTER_PATH.fullmatch(parts.path)
            letter_id = f"{match[1]}-{match[2]}" if match else ""
            if row[column["statuscode"]] != "200":
                counts["not 200"] += 1
            elif row[column["mimetype"]] != "text/html":
                counts["not HTML"] += 1
            elif not letter_id or parts.query:
                counts["other URL shapes"] += 1
            elif not _in_years(letter_year(letter_id)):
                counts["outside the years"] += 1
            else:
                capture = Capture(letter_id, row[column["timestamp"]], original)
                captures.setdefault(letter_id, []).append(capture)
                counts["kept"] += 1
    return {k: sorted(v) for k, v in sorted(captures.items())}, counts


def _in_years(year: int) -> bool:
    return year >= FIRST_YEAR and (LAST_YEAR is None or year <= LAST_YEAR)


def _media_type(response: Response) -> str:
    return response.content_type.split(";", 1)[0].strip().lower()


def _digest(data: bytes) -> tuple[int, str]:
    return len(data), hashlib.sha256(data).hexdigest()


def _keep(capture: Capture, data: bytes, layout: str, dest: Path) -> Letter:
    """Write the page to dest/{id}.html through a .part file, and describe it."""
    dest.mkdir(parents=True, exist_ok=True)
    part = dest / f"{capture.id}.html.part"
    part.write_bytes(data)
    os.replace(part, dest / f"{capture.id}.html")
    size, sha256 = _digest(data)
    return Letter(
        capture.id,
        letter_year(capture.id),
        capture.timestamp,
        capture.original,
        layout,
        size,
        sha256,
    )


def fetch_letter(captures: Sequence[Capture], dest: Path, get: Get) -> Letter:
    """Keep the newest of at most TRIES captures that reads as a letter page.

    A redirect, another status or a media type other than text/html moves on to the next
    capture. When no capture reads, the newest HTML page is kept with layout "".
    """
    unreadable: tuple[Capture, bytes] | None = None
    for capture in sorted(captures, reverse=True)[:TRIES]:
        response = get(capture.url)
        if response.status != 200 or _media_type(response) != "text/html":
            continue
        page = read_page(html_of(response.body))
        if page is not None:
            return _keep(capture, response.body, page.layout, dest)
        unreadable = unreadable or (capture, response.body)
    if unreadable is None:
        raise FetchError(f"{captures[0].id}: no capture gave a page")
    return _keep(*unreadable, "", dest)


def load_letters(path: Path) -> list[Letter]:
    with path.open(encoding="utf-8") as file:
        return [Letter(**json.loads(line)) for line in file if line.strip()]


def write_letters(path: Path, letters: Iterable[Letter]) -> None:
    """JSON lines sorted by reference number, written through a temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.name}.part")
    with part.open("w", encoding="utf-8", newline="\n") as file:
        for letter in sorted(letters, key=lambda x: x.id):
            file.write(json.dumps(asdict(letter)) + "\n")
    os.replace(part, path)


def letter_path(letter_id: str, splits: Mapping[str, str] | None) -> Path:
    """Where a letter's page lives: unsplit before the split, then in its split's folder."""
    if splits is None:
        return UNSPLIT / f"{letter_id}.html"
    folder = DEV_LETTERS if splits[letter_id] == "dev" else HELDOUT_LETTERS
    return folder / f"{letter_id}.html"


def _matches(path: Path, letter: Letter) -> bool:
    return path.is_file() and _digest(path.read_bytes()) == (letter.size, letter.sha256)


def _progress(i: int, n: int, letter_id: str) -> str:
    return f"[{i}/{n} {time.strftime('%H:%M:%S')}] {letter_id}"


def _summary(letters: Sequence[Letter], matching: int, start: float) -> None:
    years = Counter(x.year for x in letters)
    layouts = Counter(x.layout for x in letters)
    print(
        "letters per reference year: "
        + ", ".join(f"{year} {n}" for year, n in sorted(years.items()))
    )
    print(
        f"layouts: article {layouts['article']}, content-wall {layouts['content-wall']},"
        f" unreadable {layouts['']}"
    )
    print(
        f"{matching} letters match the manifest in"
        f" {(time.monotonic() - start) / 60:.0f} min"
    )


def _list(path: Path, get: Get) -> int:
    start = time.monotonic()
    known = {x.id: x for x in load_letters(path)} if path.exists() else {}
    captures, counts = read_index(index_pages(get))
    failed = 0
    for i, (letter_id, letter_captures) in enumerate(captures.items(), start=1):
        prefix = _progress(i, len(captures), letter_id)
        old = known.get(letter_id)
        if old is not None and old.layout:
            print(f"{prefix}: present ({old.size:,} bytes)", flush=True)
            continue
        try:
            letter = fetch_letter(letter_captures, UNSPLIT, get)
        except FetchError as err:
            failed += 1
            print(f"{prefix}: FAILED: {err}", flush=True)
            continue
        known[letter_id] = letter
        write_letters(path, known.values())
        outcome = "fetched" if letter.layout else "unreadable"
        print(f"{prefix}: {outcome} ({letter.size:,} bytes)", flush=True)
    print(
        "index: "
        + ", ".join(
            f"{reason} {counts[reason]:,}"
            for reason in (
                "kept",
                "other URL shapes",
                "outside the years",
                "not HTML",
                "not 200",
            )
        )
    )
    _summary(list(known.values()), len(known), start)
    return 1 if failed else 0


def _check(path: Path, get: Get) -> int:
    start = time.monotonic()
    letters = load_letters(path)
    failed = 0
    for i, letter in enumerate(letters, start=1):
        prefix = _progress(i, len(letters), letter.id)
        target = letter_path(letter.id, None)
        if _matches(target, letter):
            print(f"{prefix}: present ({letter.size:,} bytes)", flush=True)
            continue
        capture = Capture(letter.id, letter.capture, letter.original)
        try:
            response = get(capture.url)
        except FetchError as err:
            failed += 1
            print(f"{prefix}: FAILED: {err}", flush=True)
            continue
        if response.status != 200 or _digest(response.body) != (
            letter.size,
            letter.sha256,
        ):
            failed += 1
            print(
                f"{prefix}: FAILED: HTTP {response.status},"
                " not the bytes the manifest records",
                flush=True,
            )
            continue
        _keep(capture, response.body, letter.layout, target.parent)
        print(f"{prefix}: fetched ({letter.size:,} bytes)", flush=True)
    _summary(letters, len(letters) - failed, start)
    return 1 if failed else 0


def _skeletons(path: Path) -> int:
    counts: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for letter in load_letters(path):
        if letter.layout:
            continue
        html = html_of(letter_path(letter.id, None).read_bytes())
        counts[found := signature(html)] += 1
        examples.setdefault(found, skeleton(html))
    for found, n in counts.most_common():
        print(f"{found}: {n} pages; the first one's structure:")
        print(examples[found])
    print(f"{sum(counts.values())} unreadable pages")
    return 0


def main(argv: Sequence[str] | None = None, *, get: Get | None = None) -> int:
    # Windows encodes a piped stdout as cp1252: escape what it cannot show, such as a
    # class name in a page's structure, rather than stop.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.letters",
        description="List the regulator's letters the Internet Archive holds, fetch"
        " them, and check them against the manifest; never prints a letter's text.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--list",
        action="store_true",
        help="read the archive's index and fetch new letters",
    )
    mode.add_argument(
        "--skeletons",
        action="store_true",
        help="show the structure of the pages no capture could read",
    )
    parser.add_argument("--letters", type=Path, default=DEFAULT_LETTERS)
    parser.add_argument("--split", type=Path, default=SPLIT_FILE)
    args = parser.parse_args(argv)
    if (args.list or args.skeletons) and args.split.exists():
        print("the split exists, so the pool is frozen")
        return 2
    if args.skeletons:
        return _skeletons(args.letters)
    getter = get if get is not None else Paced(http_get, interval=ARCHIVE_INTERVAL)
    if args.list:
        return _list(args.letters, getter)
    if not args.letters.exists():
        print(
            f"no manifest at {args.letters}:"
            ' run "uv run python -m regulator_graded_rag.letters --list"'
        )
        return 1
    return _check(args.letters, getter)


if __name__ == "__main__":
    raise SystemExit(main())
