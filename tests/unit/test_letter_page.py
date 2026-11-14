# Author: Nicola Antonello
from datetime import date

from regulator_graded_rag.letter_page import LetterPage, read_page, signature, skeleton

# Invented pages shaped like the two layouts measured on 2026-11-14; no real letter.
ARTICLE = (
    '<html><body><main><article class="node node--type-interpretation-response node--view-mode-full">'
    '<h1 class="page__title node__title">Interpretation 99-0001</h1>'
    '<p><strong>Response Publish Date:</strong> <time class="datetime" datetime="2020-03-02T12:00:00Z">03/02/2020</time></p>'
    "<p><strong>Company Name:</strong> Example Shipping Co.</p>"
    "<p><strong>Individual Name:</strong> Pat Example</p>"
    "<p><strong>Location State:</strong> VA <strong>Country:</strong> US</p>"
    '<p class="mb-0"><strong>Response text:</strong></p>'
    "<p>Dear Pat Example:</p>"
    "<p>This responds to your letter.<br>Q1. Does the rule apply?</p>"
    "<p></p><p>A1. Yes. See &sect;&#8201;171.1.</p>"
    '<h2 class="mb-4">Regulation Sections</h2><p>171.1</p>'
    "</article></main></body></html>"
)
CONTENT_WALL = (
    '<html><body><div class="dot-regulations-content"><section id="content-wall"><h1 class="title">99-0002</h1>'
    "<table><tr><td><b>Response Publish Date:</b> 3/2/2020</td></tr>"
    "<tr><td><b>Company Name:</b> Example Shipping Co.</td></tr>"
    "<tr><td><b>Individual Name:</b> Pat Example</td></tr>"
    "<tr><td><b>Response text:</b><p>Dear Pat Example:</p><p>A1. No.</p></td></tr></table>"
    "<h2>Regulation Sections</h2></section></div></body></html>"
)


def test_article_layout_gives_fields_and_paragraphs() -> None:
    assert read_page(ARTICLE) == LetterPage(
        "article",
        date(2020, 3, 2),
        "Example Shipping Co.",
        "Pat Example",
        (
            "Dear Pat Example:",
            "This responds to your letter. Q1. Does the rule apply?",
            "A1. Yes. See § 171.1.",
        ),
    )


def test_content_wall_layout_gives_fields_and_paragraphs() -> None:
    assert read_page(CONTENT_WALL) == LetterPage(
        "content-wall",
        date(2020, 3, 2),
        "Example Shipping Co.",
        "Pat Example",
        ("Dear Pat Example:", "A1. No."),
    )


def test_content_wall_dates_may_use_hyphens() -> None:
    # The captures of 2020-2021 write the date as MM-DD-YYYY (measured on 2026-11-14).
    page = read_page(CONTENT_WALL.replace("3/2/2020", "04-17-2020"))
    assert page is not None and page.publish_date == date(2020, 4, 17)


def test_the_response_stops_at_the_next_heading() -> None:
    page = read_page(ARTICLE)
    assert page is not None and page.paragraphs[-1] == "A1. Yes. See § 171.1."


def test_unknown_layout_gives_no_page() -> None:
    assert (
        read_page("<html><body><main><p>Access denied</p></main></body></html>") is None
    )
    assert read_page(ARTICLE.replace("Response text:", "Summary:")) is None


def test_skeleton_shows_structure_and_no_text() -> None:
    lines = skeleton(ARTICLE)
    assert "article" in lines and "page__title" in lines
    assert "Pat" not in lines and "Example" not in lines and "rule" not in lines


def test_signature_names_the_layout() -> None:
    assert (signature(ARTICLE), signature(CONTENT_WALL)) == ("article", "content-wall")
    assert (
        signature("<html><body><p>Access denied</p></body></html>")
        == "unknown: no response text"
    )
