# Author: Nicola Antonello
from datetime import date
from pathlib import Path

import pytest

from regulator_graded_rag.ecfr import (
    Cache,
    PageMissing,
    characters,
    page_url,
    parse_units,
    unit_key,
)
from regulator_graded_rag.fetch import FetchError, Response

# Shaped like the renderer's pages measured on 2026-11-14, with invented rule text.
PAGE = (
    '<div class="editorial-note"><p>Unofficial.</p></div>'
    '<div class="section" id="173.9"><h4>§ 173.9 Transport vehicles.</h4>'
    '<div id="p-173.9(a)"><p class="indent-1">(a) Rule a.</p>'
    '<div id="p-173.9(a)(1)"><p class="indent-2">(1) Rule a1 is 1<span class="fraction">'
    '<span class="numerator">1</span>⁄<span class="denominator">2</span></span> inches.</p></div></div>'
    '<div id="p-173.9(b)"><p>(b) Rule b<sup>[<a class="footnote-reference">1</a>] </sup>; see §§ 173.1, 173.2.</p></div>'
    '<div class="table-wrapper"><table class="gpo_table"><caption>Table 1</caption><thead><tr><th>Code</th></tr></thead>'
    "<tbody><tr><td>(1)</td></tr><tr><td>IB1</td></tr></tbody></table></div>"
    '<div class="footnote"><p>1 A note.</p></div>'
    '<p class="citation">[Amdt. 173-1, 1 FR 1, Jan. 1, 2000]</p></div>'
    '<div class="appendix" id="Appendix-A-to-Subpart-C-of-Part-178"><h4>Appendix A</h4><p>Figures.</p></div>'
)
DAY = date(2025, 10, 1)


def test_a_unit_keeps_its_rule_text_only() -> None:
    unit = parse_units(PAGE)["173.9"]
    assert (
        characters(unit.text)
        == "(a)Rulea.(1)Rulea1is11/2inches.(b)Ruleb1;see173.1,173.2.IB1"
    )
    assert unit.footnotes == "1 A note."


def test_a_paragraph_holds_its_subparagraphs() -> None:
    paragraphs = parse_units(PAGE)["173.9"].paragraphs
    assert paragraphs["173.9(a)"].startswith("(a) Rule a. (1) Rule a1")
    assert "Rule a." not in paragraphs["173.9(a)(1)"]


def test_appendix_keys_match_the_passage_units() -> None:
    assert "178.subptC.appA" in parse_units(PAGE)
    assert unit_key("appendix", "Appendix-B-to-Part-172") == "172.appB"
    assert unit_key("appendix", "Appendixes-E-G-to-Part-173") is None


def test_page_urls() -> None:
    assert page_url(DAY, "173", "173.185") == (
        "https://www.ecfr.gov/api/renderer/v1/content/enhanced/2025-10-01/title-49?part=173&section=173.185"
    )


def test_a_cached_page_is_not_fetched_again(tmp_path: Path) -> None:
    calls: list[str] = []

    def get(url: str) -> Response:
        calls.append(url)
        return Response(200, "text/html", PAGE.encode())

    cache = Cache(tmp_path, get)
    assert cache.page(DAY, "173", "173.9") == cache.page(DAY, "173", "173.9")
    assert (
        len(calls) == 1 and (tmp_path / "2025-10-01" / "173" / "173.9.html").is_file()
    )


def test_a_paragraph_printed_twice_is_kept_once_unless_its_copies_differ() -> None:
    # The official §178.55 prints its paragraph (i) twice, word for word, and eCFR
    # repeats it with the same ids (measured on 2026-11-15).
    page = (
        '<div class="section" id="178.55"><h4>§ 178.55 Cylinders.</h4>'
        '<div id="p-178.55(i)"><p>(i) Same.</p></div><div id="p-178.55(i)"><p>(i) Same.</p></div>'
        '<div id="p-178.55(j)"><p>(j) One.</p></div><div id="p-178.55(j)"><p>(j) Two.</p></div></div>'
    )
    assert parse_units(page)["178.55"].paragraphs == {"178.55(i)": "(i) Same."}


def test_an_unexpected_page_is_refused() -> None:
    with pytest.raises(ValueError, match="173.9"):
        parse_units(PAGE + PAGE)


def test_the_renderers_redirect_to_its_canonical_address_is_followed(
    tmp_path: Path,
) -> None:
    # Measured on 2026-11-15: a part or section request answers 302 with the hierarchy.
    canonical = page_url(DAY, "173", "173.9").replace(
        "?part=", "?subtitle=B&chapter=I&subchapter=C&part="
    )
    answers = {
        page_url(DAY, "173", "173.9"): Response(
            302, "text/html", b"", location=canonical
        ),
        canonical: Response(200, "text/html", PAGE.encode()),
    }
    assert "173.9" in parse_units(
        Cache(tmp_path, answers.__getitem__).page(DAY, "173", "173.9")
    )


def test_a_redirect_elsewhere_is_refused(tmp_path: Path) -> None:
    cache = Cache(
        tmp_path, lambda url: Response(302, "", b"", location="https://example.com/x")
    )
    with pytest.raises(FetchError, match="redirected to https://example.com/x"):
        cache.page(DAY, "173")


def test_a_redirect_to_another_day_is_refused(tmp_path: Path) -> None:
    elsewhere = page_url(date(2024, 1, 1), "173")
    answers = {
        page_url(DAY, "173"): Response(302, "", b"", location=elsewhere),
        elsewhere: Response(200, "text/html", PAGE.encode()),
    }
    with pytest.raises(FetchError, match="redirected to"):
        Cache(tmp_path, answers.__getitem__).page(DAY, "173")
    assert list(tmp_path.rglob("*.html")) == []


def test_a_page_ecfr_does_not_hold_is_missing(tmp_path: Path) -> None:
    cache = Cache(tmp_path, lambda url: Response(404, "text/html", b"Not found"))
    with pytest.raises(PageMissing, match="173.999"):
        cache.page(DAY, "173", "173.999")
    assert list(tmp_path.rglob("*.html")) == []
