# Author: Nicola Antonello
"""Draw the dev and held-out split of the letters, once, before anyone reads them (ADR-0018).

Usage: python -m regulator_graded_rag.split (--dry-run | --expect DIGEST) [--letters PATH]
[--split PATH], from the repository root. It checks every letter file against the
manifest, groups the letters (see groups), and sends 40% of each year's groups, rounded
half up, to held-out: those with the lowest SHA-256 keys of the seed and their lowest
reference number. --dry-run prints the counts and the assignment's digest, with the
Python version that computed it, and writes and moves nothing. The draw itself needs
--expect with the digest of the dry run that was approved: it then writes
eval/split.jsonl, whose SHA-256 is that digest, and moves each letter file into its
split's folder. Everything printed is a count, a year or a reference number. The split
is drawn once: the command refuses to run when the split file exists.
Exit code 0 when the split is drawn (or would be); 1 when a letter file is missing or
changed, or the unsplit folder still holds files after the draw; 2 when the split
exists; 3 when a group is too large for the draw; 4 when the draw's digest is not the
one expected, in which case nothing is written or moved.
"""

import argparse
import hashlib
import io
import json
import os
import platform
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from regulator_graded_rag import letters as letter_files
from regulator_graded_rag.groups import (
    GroupTooLarge,
    check_sizes,
    group_letters,
    report,
)
from regulator_graded_rag.letter_page import read_page
from regulator_graded_rag.letters import (
    DEFAULT_LETTERS,
    SPLIT_FILE,
    html_of,
    letter_path,
    letter_year,
    load_letters,
)

# The corpus version (ADR-0006), recorded before any letter was listed, so nobody can
# have chosen it to shape the split.
SEED = "ecaac596422344e6b548dcd8a1816261a27d398d0d707077def27a5976db34ef"
# Read during the design (ADR-0008), so they go to dev.
ALREADY_READ = frozenset({"20-0003", "20-0018", "20-0034"})
Split = Literal["dev", "heldout"]


def draw_key(seed: str, name: str) -> str:
    """The same on any machine and Python version, unlike random's sample()."""
    return hashlib.sha256(f"{seed}:{name}".encode()).hexdigest()


def heldout_count(n: int) -> int:
    """40% of n groups, rounded half up."""
    return (4 * n + 5) // 10


@dataclass(frozen=True, order=True)
class Assigned:
    letter: str
    group: str  # the group's lowest reference number
    year: int  # the group's year, the stratum of the draw: that number's reference year
    split: Split


def assign(groups: Sequence[Sequence[str]], seed: str = SEED) -> list[Assigned]:
    """Each letter's split, sorted by letter, with every group kept together.

    In each year, the groups with the lowest keys go to held-out, drawn from the groups
    that hold no letter already read, so that a year still sends 40% of all its groups.
    """
    by_year: defaultdict[int, list[tuple[str, ...]]] = defaultdict(list)
    for group in groups:
        by_year[letter_year(min(group))].append(tuple(sorted(group)))
    rows: list[Assigned] = []
    for year, year_groups in by_year.items():
        k = heldout_count(len(year_groups))
        candidates = sorted(
            (g for g in year_groups if not ALREADY_READ & set(g)),
            key=lambda g: draw_key(seed, g[0]),
        )
        if k > len(candidates):
            raise ValueError(f"{year}: {k} held-out groups from {len(candidates)}")
        heldout = set(candidates[:k])
        rows += [
            Assigned(letter, g[0], year, "heldout" if g in heldout else "dev")
            for g in year_groups
            for letter in g
        ]
    return sorted(rows)


def _lines(rows: Sequence[Assigned]) -> str:
    return "".join(json.dumps(asdict(row)) + "\n" for row in sorted(rows))


def write_split(path: Path, rows: Sequence[Assigned]) -> None:
    """JSON lines sorted by letter, written through a temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.name}.part")
    with part.open("w", encoding="utf-8", newline="\n") as file:
        file.write(_lines(rows))
    os.replace(part, path)


def load_split(path: Path) -> dict[str, Split]:
    splits: dict[str, Split] = {}
    with path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["split"] == "dev":
                splits[row["letter"]] = "dev"
            elif row["split"] == "heldout":
                splits[row["letter"]] = "heldout"
            else:
                raise ValueError(f"{path}: {row['letter']}: split {row['split']!r}")
    return splits


def _summary(rows: Sequence[Assigned]) -> list[str]:
    """Per year and in total: groups and letters, and how many groups each split holds."""
    lines = []
    for year in sorted({r.year for r in rows}):
        of_year = [r for r in rows if r.year == year]
        groups = {r.group: r.split for r in of_year}
        sides = Counter(groups.values())
        lines.append(
            f"{year}: {len(groups)} groups, {len(of_year)} letters:"
            f" dev {sides['dev']}, held-out {sides['heldout']}"
        )
    groups = {r.group: r.split for r in rows}
    sides, letters = Counter(groups.values()), Counter(r.split for r in rows)
    lines.append(
        f"total: {len(groups)} groups, {len(rows)} letters: dev {sides['dev']} groups"
        f" ({letters['dev']} letters), held-out {sides['heldout']} groups"
        f" ({letters['heldout']} letters)"
    )
    split_of = {r.letter: r.split for r in rows}
    lines.append(
        "already read: "
        + ", ".join(
            f"{x} {split_of.get(x, 'not in the pool')}" for x in sorted(ALREADY_READ)
        )
    )
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    # Windows encodes a piped stdout as cp1252: escape what it cannot show.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.split",
        description="Group the letters and draw dev and held-out, once; prints counts"
        " and reference numbers only.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the counts; write and move nothing",
    )
    parser.add_argument(
        "--expect",
        metavar="DIGEST",
        help="the digest of the approved dry run; the draw refuses any other",
    )
    parser.add_argument("--letters", type=Path, default=DEFAULT_LETTERS)
    parser.add_argument("--split", type=Path, default=SPLIT_FILE)
    args = parser.parse_args(argv)
    if args.split.exists():
        print("the split exists; it is drawn once")
        return 2
    if not args.letters.exists():
        print(
            f"no manifest at {args.letters}:"
            ' run "uv run python -m regulator_graded_rag.letters --list"'
        )
        return 1
    manifest = load_letters(args.letters)
    texts: dict[str, str | None] = {}
    for letter in manifest:
        path = letter_path(letter.id, None)
        data = path.read_bytes() if path.is_file() else None
        if data is None or (len(data), hashlib.sha256(data).hexdigest()) != (
            letter.size,
            letter.sha256,
        ):
            problem = "missing" if data is None else "changed"
            print(
                f"{letter.id}: {problem}:"
                ' run "uv run python -m regulator_graded_rag.letters"'
            )
            return 1
        page = read_page(html_of(data))
        texts[letter.id] = page.text if page else None
    grouping = group_letters(texts, [x.id for x in manifest])
    print("\n".join(report(grouping)))
    try:
        check_sizes(grouping)
    except GroupTooLarge as err:
        print(err)
        return 3
    rows = assign(grouping.groups)
    print("\n".join(_summary(rows)))
    digest = hashlib.sha256(_lines(rows).encode()).hexdigest()
    # The grouping reads text with html.parser and \w, so the Python version is recorded.
    print(f"assignment digest {digest} (Python {platform.python_version()})")
    if args.dry_run:
        return 0
    if args.expect != digest:
        print(
            f"the draw's digest is not the expected {args.expect or '(none given)'}:"
            " nothing written or moved"
        )
        return 4
    write_split(args.split, rows)
    splits = load_split(args.split)
    for letter in manifest:
        target = letter_path(letter.id, splits)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(letter_path(letter.id, None), target)
    for folder in (letter_files.DEV_LETTERS, letter_files.HELDOUT_LETTERS):
        print(f"{folder}: {sum(1 for _ in folder.glob('*.html'))} files")
    unsplit = letter_files.UNSPLIT
    if left := sum(1 for _ in unsplit.iterdir()):
        print(f"{unsplit} still holds {left} files, so it stays")
        return 1
    unsplit.rmdir()
    print(f"{unsplit} is empty and removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
