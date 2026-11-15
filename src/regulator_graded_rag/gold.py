# Author: Nicola Antonello
"""Gold items, the questions a run is scored on, read and checked (ADR-0007, ADR-0012).

A gold file holds one JSON object per line, with exactly the fields the gold rules
require. An item that breaks a rule is refused with its file, line and field, so a hand
edit cannot slip a malformed label into a run. The gold-set version is the SHA-256 of the
file's bytes, so any change to any item changes it.
"""

import hashlib
import json
import re
from dataclasses import dataclass, fields
from datetime import date
from pathlib import Path
from typing import Any, NoReturn

TYPES = ("unanswerable", "table", "multi_passage", "lookup")
EDITION = "2025"
ITEM_ID = re.compile(r"\d{2}-\d{4}-Q\d+|U-\d+")
# The passage builder's unit keys, plus paragraph designators.
EVIDENCE = re.compile(
    r"\d{3}\.(?:\d+[a-z]?(?:-\d+)?|(?:subpt[A-Z]+\.)?app[A-Z])(?:\([0-9A-Za-z]+\))*"
)
SPLITS = ("dev", "heldout")

_LETTER_ITEM = re.compile(r"\d{2}-\d{4}-Q\d+")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ARCHIVE = "https://web.archive.org/"


@dataclass(frozen=True)
class Item:
    id: str
    question: str
    type: str
    answer: str
    evidence: tuple[str, ...]
    letter_date: str
    source: str
    split: str
    written_by: str
    verified: str
    edition: str

    @property
    def answerable(self) -> bool:
        return self.type != "unanswerable"

    @property
    def sections(self) -> frozenset[str]:
        """The units the evidence cites, a paragraph counting for its section."""
        if not self.answerable:
            return frozenset()
        return frozenset(label.split("(", 1)[0] for label in self.evidence)


_FIELDS = tuple(f.name for f in fields(Item))


def _is_iso_date(text: str) -> bool:
    if not _ISO_DATE.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _checked(record: dict[str, Any], where: str, seen: set[str]) -> Item:
    def refuse(field: str, why: str) -> NoReturn:
        raise ValueError(f"{where}: {field}: {why}")

    for key in record:
        if key not in _FIELDS:
            refuse(key, "not a gold field")
    for name in _FIELDS:
        if name not in record:
            refuse(name, "missing")
        value = record[name]
        if name == "evidence":
            if not isinstance(value, list) or not all(
                isinstance(v, str) for v in value
            ):
                refuse(name, "not a list of strings")
        elif not isinstance(value, str):
            refuse(name, "not a string")
    item_id = record["id"]
    if not ITEM_ID.fullmatch(item_id):
        refuse("id", f"{item_id!r} is neither NN-NNNN-Qn nor U-n")
    if item_id in seen:
        refuse("id", f"repeated: {item_id}")
    if record["type"] not in TYPES:
        refuse("type", f"{record['type']!r} is not one of {', '.join(TYPES)}")
    answerable = record["type"] != "unanswerable"
    if answerable and record["answer"] not in ("yes", "no"):
        refuse("answer", f"{record['answer']!r}: an answerable item's is yes or no")
    if not answerable and record["answer"] != "":
        refuse("answer", f"{record['answer']!r}: an unanswerable item has none")
    if not record["evidence"]:
        refuse("evidence", "empty")
    if answerable:
        for label in record["evidence"]:
            if not EVIDENCE.fullmatch(label):
                refuse("evidence", f"{label!r} is not a section or paragraph label")
    if _LETTER_ITEM.fullmatch(item_id):
        if not _is_iso_date(record["letter_date"]):
            refuse("letter_date", f"{record['letter_date']!r} is not an ISO date")
        if not record["source"].startswith(_ARCHIVE):
            refuse("source", f"a letter item's source starts with {_ARCHIVE}")
    else:
        for name in ("letter_date", "source"):
            if record[name]:
                refuse(name, "the owner's items have none")
    if record["split"] not in SPLITS:
        refuse("split", f"{record['split']!r} is not one of {', '.join(SPLITS)}")
    for name in ("question", "written_by", "verified"):
        if not record[name].strip():
            refuse(name, "empty")
    if record["edition"] != EDITION:
        refuse("edition", f"{record['edition']!r} is not {EDITION}")
    return Item(**(record | {"evidence": tuple(record["evidence"])}))


def load_items(path: Path) -> list[Item]:
    """The file's items, in order; the first one that breaks a rule is refused."""
    items: list[Item] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as file:
        for number, line in enumerate(file, start=1):
            if line.strip():
                where = f"{path}:{number}"
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as err:
                    raise ValueError(
                        f"{where}: json: {err.msg}, column {err.colno}"
                    ) from None
                if not isinstance(record, dict):
                    raise ValueError(f"{where}: json: not an object")
                item = _checked(record, where, seen)
                seen.add(item.id)
                items.append(item)
    return items


def gold_version(path: Path) -> str:
    """The SHA-256 of the file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
