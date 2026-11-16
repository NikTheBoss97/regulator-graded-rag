# Author: Nicola Antonello
from regulator_graded_rag.scrub import Scrubbed, scrub


def test_the_pages_names_emails_and_phone_numbers_are_removed() -> None:
    text = (
        "Jane Roe of Example Freight LLC asks whether Ms. Roe may call 555-123-4567 "
        "or write to jane.roe@example.com."
    )
    assert scrub(
        text, company="Example Freight LLC", individual="Jane Roe"
    ) == Scrubbed(
        "[name] of [company] asks whether [name] may call [phone] or write to [email].",
        ("company", "email", "name", "phone"),
    )


def test_text_without_personal_data_is_unchanged() -> None:
    text = "Is it the case that the marking complies with § 172.301(a)?"
    assert scrub(text, company="", individual="") == Scrubbed(text, ())


def test_section_numbers_and_dates_are_not_phone_numbers() -> None:
    text = "Under § 173.185(b)(5), as of 01-01-2020, UN3480 cells of 100 Wh ..."
    assert scrub(text, company="", individual="").text == text


def test_a_company_name_ending_with_a_period_is_removed() -> None:
    # Review: 71 of the dev candidates come from letters whose company ends in ".".
    got = scrub(
        "Example Freight, Inc. asks whether it may ship.",
        company="Example Freight, Inc.",
        individual="",
    )
    assert got == Scrubbed("[company] asks whether it may ship.", ("company",))
