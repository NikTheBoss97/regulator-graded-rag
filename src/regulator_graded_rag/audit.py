# Author: Nicola Antonello
"""The audit of the drafts that code accepts (ADR-0022).

Usage: python -m regulator_graded_rag.audit --split {dev,heldout} --draw
[--heldout-by-owner], from the repository root.

A draft with no reason from the checks is accepted by code. Once per split, this draws
a random sample of 40 of those drafts for the owner to audit, by the committed seed, and
records the pool and the sample in eval/<split>/audit.json. The file is never rewritten:
a second draw would let the checks be tuned until the sample looks right. The published
bound is the exact one-sided 95% upper bound on how many of the drafts only code
verified the owner would have changed, given how many sample drafts were changed. The
command prints counts only. Held-out audits are drawn by the owner only.
Exit code 0 when drawn, 1 when the audit exists or an input is missing, and 2 for a
held-out draw without the owner's flag.
"""

import argparse
import json
import math
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Final

from regulator_graded_rag.checks import CHECKS, reasons
from regulator_graded_rag.drafts import DRAFTS, Draft, load_drafts
from regulator_graded_rag.letter_page import LetterPage, read_page
from regulator_graded_rag.letters import SPLIT_FILE, letter_path
from regulator_graded_rag.split import SEED, draw_key, load_split

AUDIT = {
    "dev": Path("eval/dev/audit.json"),
    "heldout": Path("eval/heldout/audit.json"),
}
SAMPLE: Final = 40


@dataclass(frozen=True)
class Audit:
    split: str
    checks: str
    drawn: str
    pool: tuple[str, ...]
    sample: tuple[str, ...]


def draw_sample(
    pool: Iterable[str], seed: str = SEED, size: int = SAMPLE
) -> tuple[str, ...]:
    """The size drafts with the lowest keys, sorted; a smaller pool is taken whole. The
    keys depend on the seed and the ID alone, so the order of the pool changes nothing."""
    keyed = sorted(pool, key=lambda name: draw_key(seed, f"audit:{name}"))
    return tuple(sorted(keyed[:size]))


def draw(
    undecided: Sequence[Draft],
    page: Callable[[Draft], LetterPage | None],
    split: str,
    today: date,
) -> Audit:
    """The pool is the undecided drafts that have no reason; the sample is drawn from it."""
    pool = sorted(d.id for d in undecided if not reasons(d, page(d)))
    return Audit(split, CHECKS, today.isoformat(), tuple(pool), draw_sample(pool))


def write_audit(path: Path, audit: Audit) -> None:
    """Sorted keys and LF, written whole or not at all; never over an existing audit."""
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(asdict(audit), sort_keys=True, ensure_ascii=False) + "\n"
    part = path.with_name(path.name + ".part")
    part.write_text(text, encoding="utf-8", newline="\n")
    os.replace(part, path)


def load_audit(path: Path) -> Audit:
    record = json.loads(path.read_text(encoding="utf-8"))
    return Audit(
        split=record["split"],
        checks=record["checks"],
        drawn=record["drawn"],
        pool=tuple(record["pool"]),
        sample=tuple(record["sample"]),
    )


def upper_bound(pool: int, sampled: int, changed: int, alpha: float = 0.05) -> int:
    """The largest number K of changeable drafts in the pool for which a sample of the
    given size, drawn without replacement, still shows at most this many changes with
    probability alpha or more (the hypergeometric distribution's exact tail)."""
    total = math.comb(pool, sampled)
    best = changed
    for bad in range(changed, pool + 1):
        seen = sum(
            math.comb(bad, k) * math.comb(pool - bad, sampled - k)
            for k in range(changed + 1)
        )
        if seen / total >= alpha:
            best = bad
    return best


def changed(audit: Audit, actions: Mapping[str, str]) -> int:
    """The sampled drafts the owner edited or rejected; a read is not a decision."""
    return sum(actions.get(name) in ("edit", "reject") for name in audit.sample)


def describe(audit: Audit, actions: Mapping[str, str], read: int, items: int) -> str:
    """The bound in words: for the drafts only code verified, and for all the items."""
    if len(audit.pool) <= len(audit.sample):
        return f"audit: the owner checked the whole pool of {len(audit.pool)}"
    n_changed = changed(audit, actions)
    if n_changed >= 2:
        return (
            f"audit: {n_changed} of {len(audit.sample)} sampled drafts changed, so"
            f" the owner checked the whole pool of {len(audit.pool)}"
        )
    if read == 0:
        return (
            f"audit: {n_changed} of {len(audit.sample)} sampled drafts changed; no"
            " item rests on code's checks alone"
        )
    bound = upper_bound(len(audit.pool), len(audit.sample), n_changed)
    residual = min(bound - n_changed, read)
    return (
        f"audit: {n_changed} of {len(audit.sample)} sampled drafts changed; at most"
        f" {residual} of the {read} items only code verified would have been changed"
        f" (95%): {residual / read:.1%} of them, {residual / items:.1%} of the"
        f" {items} items"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.audit",
        description="Draw the audit of the drafts that code accepts.",
    )
    parser.add_argument("--split", required=True, choices=sorted(AUDIT))
    parser.add_argument("--draw", action="store_true", required=True)
    parser.add_argument(
        "--heldout-by-owner",
        action="store_true",
        help="the owner draws the held-out audit (ADR-0014)",
    )
    args = parser.parse_args(argv)
    if args.split == "heldout" and not args.heldout_by_owner:
        print("the held-out audit is drawn by the owner only (ADR-0014)")
        return 2
    # review_page imports this module, so it is imported here and not at the top.
    from regulator_graded_rag.review_page import DECISIONS, UNANSWERABLE, pending

    out = AUDIT[args.split]
    if out.exists():
        print(f"{out.as_posix()} exists: the audit is drawn once")
        return 1
    if not UNANSWERABLE[args.split].is_file():
        print(f"{UNANSWERABLE[args.split]} is missing")
        return 1
    try:
        drafts = load_drafts(DRAFTS[args.split])
        undecided = pending(drafts, DECISIONS[args.split])
        splits = load_split(SPLIT_FILE)
    except FileNotFoundError as err:
        print(f"{err.filename} is missing")
        return 1

    def page(draft: Draft) -> LetterPage | None:
        path = letter_path(draft.letter, splits) if draft.letter in splits else None
        if path is None or not path.is_file():
            return None
        return read_page(path.read_text(encoding="utf-8"))

    drawn = draw(undecided, page, args.split, date.today())
    write_audit(out, drawn)
    print(
        f"pool {len(drawn.pool)}, sample {len(drawn.sample)},"
        f" with a reason {len(undecided) - len(drawn.pool)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
