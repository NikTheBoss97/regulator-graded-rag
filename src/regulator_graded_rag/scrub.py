# Author: Nicola Antonello
"""Remove the personal data a script can recognise from a question (ADR-0007).

The letter page names the requester's company and the person who wrote; those names,
emails and North American phone numbers are replaced by a placeholder in the question
text before any draft is written. The owner's check, and for the drafts code accepts the owner's read (ADR-0022), is the
backstop for the rest.
"""

import re
from dataclasses import dataclass

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(
    r"(?<![\d.])(?:\+?1[-.\s]?)?(?:\(\d{3}\)\s?|\d{3}[-.\s])\d{3}[-.\s]\d{4}"
    r"(?:\s*(?:x|ext\.?|extension)\s*\d{1,6})?(?!\d)",
    re.IGNORECASE,
)
_TITLE = r"(?:(?:Mr|Ms|Mrs|Dr)\.?\s+)?"


@dataclass(frozen=True)
class Scrubbed:
    text: str
    removed: tuple[str, ...]


def scrub(text: str, company: str, individual: str) -> Scrubbed:
    """The text with the page's company and person, emails and phone numbers replaced,
    and the sorted kinds that were."""
    removed: set[str] = set()

    def replace(pattern: str | re.Pattern[str], placeholder: str, kind: str) -> None:
        nonlocal text
        text, count = re.subn(pattern, placeholder, text)
        if count:
            removed.add(kind)

    replace(_EMAIL, "[email]", "email")
    replace(_PHONE, "[phone]", "phone")
    # Names are bounded by non-word characters, not \b, so "Example Freight, Inc."
    # matches although it ends with a period.
    if company.strip():
        name = r"\s+".join(re.escape(word) for word in company.split())
        pattern = re.compile(rf"(?<!\w){name}(?!\w)", re.IGNORECASE)
        replace(pattern, "[company]", "company")
    words = [word for word in individual.split() if len(word.strip(".,")) >= 3]
    if words:
        full = r"\s+".join(re.escape(word) for word in individual.split())
        replace(rf"(?<!\w){_TITLE}{full}(?!\w)", "[name]", "name")
        for word in words:
            part = re.escape(word.strip(".,"))
            replace(rf"(?<!\w){_TITLE}{part}(?!\w)", "[name]", "name")
    return Scrubbed(text, tuple(sorted(removed)))
