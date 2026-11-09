# Author: Nicola Antonello
import hashlib
from http.client import IncompleteRead
from pathlib import Path

import pytest

from regulator_graded_rag import __version__
from regulator_graded_rag.fetch import USER_AGENT, FetchError, Response, fetch_file
from regulator_graded_rag.manifest import CorpusFile

XML = b'<?xml version="1.0"?>\n<CFRGRANULE/>\n'
FILE = CorpusFile(
    "x.xml",
    "https://www.govinfo.gov/content/pkg/x/xml/x.xml",
    len(XML),
    hashlib.sha256(XML).hexdigest(),
    "public domain (17 U.S.C. 105)",
)


def ok(url: str) -> Response:
    return Response(200, "application/xml", XML)


def no_wait(seconds: float) -> None:
    raise AssertionError("no retry expected")


def test_fetch_writes_a_verified_file(tmp_path: Path) -> None:
    assert fetch_file(FILE, tmp_path, get=ok, sleep=no_wait) == "fetched"
    assert [p.name for p in tmp_path.iterdir()] == ["x.xml"]
    assert (tmp_path / "x.xml").read_bytes() == XML


def test_redirect_to_the_error_page_is_refused(tmp_path: Path) -> None:
    def redirect(url: str) -> Response:
        return Response(302, "", b"", location="https://www.govinfo.gov/error")

    with pytest.raises(FetchError, match="redirected to https://www.govinfo.gov/error"):
        fetch_file(FILE, tmp_path, get=redirect, sleep=no_wait)
    assert list(tmp_path.iterdir()) == []


def test_html_answered_with_200_is_refused(tmp_path: Path) -> None:
    def error_page(url: str) -> Response:
        return Response(200, "text/html;charset=UTF-8", b"<!DOCTYPE html><html></html>")

    with pytest.raises(FetchError, match="expected application/xml, got text/html"):
        fetch_file(FILE, tmp_path, get=error_page, sleep=no_wait)
    assert list(tmp_path.iterdir()) == []


def test_bytes_that_do_not_match_the_manifest_are_refused(tmp_path: Path) -> None:
    def altered(url: str) -> Response:
        return Response(200, "application/xml", XML.replace(b"GRANULE", b"GRANULX"))

    with pytest.raises(FetchError, match="SHA-256"):
        fetch_file(FILE, tmp_path, get=altered, sleep=no_wait)
    assert list(tmp_path.iterdir()) == []


def test_a_matching_local_copy_is_not_fetched_again(tmp_path: Path) -> None:
    (tmp_path / "x.xml").write_bytes(XML)

    def no_request(url: str) -> Response:
        raise AssertionError("no request expected")

    assert fetch_file(FILE, tmp_path, get=no_request, sleep=no_wait) == "present"


def test_local_copy_with_wrong_checksum_is_fetched_again(tmp_path: Path) -> None:
    (tmp_path / "x.xml").write_bytes(XML[:10])
    assert fetch_file(FILE, tmp_path, get=ok, sleep=no_wait) == "fetched"
    assert (tmp_path / "x.xml").read_bytes() == XML


def test_server_errors_are_retried_after_a_pause(tmp_path: Path) -> None:
    answers = iter(
        [Response(503, "text/html", b""), Response(200, "application/xml", XML)]
    )
    waits: list[float] = []
    fetched = fetch_file(
        FILE, tmp_path, get=lambda url: next(answers), sleep=waits.append
    )
    assert fetched == "fetched"
    assert waits == [2.0]


def test_network_errors_are_retried_then_reported(tmp_path: Path) -> None:
    waits: list[float] = []

    def down(url: str) -> Response:
        raise OSError("connection reset")

    with pytest.raises(FetchError, match="after 3 attempts"):
        fetch_file(FILE, tmp_path, get=down, sleep=waits.append)
    assert waits == [2.0, 4.0]


def test_a_download_cut_off_mid_body_is_retried(tmp_path: Path) -> None:
    # A connection closed early raises IncompleteRead, which is not an OSError.
    answers: list[Response | Exception] = [IncompleteRead(b"", 10), ok("")]
    waits: list[float] = []

    def cut_off_once(url: str) -> Response:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    fetched = fetch_file(FILE, tmp_path, get=cut_off_once, sleep=waits.append)
    assert (fetched, waits) == ("fetched", [2.0])


def test_requests_name_the_project_and_no_person() -> None:
    assert USER_AGENT == f"regulator-graded-rag/{__version__}"
