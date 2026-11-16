# Author: Nicola Antonello
"""Draft gold items from a split's letters, for the owner's check (ADR-0007, ADR-0021).

Usage: python -m regulator_graded_rag.drafts --split {dev,heldout} [--heldout-by-owner]
[--out PATH], from the repository root.

Each letter of the split gives one draft per question whose answer starts with yes or no
and cites at least one section. A draft holds the question, scrubbed of the page's names,
emails and phone numbers and rewritten by the fixed rule; the verdict; the evidence
labels; and the type. The drift check then compares every label on the letter's date and
on the edition's day. A draft is kept when all are unchanged, or when it is an
unanswerable candidate, whose answer cites only rules outside Parts 171-180. Its flags
point the owner to what needs a look. The command prints counts, never a question.
Held-out drafts are made by the owner only (ADR-0014).
Exit code 0 when the drafts are written, 1 when an input is missing or wrong, and 2 for
a held-out run without the owner's flag.
"""

import argparse
import json
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path

from regulator_graded_rag.citations import cite, definitions, item_type, table_units
from regulator_graded_rag.drift import check, parse_citation
from regulator_graded_rag.ecfr import (
    KNOWN_DIFFERENCES,
    Cache,
    default_cache,
    edition_units,
)
from regulator_graded_rag.extract import (
    direct,
    letter_date,
    mentions_picture,
    pairs,
    verdict,
)
from regulator_graded_rag.index import read_passages
from regulator_graded_rag.letter_page import LetterPage, read_page
from regulator_graded_rag.letters import (
    DEFAULT_LETTERS,
    SPLIT_FILE,
    Letter,
    letter_path,
    load_letters,
)
from regulator_graded_rag.manifest import DEFAULT_MANIFEST, load_manifest
from regulator_graded_rag.passages import DEFAULT_OUT
from regulator_graded_rag.scrub import scrub
from regulator_graded_rag.split import load_split

DRAFTS = {
    "dev": Path("eval/dev/drafts.jsonl"),
    "heldout": Path("eval/heldout/drafts.jsonl"),
}
FLAGS = (
    "picture",
    "not rewritten",
    "known difference",
    "date from the publish field",
    "dates differ",
    "outside the corpus",
    "scrubbed",
    "unnumbered",
    "answer continues",
)
ARCHIVE = "https://web.archive.org/web"


@dataclass(frozen=True)
class Draft:
    id: str
    letter: str
    number: int
    numbered: bool
    question: str
    rewritten: bool
    answer: str
    evidence: tuple[str, ...]
    outside: tuple[str, ...]
    type: str
    letter_date: str
    date_source: str
    source: str
    split: str
    drift: dict[str, str]
    kept: bool
    flags: tuple[str, ...]


def draft_letter(
    letter: Letter,
    page: LetterPage,
    split: str,
    definitions: Mapping[str, str],
    tables: AbstractSet[str],
    units: Sequence[str] = (),
) -> list[Draft]:
    """The letter's drafts before the drift check; none when the letter has no date.
    units, the corpus's units in order, lets a range of sections give every member."""
    day, date_source = letter_date(page)
    if day is None:
        return []
    dated: set[str] = set()
    if date_source == "published":
        dated.add("date from the publish field")
    elif page.publish_date is not None and page.publish_date != day:
        dated.add("dates differ")
    drafts: list[Draft] = []
    for pair in pairs(page.paragraphs):
        said = verdict(pair.answer)
        cited = cite(pair.answer, definitions, units)
        if said is None or not (cited.corpus or cited.outside):
            continue
        first = pair.answer.split("\n", 1)[0]
        kind = item_type(cited, tables)
        scrubbed = scrub(pair.question, page.company, page.individual)
        question = direct(scrubbed.text)
        flags = set(dated)
        if question is None:
            flags.add("not rewritten")
        if mentions_picture(pair.question, pair.answer):
            flags.add("picture")
        if any(label.split("(")[0] in KNOWN_DIFFERENCES for label in cited.corpus):
            flags.add("known difference")
        if cited.outside:
            flags.add("outside the corpus")
        if scrubbed.removed:
            flags.add("scrubbed")
        if not pair.numbered:
            flags.add("unnumbered")
        # The answer's later paragraphs add citations: the owner confirms they are its
        # own, not the next question's context (owner, 2026-11-16).
        if pair.continues and cite(first, definitions, units) != cited:
            flags.add("answer continues")
        unanswerable = kind == "unanswerable"
        outside = ", ".join(cited.outside)
        drafts.append(
            Draft(
                id=f"{letter.id}-Q{pair.number}",
                letter=letter.id,
                number=pair.number,
                numbered=pair.numbered,
                question=scrubbed.text if question is None else question,
                rewritten=question is not None,
                answer="" if unanswerable else said,
                evidence=(
                    (f"PHMSA's answer cites only {outside}, outside Parts 171-180",)
                    if unanswerable
                    else cited.corpus
                ),
                outside=cited.outside,
                type=kind,
                letter_date=day.isoformat(),
                date_source=date_source,
                source=f"{ARCHIVE}/{letter.capture}/{letter.original}",
                split=split,
                drift={},
                kept=unanswerable,
                flags=tuple(flag for flag in FLAGS if flag in flags),
            )
        )
    return drafts


def with_drift(draft: Draft, outcomes: Mapping[str, str]) -> Draft:
    """The draft with each label's outcome, kept only when every one is unchanged."""
    drift = {label: outcomes[label] for label in draft.evidence}
    kept = bool(drift) and all(outcome == "unchanged" for outcome in drift.values())
    return replace(draft, drift=drift, kept=kept)


def drift_draft(draft: Draft, cache: Cache) -> Draft:
    """The draft after the drift check of its labels on its letter's date; an
    unanswerable candidate has no label to check and stays as it is."""
    if draft.type == "unanswerable":
        return draft
    day = date.fromisoformat(draft.letter_date)
    outcomes = check(map(parse_citation, draft.evidence), day, cache)
    return with_drift(draft, {c.label: o for c, o in outcomes.items()})


def write_drafts(path: Path, drafts: Iterable[Draft]) -> None:
    """One JSON object per draft and line, sorted keys, LF. An unkept draft is written
    without its question, since the owner checks only kept ones and no unchecked letter
    text may reach git (owner, 2026-11-16)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = "".join(
        json.dumps(
            asdict(draft if draft.kept else replace(draft, question="")),
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
        for draft in drafts
    )
    path.write_text(lines, encoding="utf-8", newline="\n")


def load_drafts(path: Path) -> list[Draft]:
    drafts: list[Draft] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            for name in ("evidence", "outside", "flags"):
                record[name] = tuple(record[name])
            drafts.append(Draft(**record))
    return drafts


def _clock(start: float) -> str:
    elapsed = int(time.monotonic() - start)
    return f"{elapsed // 3600:02}:{elapsed // 60 % 60:02}:{elapsed % 60:02}"


def _report(count: Counter[str], drafts: Sequence[Draft]) -> None:
    kept = [draft for draft in drafts if draft.kept]
    outcomes = [set(draft.drift.values()) for draft in drafts]
    print(
        f"letters: {count['read']} read, {count['unreadable']} unreadable,"
        f" {count['undated']} undated; pairs: {count['pairs']}"
    )
    print(
        f"candidates: {len(drafts)}; kept: {len(kept)}; changed:"
        f" {sum('changed' in o for o in outcomes)}; missing only:"
        f" {sum('missing' in o and 'changed' not in o for o in outcomes)}"
    )
    types = Counter(draft.type for draft in kept)
    print("kept by type: " + ", ".join(f"{t} {n}" for t, n in sorted(types.items())))
    flags = Counter(flag for draft in kept for flag in draft.flags)
    print("kept by flag: " + ", ".join(f"{f} {flags[f]}" for f in FLAGS if flags[f]))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.drafts",
        description="Draft gold items from a split's letters, for the owner's check.",
    )
    parser.add_argument("--split", required=True, choices=sorted(DRAFTS))
    parser.add_argument(
        "--heldout-by-owner",
        action="store_true",
        help="the owner drafts the held-out letters (ADR-0014)",
    )
    parser.add_argument(
        "--out", type=Path, help="the drafts file (default: the split's)"
    )
    args = parser.parse_args(argv)
    if args.split == "heldout" and not args.heldout_by_owner:
        print("held-out drafts are made by the owner only (ADR-0014)")
        return 2
    try:
        splits = load_split(SPLIT_FILE)
        letters = {letter.id: letter for letter in load_letters(DEFAULT_LETTERS)}
        records = read_passages(DEFAULT_OUT, load_manifest(DEFAULT_MANIFEST))
    except FileNotFoundError as err:
        print(f"{err.filename} is missing")
        return 1
    except ValueError as err:
        print(err)
        return 1
    tables = table_units(records)
    units = list(dict.fromkeys(record["id"].rsplit(":", 1)[0] for record in records))
    cache = default_cache()
    terms = definitions(edition_units(cache))
    chosen = sorted(name for name, split in splits.items() if split == args.split)
    count: Counter[str] = Counter()
    drafts: list[Draft] = []
    start = time.monotonic()
    for n, letter_id in enumerate(chosen, start=1):
        print(f"[{n}/{len(chosen)} {_clock(start)}] {letter_id}", flush=True)
        path = letter_path(letter_id, splits)
        page = read_page(path.read_text(encoding="utf-8")) if path.is_file() else None
        if page is None:
            count["unreadable"] += 1
            continue
        count["read"] += 1
        count["pairs"] += len(pairs(page.paragraphs))
        if letter_date(page)[0] is None:
            count["undated"] += 1
        found = draft_letter(letters[letter_id], page, args.split, terms, tables, units)
        drafts += [drift_draft(draft, cache) for draft in found]
    write_drafts(args.out or DRAFTS[args.split], drafts)
    _report(count, drafts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
