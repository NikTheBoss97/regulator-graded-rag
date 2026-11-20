# Author: Nicola Antonello
"""The gold items, built from the drafts and the owner's decisions (ADR-0007, ADR-0012).

Usage: python -m regulator_graded_rag.items --split {dev,heldout} [--heldout-by-owner]
[--freeze], from the repository root.

Every kept draft needs the owner's decision on it as it now reads, except in the
audit's pool (ADR-0022): when eval/<split>/audit.json exists, a pool draft outside the
audit sample that the owner has read for personal data becomes an item that code's
checks verified, while fewer than two sampled drafts have changed. The command then
prints the audit's bound. Approve keeps the
draft as drafted, Save edits keeps it with the owner's fields, and Reject drops it. An
item whose date or evidence the owner edited must pass the drift check again, or it is
dropped. The owner's unanswerable questions for the split join the letter items, and all
are written to eval/<split>/items.jsonl, sorted by ID, then read back through the gold
checks. The command prints counts only. --freeze, for the held-out split, records the
file's SHA-256 and item count in eval/heldout-items.sha256, which a held-out run then
requires (ADR-0014). Held-out items are built by the owner only.
Exit code 0 when the items are written, 1 when an input is missing or wrong, and 2 for
a held-out run without the owner's flag.
"""

import argparse
import json
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date, datetime
from pathlib import Path

from regulator_graded_rag.audit import AUDIT, Audit, changed, describe, load_audit
from regulator_graded_rag.drafts import DRAFTS, Draft, load_drafts
from regulator_graded_rag.drift import check, parse_citation
from regulator_graded_rag.ecfr import Cache, default_cache
from regulator_graded_rag.gold import Item, load_items, validate, write_items
from regulator_graded_rag.review_page import (
    DECISIONS,
    UNANSWERABLE,
    digest,
    item_record,
)
from regulator_graded_rag.runs import FROZEN, GOLD, freeze


def latest(
    decisions: Iterable[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    """Each draft's last decision: a later one replaces an earlier one."""
    found: dict[str, Mapping[str, object]] = {}
    for decision in decisions:
        found[str(decision["id"])] = decision
    return found


def build(
    drafts: Sequence[Draft],
    decisions: Mapping[str, Mapping[str, object]],
    unanswerable: Sequence[Item],
    recheck: Callable[[Item], bool],
    audit: Audit | None = None,
) -> tuple[list[Item], Counter[str]]:
    """The items, sorted by ID, and how many were kept, read, rejected, dropped on
    recheck, and written by the owner. Every kept draft needs a decision on it as it now
    reads, except the audit's: a pool draft outside the sample, while fewer than two
    sampled drafts have changed, may instead have a read, and then code's checks verify
    it. An approval keeps the draft as drafted and an edit keeps the edited fields; an
    item whose date or evidence was edited must pass recheck, and every item the gold
    checks."""
    kept = [draft for draft in drafts if draft.kept]
    current = {
        draft.id: str(decisions[draft.id].get("action"))
        for draft in kept
        if decisions.get(draft.id, {}).get("digest") == digest(draft)
    }
    readable: set[str] = set()
    if audit is not None and changed(audit, current) < 2:
        readable = set(audit.pool) - set(audit.sample)
    unread = [
        draft.id for draft in kept if draft.id in readable and draft.id not in current
    ]
    if unread:
        raise ValueError(
            f"{len(unread)} not yet read for personal data: {_shown(unread)}"
        )
    undecided = [
        draft.id
        for draft in kept
        if current.get(draft.id) not in ("approve", "edit", "reject")
        and not (current.get(draft.id) == "read" and draft.id in readable)
    ]
    if undecided:
        raise ValueError(
            f"{len(undecided)} undecided, with no decision on the draft as it now"
            f" reads: {_shown(undecided)}"
        )
    counts: Counter[str] = Counter()
    built: list[Item] = []
    for draft in kept:
        decision = decisions[draft.id]
        action = decision.get("action")
        if action == "reject":
            counts["rejected"] += 1
            continue
        if action == "read" and audit is not None:
            by = f"code checks {audit.checks}"
            built.append(
                validate(
                    item_record(draft, {}, date.fromisoformat(audit.drawn), by=by),
                    draft.id,
                )
            )
            counts["read"] += 1
            continue
        if action not in ("approve", "edit"):
            raise ValueError(f"{draft.id}: action: {action!r} is not a decision")
        fields = decision.get("fields") if action == "edit" else {}
        if not isinstance(fields, Mapping):
            raise TypeError(f"{draft.id}: fields: not an object")
        day = datetime.fromisoformat(str(decision.get("at"))).date()
        item = validate(item_record(draft, fields, day), draft.id)
        if ("letter_date" in fields or "evidence" in fields) and not recheck(item):
            counts["dropped on recheck"] += 1
            continue
        counts["kept"] += 1
        built.append(item)
    if unanswerable:
        counts["the owner's"] += len(unanswerable)
    return sorted([*built, *unanswerable], key=lambda item: item.id), counts


def _shown(names: Sequence[str]) -> str:
    """The first five IDs, and an ellipsis when there are more."""
    return ", ".join(names[:5]) + (", …" if len(names) > 5 else "")


def _recheck(cache: Cache) -> Callable[[Item], bool]:
    """The drift check again, for an item whose date or evidence the owner edited."""

    def again(item: Item) -> bool:
        if not item.answerable:
            return True
        day = date.fromisoformat(item.letter_date)
        outcomes = check(map(parse_citation, item.evidence), day, cache)
        return all(outcome == "unchanged" for outcome in outcomes.values())

    return again


def _decisions(path: Path) -> list[Mapping[str, object]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.items",
        description="Build a split's gold items from the drafts and the owner's decisions.",
    )
    parser.add_argument("--split", required=True, choices=sorted(GOLD))
    parser.add_argument(
        "--heldout-by-owner",
        action="store_true",
        help="the owner builds the held-out items (ADR-0014)",
    )
    parser.add_argument(
        "--freeze",
        action="store_true",
        help=f"held-out only: record the items' SHA-256 in {FROZEN.as_posix()}",
    )
    args = parser.parse_args(argv)
    if args.split == "heldout" and not args.heldout_by_owner:
        print("held-out items are built by the owner only (ADR-0014)")
        return 2
    if args.freeze and args.split != "heldout":
        print("--freeze is for the held-out split only")
        return 1
    try:
        drafts = load_drafts(DRAFTS[args.split])
        decisions = latest(_decisions(DECISIONS[args.split]))
        owners = load_items(UNANSWERABLE[args.split])
        splits = {d.id: d.split for d in drafts} | {i.id: i.split for i in owners}
        stray = next((name for name, s in splits.items() if s != args.split), None)
        if stray is not None:
            raise ValueError(f"{stray} belongs to another split than {args.split}")
        path = AUDIT[args.split]
        audit = load_audit(path) if path.is_file() else None
        built, counts = build(
            drafts, decisions, owners, _recheck(default_cache()), audit
        )
    except FileNotFoundError as err:
        print(f"{err.filename} is missing")
        return 1
    except (KeyError, TypeError, ValueError) as err:
        print(err)
        return 1
    out = GOLD[args.split]
    write_items(out, built)
    written = load_items(out)
    types = Counter(item.type for item in written)
    counted = ", ".join(f"{name} {n}" for name, n in sorted(counts.items()))
    print(f"items: {len(written)}; {counted}")
    lowest = sorted(types.items(), key=lambda pair: (pair[1], pair[0]))
    print("by type, lowest first: " + ", ".join(f"{t} {n}" for t, n in lowest))
    if audit is not None:
        actions = {name: str(d.get("action")) for name, d in decisions.items()}
        current = {
            d.id: actions[d.id]
            for d in drafts
            if d.kept and decisions.get(d.id, {}).get("digest") == digest(d)
        }
        print(describe(audit, current, counts["read"], len(written)))
    if args.freeze:
        freeze(out, FROZEN, len(written))
        print(
            f"frozen in {FROZEN.as_posix()}; back up {out.as_posix()} outside the repo"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
