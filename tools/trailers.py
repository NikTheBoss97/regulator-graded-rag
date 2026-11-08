# Author: Nicola Antonello
"""Reject commit trailers other than Refs:, and co-author or "Generated with" lines.

Only Refs: may end a commit message, so no tool can add its own lines to the history.
Usage: python -m tools.trailers [--base REV]. Exit code 0 when every commit is clean,
1 when one has a problem, 2 when the base is not a commit in this clone.
"""

import argparse
import os
import re
import subprocess
from collections.abc import Sequence

ALLOWED_TRAILERS: frozenset[str] = frozenset({"Refs"})
ZERO_SHA = "0" * 40
_CO_AUTHOR = re.compile(r"^co-authored-by:", re.IGNORECASE | re.MULTILINE)
_GENERATED_WITH = re.compile(r"^\W*generated with", re.IGNORECASE | re.MULTILINE)


def _git(*args: str, stdin: str | None = None) -> str:
    # UTF-8 explicitly: git stores messages as UTF-8, and Windows pipes default to cp1252.
    result = subprocess.run(
        ["git", *args], input=stdin, capture_output=True, encoding="utf-8", check=True
    )
    return result.stdout


def trailer_keys(message: str) -> list[str]:
    """The trailer keys git finds at the end of a message, in order."""
    # --no-divider: the input is the whole message, as git reads a commit's trailers;
    # without it, a "---" line would hide every trailer after it.
    parsed = _git("interpret-trailers", "--parse", "--no-divider", stdin=message)
    return [line.split(":", 1)[0] for line in parsed.splitlines() if line]


def message_problems(message: str) -> list[str]:
    """One string per problem: disallowed trailers, then co-author and generated lines."""
    problems = [
        f'trailer "{key}" is not allowed'
        for key in trailer_keys(message)
        if key not in ALLOWED_TRAILERS
    ]
    if _CO_AUTHOR.search(message):
        problems.append("co-author line")
    if _GENERATED_WITH.search(message):
        problems.append("generated-with line")
    return problems


def commits_to_check(base: str | None, head: str = "HEAD") -> list[str]:
    """Commits in base..head, oldest first and without merges; all of them for no base."""
    if base is None or base == ZERO_SHA:
        revisions = head
    else:
        try:
            _git("cat-file", "-e", f"{base}^{{commit}}")
        except subprocess.CalledProcessError:
            raise ValueError(f"base {base} is not a commit in this clone") from None
        revisions = f"{base}..{head}"
    return _git("rev-list", "--no-merges", "--reverse", revisions).split()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.trailers",
        description="Reject commit trailers other than Refs:.",
    )
    parser.add_argument(
        "--base",
        default=os.environ.get("TRAILER_BASE") or None,
        help="check the commits after this one; default $TRAILER_BASE, else all",
    )
    args = parser.parse_args(argv)
    try:
        commits = commits_to_check(args.base)
    except ValueError as err:
        print(err)
        return 2
    problems = 0
    for sha in commits:
        found = message_problems(_git("log", "-1", "--format=%B", sha))
        if found:
            subject = _git("log", "-1", "--format=%s", sha).strip()
            short = _git("rev-parse", "--short", sha).strip()
            for problem in found:
                print(f"{short} {subject}: {problem}")
        problems += len(found)
    print(f"{len(commits)} commit(s) checked, {problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
