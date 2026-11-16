# Author: Nicola Antonello
"""The owner's unanswerable questions, split by the letters' seed (ADR-0007, ADR-0018).

Usage: python -m regulator_graded_rag.unanswerable --heldout-by-owner, from the
repository root.

The owner writes every unanswerable question before seeing any draft, in
eval/heldout/unanswerable-all.jsonl: one {"id", "question", "searched"} object per line,
where searched says what the owner looked for in the corpus. The seed that split the
letters sends 40% of the questions, those with the lowest draw keys, to held-out, and
the rest to dev. Each becomes a gold item written by the owner, with what was searched
as its evidence. Like the letters, the questions are split once: the command refuses to
run when either split's file exists. The file holds future held-out items, so only the
owner runs this command, and it prints counts only.
Exit code 0 when both files are written, 1 when an input is missing or wrong, and 2
without the owner's flag.
"""

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

from regulator_graded_rag.gold import EDITION, Item, validate, write_items
from regulator_graded_rag.review_page import UNANSWERABLE
from regulator_graded_rag.split import SEED, draw_key, heldout_count

ALL = Path("eval/heldout/unanswerable-all.jsonl")
_KEYS = ("id", "question", "searched")


def complete(record: Mapping[str, str], split: str, verified: str) -> Item:
    """The owner's question as a gold item: unanswerable, with what was searched as its
    evidence. A record with other keys, or an empty one, is refused by its ID."""
    name = str(record.get("id", "an unnamed question"))
    if sorted(record) != sorted(_KEYS):
        raise ValueError(
            f"{name}: keys: {', '.join(sorted(record))}, where the owner's questions"
            f" have {', '.join(_KEYS)}"
        )
    searched = record["searched"]
    if not isinstance(searched, str) or not searched.strip():
        raise ValueError(f"{name}: searched: empty or not a string")
    return validate(
        {
            "id": record["id"],
            "question": record["question"],
            "type": "unanswerable",
            "answer": "",
            "evidence": [searched],
            "letter_date": "",
            "source": "",
            "split": split,
            "written_by": "owner",
            "verified": verified,
            "edition": EDITION,
        },
        name,
    )


def split_unanswerable(ids: Sequence[str], seed: str = SEED) -> dict[str, str]:
    """Each question's split: the heldout_count(len(ids)) IDs with the lowest draw keys
    go to held-out and the rest to dev, whatever order the IDs come in."""
    repeated = sorted(name for name, n in Counter(ids).items() if n > 1)
    if repeated:
        raise ValueError(f"repeated: {', '.join(repeated)}")
    ranked = sorted(ids, key=lambda name: draw_key(seed, name))
    held = set(ranked[: heldout_count(len(ids))])
    return {name: "heldout" if name in held else "dev" for name in ids}


def split_questions(
    source: Path, outputs: Mapping[str, Path], verified: str
) -> dict[str, int]:
    """The owner's questions in source, split by the seed into outputs, one gold file
    per split, and each split's count. They are split once, like the letters: when an
    output exists, nothing is written, since splitting a changed set again could move a
    question from one split to the other."""
    existing = [path for path in outputs.values() if path.exists()]
    if existing:
        raise ValueError(
            f"{existing[0].as_posix()} exists: the owner's questions are split once,"
            " like the letters, since a second split could move a question between"
            " dev and held-out"
        )
    lines = source.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines if line.strip()]
    splits = split_unanswerable([str(record["id"]) for record in records])
    items = [complete(r, splits[str(r["id"])], verified) for r in records]
    counts: dict[str, int] = {}
    for split, path in outputs.items():
        chosen = [item for item in items if item.split == split]
        write_items(path, sorted(chosen, key=lambda item: item.id))
        counts[split] = len(chosen)
    return counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.unanswerable",
        description="Split the owner's unanswerable questions by the letters' seed.",
    )
    parser.add_argument(
        "--heldout-by-owner",
        action="store_true",
        help="the owner splits the unanswerable questions (ADR-0014)",
    )
    args = parser.parse_args(argv)
    if not args.heldout_by_owner:
        print("the unanswerable questions are split by the owner only (ADR-0014)")
        return 2
    verified = f"owner, {date.today().isoformat()}"
    try:
        counts = split_questions(ALL, UNANSWERABLE, verified)
    except FileNotFoundError as err:
        print(f"{err.filename} is missing")
        return 1
    except (KeyError, TypeError, ValueError) as err:
        print(f"an input is wrong: {err}")
        return 1
    total = sum(counts.values())
    print(f"unanswerable: {total}; dev {counts['dev']}, held-out {counts['heldout']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
