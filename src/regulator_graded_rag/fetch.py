# Author: Nicola Antonello
"""Download the corpus files the manifest names, keeping each only when its bytes match.

Usage: python -m regulator_graded_rag.fetch [--manifest PATH] [--dest DIR], from the
repository root. GovInfo answers a missing file with a redirect to its error page, which
answers 200 with HTML, so redirects are refused and only application/xml is accepted. A
file is written under a temporary name and moved into place only after its size and
SHA-256 match the manifest, so an interrupted download never looks complete.
Exit code 0 when every file matches the manifest, 1 when one cannot be fetched.
"""

import argparse
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from http.client import HTTPException, HTTPMessage
from pathlib import Path
from typing import IO, Literal

from regulator_graded_rag import __version__
from regulator_graded_rag.manifest import (
    DEFAULT_MANIFEST,
    DEFAULT_RAW,
    CorpusFile,
    check_bytes,
    load_manifest,
)

# The project, never a person: requests carry no email or other personal data.
USER_AGENT = f"regulator-graded-rag/{__version__}"
TIMEOUT_SECONDS = 60
# Statuses that usually pass on their own: rate limiting and the gateway family.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class Response:
    status: int
    content_type: str
    body: bytes
    location: str | None = None


Get = Callable[[str], Response]


class FetchError(Exception):
    """A file could not be fetched with the bytes its manifest entry names."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Returning None makes urllib raise HTTPError for the 3xx instead of following it.
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def http_get(url: str) -> Response:
    """One GET that follows no redirect; any HTTP status comes back as a Response.

    Network errors propagate: OSError, or an HTTPException such as IncompleteRead when
    the connection closes before the whole body arrives.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with _OPENER.open(request, timeout=TIMEOUT_SECONDS) as answer:
            return Response(
                answer.status, answer.headers.get("Content-Type", ""), answer.read()
            )
    except urllib.error.HTTPError as err:
        return Response(
            err.code,
            err.headers.get("Content-Type", ""),
            err.read(),
            err.headers.get("Location"),
        )


def _the_file(entry: CorpusFile, response: Response) -> bytes:
    """The body when it is the entry's file; otherwise FetchError says what came."""
    if 300 <= response.status < 400:
        raise FetchError(
            f"{entry.name}: GovInfo redirected to {response.location},"
            " so the file is missing or its URL changed"
        )
    if response.status != 200:
        raise FetchError(f"{entry.name}: HTTP {response.status}")
    media_type = response.content_type.split(";", 1)[0].strip().lower()
    if media_type != "application/xml":
        raise FetchError(
            f"{entry.name}: expected application/xml, got {media_type}:"
            " probably GovInfo's error page"
        )
    if problem := check_bytes(entry, response.body):
        raise FetchError(f"{entry.name}: {problem}")
    return response.body


def fetch_file(
    entry: CorpusFile,
    dest: Path,
    *,
    get: Get = http_get,
    sleep: Callable[[float], None] = time.sleep,
    attempts: int = 3,
) -> Literal["present", "fetched"]:
    """Make dest/name hold the entry's bytes, downloading them unless a copy matches.

    Network errors (OSError, or an HTTPException such as a body cut short) and
    RETRY_STATUSES are retried after 2 seconds, then 4; any other answer that is not
    the file raises FetchError at once.
    """
    target = dest / entry.name
    if target.is_file() and check_bytes(entry, target.read_bytes()) is None:
        return "present"
    last = ""
    for attempt in range(attempts):
        if attempt:
            sleep(2.0 * 2 ** (attempt - 1))
        try:
            response = get(entry.url)
        except (OSError, HTTPException) as err:
            last = f"{type(err).__name__}: {err}"
            continue
        if response.status in RETRY_STATUSES:
            last = f"HTTP {response.status}"
            continue
        data = _the_file(entry, response)
        dest.mkdir(parents=True, exist_ok=True)
        part = dest / f"{entry.name}.part"
        part.write_bytes(data)
        os.replace(part, target)
        return "fetched"
    raise FetchError(f"{entry.name}: failed after {attempts} attempts: {last}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.fetch",
        description="Download the corpus files the manifest names, keeping each only"
        " when its size and SHA-256 match.",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dest", type=Path, default=DEFAULT_RAW)
    args = parser.parse_args(argv)
    manifest = load_manifest(args.manifest)
    start = time.monotonic()
    total = len(manifest.files)
    for i, entry in enumerate(manifest.files, start=1):
        prefix = f"[{i}/{total} {time.strftime('%H:%M:%S')}] {entry.name}"
        try:
            outcome = fetch_file(entry, args.dest)
        except FetchError as err:
            print(f"{prefix}: FAILED: {err}", flush=True)
            return 1
        print(f"{prefix}: {outcome} ({entry.size:,} bytes)", flush=True)
    print(f"{total} files match the manifest in {time.monotonic() - start:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
