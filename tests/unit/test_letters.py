# Author: Nicola Antonello
import hashlib
import io
import json
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest

from regulator_graded_rag import letters
from regulator_graded_rag.fetch import FetchError, Response
from regulator_graded_rag.letters import (
    Capture,
    Letter,
    fetch_letter,
    index_pages,
    letter_year,
    load_letters,
    main,
    read_index,
    write_letters,
)
from tests.unit.test_letter_page import ARTICLE

HEADER = ["original", "timestamp", "mimetype", "statuscode"]
URL = "https://www.phmsa.dot.gov/regulations/title49/interp/{}"


def test_index_keeps_letter_pages_from_2017_on() -> None:
    page = [
        HEADER,
        [URL.format("17-0001"), "20190101000000", "text/html", "200"],
        [URL.format("17-0001"), "20260101000000", "text/html", "200"],
        [URL.format("16-0099"), "20190101000000", "text/html", "200"],
        [URL.format("17-0001") + "?page=1", "20190101000000", "text/html", "200"],
        [
            "https://www7.phmsa.dot.gov/regulations/title49/interp/26-0001",
            "20260301000000",
            "text/html",
            "200",
        ],
        [URL.format(""), "20190101000000", "text/html", "200"],
    ]
    captures, counts = read_index([page])
    assert sorted(captures) == ["17-0001", "26-0001"]
    assert [c.timestamp for c in captures["17-0001"]] == [
        "20190101000000",
        "20260101000000",
    ]
    assert captures["26-0001"][0].original.startswith("https://www7.")
    assert counts == Counter({"kept": 3, "outside the years": 1, "other URL shapes": 2})


def test_reference_numbers_of_the_1990s_are_read_as_the_1990s() -> None:
    ids = ("96-0001", "99-0328", "00-0001", "17-0001", "26-0103")
    assert [letter_year(x) for x in ids] == [1996, 1999, 2000, 2017, 2026]
    row = [URL.format("99-0328"), "20190101000000", "text/html", "200"]
    assert read_index([[HEADER, row]]) == ({}, Counter({"outside the years": 1}))


def test_resume_keys_are_followed() -> None:
    asked: list[str] = []
    pages = iter(
        [
            json.dumps(
                [
                    HEADER,
                    [URL.format("17-0001"), "20190101000000", "text/html", "200"],
                    [],
                    ["KEY1"],
                ]
            ),
            json.dumps(
                [HEADER, [URL.format("17-0002"), "20190101000000", "text/html", "200"]]
            ),
        ]
    )

    def get(url: str) -> Response:
        asked.append(url)
        return Response(200, "application/json", next(pages).encode())

    assert sum(len(p) for p in index_pages(get)) == 4
    assert "resumeKey=KEY1" in asked[1]


def capture(stamp: str) -> Capture:
    return Capture("17-0001", stamp, URL.format("17-0001"))


def test_the_newest_readable_capture_is_kept(tmp_path: Path) -> None:
    letter = fetch_letter(
        [capture("20190101000000"), capture("20260101000000")],
        tmp_path,
        lambda url: Response(200, "text/html", ARTICLE.encode()),
    )
    assert (letter.capture, letter.layout, letter.year) == (
        "20260101000000",
        "article",
        2017,
    )
    assert (tmp_path / "17-0001.html").read_bytes() == ARTICLE.encode()
    assert letter.sha256 == hashlib.sha256(ARTICLE.encode()).hexdigest()


def test_an_unreadable_capture_falls_back_to_an_older_one(tmp_path: Path) -> None:
    pages = {
        "2026": b"<html><body>Access denied</body></html>",
        "2019": ARTICLE.encode(),
    }
    letter = fetch_letter(
        [capture("20190101000000"), capture("20260101000000")],
        tmp_path,
        lambda url: Response(200, "text/html", pages[url.split("/web/")[1][:4]]),
    )
    assert (letter.capture, letter.layout) == ("20190101000000", "article")


def test_a_letter_no_capture_can_read_is_kept_and_marked(tmp_path: Path) -> None:
    letter = fetch_letter(
        [capture("20260101000000")],
        tmp_path,
        lambda url: Response(
            200, "text/html", b"<html><body>Access denied</body></html>"
        ),
    )
    assert letter.layout == ""


def test_redirects_and_other_media_types_are_skipped(tmp_path: Path) -> None:
    answers = iter(
        [
            Response(302, "", b"", location="https://web.archive.org/web/2/x"),
            Response(200, "application/pdf", b"%PDF"),
        ]
    )
    with pytest.raises(FetchError, match="no capture gave a page"):
        fetch_letter(
            [capture("20190101000000"), capture("20260101000000")],
            tmp_path,
            lambda url: next(answers),
        )
    assert list(tmp_path.iterdir()) == []


def test_the_manifest_is_sorted_json_lines_with_lf(tmp_path: Path) -> None:
    b = Letter(
        "18-0002", 2018, "20260101000000", URL.format("18-0002"), "article", 3, "b" * 64
    )
    a = Letter(
        "17-0001", 2017, "20260101000000", URL.format("17-0001"), "", 4, "a" * 64
    )
    write_letters(tmp_path / "letters.jsonl", [b, a])
    data = (tmp_path / "letters.jsonl").read_bytes()
    assert b"\r" not in data and data.index(b"17-0001") < data.index(b"18-0002")
    assert load_letters(tmp_path / "letters.jsonl") == [a, b]


def test_skeletons_print_on_a_cp1252_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(letters, "UNSPLIT", tmp_path)
    page = '<html><body><div class="☃"><p>Access denied</p></div></body></html>'
    data = page.encode()
    (tmp_path / "17-0001.html").write_bytes(data)
    unreadable = Letter(
        "17-0001",
        2017,
        "20260101000000",
        URL.format("17-0001"),
        "",
        len(data),
        hashlib.sha256(data).hexdigest(),
    )
    write_letters(tmp_path / "letters.jsonl", [unreadable])
    console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)
    args = ["--skeletons", "--letters", str(tmp_path / "letters.jsonl")]
    assert main([*args, "--split", str(tmp_path / "split.jsonl")]) == 0
    console.flush()
    assert b"div.\\u2603" in console.buffer.getvalue()


def no_request(url: str) -> Response:
    raise AssertionError("no request expected")


def check(tmp_path: Path, get: Callable[[str], Response], *flags: str) -> int:
    """Run the command on tmp_path's manifest and split file, with the letters there."""
    args = ["--letters", str(tmp_path / "letters.jsonl")]
    return main([*flags, *args, "--split", str(tmp_path / "split.jsonl")], get=get)


@pytest.fixture
def one_letter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> bytes:
    """A manifest of one readable letter, whose file belongs in tmp_path/unsplit."""
    monkeypatch.setattr(letters, "UNSPLIT", tmp_path / "unsplit")
    data = ARTICLE.encode()
    letter = Letter(
        "17-0001",
        2017,
        "20260101000000",
        URL.format("17-0001"),
        "article",
        len(data),
        hashlib.sha256(data).hexdigest(),
    )
    write_letters(tmp_path / "letters.jsonl", [letter])
    return data


def test_the_checksum_mode_finds_a_present_letter_without_a_request(
    tmp_path: Path, one_letter: bytes
) -> None:
    (tmp_path / "unsplit").mkdir()
    (tmp_path / "unsplit" / "17-0001.html").write_bytes(one_letter)
    assert check(tmp_path, no_request) == 0


def test_the_checksum_mode_restores_a_missing_letter_from_its_capture(
    tmp_path: Path, one_letter: bytes
) -> None:
    asked: list[str] = []

    def get(url: str) -> Response:
        asked.append(url)
        return Response(200, "text/html", one_letter)

    assert check(tmp_path, get) == 0
    assert asked == [
        f"https://web.archive.org/web/20260101000000id_/{URL.format('17-0001')}"
    ]
    assert (tmp_path / "unsplit" / "17-0001.html").read_bytes() == one_letter


def test_the_checksum_mode_never_overwrites_with_other_bytes(
    tmp_path: Path, one_letter: bytes
) -> None:
    (tmp_path / "unsplit").mkdir()
    (tmp_path / "unsplit" / "17-0001.html").write_bytes(b"changed")
    assert check(tmp_path, lambda url: Response(200, "text/html", b"other")) == 1
    assert (tmp_path / "unsplit" / "17-0001.html").read_bytes() == b"changed"


def test_the_checksum_mode_needs_a_manifest(tmp_path: Path) -> None:
    assert check(tmp_path, no_request) == 1


def test_skeletons_are_refused_once_the_split_exists(tmp_path: Path) -> None:
    (tmp_path / "split.jsonl").write_text("{}\n", encoding="utf-8")
    assert check(tmp_path, no_request, "--skeletons") == 2


def test_listing_is_refused_once_the_split_exists(tmp_path: Path) -> None:
    (tmp_path / "split.jsonl").write_text("{}\n", encoding="utf-8")

    def no_request(url: str) -> Response:
        raise AssertionError("no request expected")

    args = [
        "--list",
        "--letters",
        str(tmp_path / "letters.jsonl"),
        "--split",
        str(tmp_path / "split.jsonl"),
    ]
    assert main(args, get=no_request) == 2


def test_a_stopped_listing_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(letters, "UNSPLIT", tmp_path / "unsplit")
    index = json.dumps(
        [HEADER]
        + [
            [URL.format(f"17-000{i}"), "20260101000000", "text/html", "200"]
            for i in (1, 2, 3)
        ]
    )
    pages: list[str] = []

    def get(url: str) -> Response:
        if "cdx/search" in url:
            return Response(200, "application/json", index.encode())
        pages.append(url)
        if fail_at and len(pages) == fail_at:
            raise FetchError("connection lost")
        return Response(200, "text/html", ARTICLE.encode())

    args = [
        "--list",
        "--letters",
        str(tmp_path / "letters.jsonl"),
        "--split",
        str(tmp_path / "split.jsonl"),
    ]
    fail_at = 3
    assert main(args, get=get) == 1
    assert [x.id for x in load_letters(tmp_path / "letters.jsonl")] == [
        "17-0001",
        "17-0002",
    ]
    pages.clear()
    fail_at = 0
    assert main(args, get=get) == 0
    assert len(pages) == 1 and len(load_letters(tmp_path / "letters.jsonl")) == 3
