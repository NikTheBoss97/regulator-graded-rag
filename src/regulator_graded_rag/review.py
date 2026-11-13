# Author: Nicola Antonello
"""Draw the passages the owner compares with the printed pages (ADR-0006, ADR-0017).

The sample comes from the hardest sections with a fixed seed, so the same corpus always
gives the same sheet. It always holds the passages whose quirks are known: the minus
tagged apart from its exponent, the table that lacks a header level, and two tables whose
rows can misplace their column labels.

Usage: python -m regulator_graded_rag.review [--passages PATH] [--manifest PATH]
[--out PATH] [--seed N] [--force], from the repository root, after the passage build.
It refuses passages whose count or version differs from the manifest's, so the owner's
verdicts always name the corpus they were made on, and it replaces an existing sheet
only with --force, because the sheet may hold the owner's verdicts.
"""

import argparse
import json
import random
import re
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

from regulator_graded_rag.manifest import DEFAULT_MANIFEST, load_manifest
from regulator_graded_rag.passages import DEFAULT_OUT, version_of


class Record(TypedDict):
    id: str
    kind: str
    source: str
    page: int
    text: str


# (unit, kind, how many), drawn in this order from one random.Random.
SAMPLE = (
    ("172.101", "row", 8),
    ("172.102", "row", 2),
    ("172.102", "text", 3),
    ("173.62", "row", 4),
    ("173.435", "row", 4),
)
# The first passage holding each of these is always in the sample.
ALWAYS = (
    "Symbol of radionuclide: Rb(nat)",  # a minus tagged apart from its exponent
    "Table 1 to § 173.319(d)(2)",  # a table that lacks a header level
    "Sum of transport indexes of the packages: 0.6 to 1",  # §176.708: labels repeat
    "10 or less: .100",  # §178.348-2: a thickness without its lading density
)
DEFAULT_SHEET = Path("corpus/parse-review.md")
SEED = 2025
_VOLUME = re.compile(r"-vol(\d+)-")


def _unit(record: Record) -> str:
    return record["id"].rsplit(":", 1)[0]


def _volume(source: str) -> str:
    match = _VOLUME.search(source)
    if match is None:
        raise ValueError(f"no volume in {source!a}")
    return match.group(1)


def pdf_url(unit: str, source: str) -> str:
    """GovInfo's PDF of one section of the 2025 edition, in the volume source is from."""
    v = _volume(source)
    section = unit.replace(".", "-")
    return (
        f"https://www.govinfo.gov/content/pkg/CFR-2025-title49-vol{v}/pdf/"
        f"CFR-2025-title49-vol{v}-sec{section}.pdf"
    )


def choose(records: Sequence[Record], seed: int) -> list[Record]:
    """The ALWAYS passages, then a seeded draw from each SAMPLE pool, in file order."""
    picked: set[str] = set()
    for needle in ALWAYS:
        found = next((r for r in records if needle in r["text"]), None)
        if found is None:
            raise ValueError(f"no passage holds {needle!a}")
        picked.add(found["id"])
    always = set(picked)
    rng = random.Random(seed)
    for unit, kind, count in SAMPLE:
        pool = [
            r
            for r in records
            if _unit(r) == unit and r["kind"] == kind and r["id"] not in always
        ]
        picked.update(r["id"] for r in rng.sample(pool, count))
    return [r for r in records if r["id"] in picked]


def sheet(
    chosen: Sequence[Record], records: Sequence[Record], version: str, seed: int
) -> str:
    """The Markdown sheet: each chosen passage with its PDF page and an open verdict."""
    first_page: dict[str, int] = {}
    for r in records:
        first_page.setdefault(_unit(r), r["page"])
    lines = [
        "<!-- Author: Nicola Antonello -->",
        "",
        "# Passages compared with the printed pages",
        "",
        (
            f"Corpus version `{version}`. Sample drawn with seed {seed} by"
            " `uv run python -m regulator_graded_rag.review`; the same seed draws the"
            " same passages."
        ),
        "",
        (
            "Compare every word and number of each passage, in order, with its printed"
            " page of the 2025 edition. `^` marks a superscript. A table row shows its"
            " section's heading, its table's title, then one `label: value` line per"
            " non-empty cell; check that each value sits under the right column. Tick"
            " the box when the passage matches, or describe each difference."
        ),
        "",
    ]
    for n, r in enumerate(chosen, start=1):
        unit = _unit(r)
        offset = r["page"] - first_page[unit] + 1
        lines += [
            f"## {n}. `{r['id']}`",
            "",
            (
                f"Printed page {r['page']} of volume {_volume(r['source'])}:"
                f" page {offset} of [the section PDF]({pdf_url(unit, r['source'])})."
            ),
            "",
            "```text",
            r["text"],
            "```",
            "",
            "- [ ] Matches the printed page",
            "- Differences:",
            "",
        ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.review",
        description="Write the sheet for comparing sampled passages with the PDF pages.",
    )
    parser.add_argument("--passages", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_SHEET)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing sheet, and the verdicts it may hold",
    )
    args = parser.parse_args(argv)
    if args.out.exists() and not args.force:
        print(
            f"{args.out} exists and may hold the owner's verdicts:"
            " move it, or pass --force to replace it"
        )
        return 1
    with args.passages.open(encoding="utf-8") as lines:
        records: list[Record] = [json.loads(line) for line in lines]
    version = version_of((r["id"], r["text"]) for r in records)
    manifest = load_manifest(args.manifest)
    if (len(records), version) != (manifest.passages, manifest.version):
        print(
            f"{len(records)} passages with version {version} differ from the manifest"
            f" (count {manifest.passages}, version {manifest.version}):"
            ' run "uv run python -m regulator_graded_rag.passages" first'
        )
        return 1
    chosen = choose(records, args.seed)
    with args.out.open("w", encoding="utf-8", newline="\n") as out:
        out.write(sheet(chosen, records, version, args.seed))
    print(f"wrote {args.out}: {len(chosen)} passages from corpus version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
