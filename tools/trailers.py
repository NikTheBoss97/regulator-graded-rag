# Author: Nicola Antonello
"""Check commits: only Refs: trailers, no attribution lines, only no-reply emails.

Only Refs: may end a commit message, so no tool can add its own lines to the history,
and only GitHub no-reply addresses may name an author or committer, so no personal
email reaches the public history (ADR-0016).
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
NO_REPLY_SUFFIX = "@users.noreply.github.com"
GITHUB_NO_REPLY = "noreply@github.com"
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


def email_problems(author: str, committer: str) -> list[str]:
    """One string per role whose email is not a GitHub no-reply address."""
    # The problem names the role, never the address, because CI logs are public.
    return [
        f"{role} email is not a GitHub no-reply address"
        for role, email in (("author", author), ("committer", committer))
        if not (email.endswith(NO_REPLY_SUFFIX) or email == GITHUB_NO_REPLY)
    ]


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
        description="Reject trailers other than Refs: and emails that are not no-reply.",
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
        author, committer = _git("log", "-1", "--format=%ae%n%ce", sha).splitlines()
        found = message_problems(_git("log", "-1", "--format=%B", sha))
        found += email_problems(author, committer)
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
