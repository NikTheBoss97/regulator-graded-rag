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


def test_article_paragraphs_may_be_divs() -> None:
    # 25 captures from 2026 hold the response in div elements (measured on 2026-11-15).
    second = "This responds to your letter.<br>Q1. Does the rule apply?"
    page = ARTICLE.replace("<p>Dear Pat Example:</p>", "<div>Dear Pat Example:</div>")
    read = read_page(page.replace(f"<p>{second}</p>", f"<div>{second}</div>"))
    assert read is not None and read.paragraphs == (
        "Dear Pat Example:",
        "This responds to your letter. Q1. Does the rule apply?",
        "A1. Yes. See § 171.1.",
    )


def test_a_div_that_wraps_paragraphs_is_not_one() -> None:
    label = '<p class="mb-0"><strong>Response text:</strong></p>'
    wrapped = ARTICLE.replace(label, f"{label}<div>").replace(
        '<h2 class="mb-4">', '</div><h2 class="mb-4">'
    )
    assert read_page(wrapped) == read_page(ARTICLE)


def before_the_sections(extra: str) -> str:
    """ARTICLE with extra response markup just before the h2 that ends the response."""
    return ARTICLE.replace('<h2 class="mb-4">', f'{extra}<h2 class="mb-4">')


def test_lists_tables_and_loose_text_are_read() -> None:
    # 89 letters hold part of the response in list items, table cells or text outside
    # any paragraph (measured on 2026-11-15).
    page = read_page(
        before_the_sections(
            "<ol><li>Question one?</li><li>Question two?</li></ol>Loose text."
            "<table><caption>Table 1</caption><tr><th>Item</th><td>Cell</td></tr></table>"
        )
    )
    assert page is not None and page.paragraphs[3:] == (
        "Question one?",
        "Question two?",
        "Loose text.",
        "Table 1",
        "Item",
        "Cell",
    )


def test_each_character_is_read_once() -> None:
    page = read_page(
        before_the_sections(
            "<ul><li>Intro <ul><li>Sub</li></ul> tail</li></ul>"
            "<p><span><div>Inside</div></span></p>"
        )
    )
    assert page is not None and page.paragraphs[3:] == (
        "Intro",
        "Sub",
        "tail",
        "Inside",
    )


def test_content_wall_text_outside_paragraphs_is_read() -> None:
    page = read_page(
        CONTENT_WALL.replace("<p>A1. No.</p>", "<p>A1. No.</p>Loose text.<br>More.")
    )
    assert page is not None and page.paragraphs == (
        "Dear Pat Example:",
        "A1. No.",
        "Loose text. More.",
    )


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
