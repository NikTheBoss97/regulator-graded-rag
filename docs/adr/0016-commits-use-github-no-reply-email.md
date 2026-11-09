<!-- Author: Nicola Antonello -->

# ADR-0016: Commits use GitHub's no-reply email

- Status: accepted
- Date: 2026-11-09

## Context

The repository's first commits named the owner's personal email address as their author,
and the repository is public, so every clone, patch and CI record showed it. On
2026-11-09 the owner decided that no personal information is ever committed, commit
metadata included. The owner's name stays, in each file's author line and as the commit
author, because it credits the work.

Checked on 2026-11-09:

- No committed file held the address. Commit metadata did, and so did GitHub's records of
  pull requests #1 and #2 and of the five CI runs.
- GitHub's documentation, "Removing sensitive data from a repository": after a rewrite and
  a force-push, the old commits stay reachable through pull request refs, which GitHub
  marks read-only, and through cached views, until GitHub Support removes them.
- GitHub's setting "Block command line pushes that expose my email" checks only the most
  recent commit of each push.
- Dependabot's own commits name `49699333+dependabot[bot]@users.noreply.github.com` as
  author and `noreply@github.com` as committer.

## Options

Removing the address that was already published:

| Option | Why not |
|---|---|
| **Rewrite the history, then delete and recreate the repository** | Chosen. Only the emails change: every commit keeps its files, message, author name and dates, under a new ID. Deleting the repository removes the pull request refs, CI records and cached views at once. Pull requests #1 and #2 and their CI runs are lost; their substance is in the commit messages. |
| Rewrite the history, force-push and ask GitHub Support | Keeps the repository and its pull request pages, but the old commits stay reachable until Support dereferences them, and the ruleset's force-push block has to be lifted. |
| Fix only future commits | Leaves the address in every published commit. |

Keeping it out:

| Option | Why not |
|---|---|
| **The commit check rejects every author or committer email that is not a GitHub no-reply address** | Chosen. It runs in the gates and in CI on every commit it checks, from any clone. |
| GitHub's push-blocking setting alone | Checks only the newest commit of a push, and lives in the owner's account rather than in the repository. |
| The instructions and each clone's git configuration | Nothing fails when a new clone, such as the Mac's, still uses the personal address. |

## Decision

- Every clone sets `git config user.email` to the owner's GitHub no-reply address.
- The commit check accepts an author or committer email only when it ends in
  `@users.noreply.github.com` or is `noreply@github.com`, the address GitHub gives the
  commits it makes itself. A problem names the role, never the address, because CI logs
  are public.
- On 2026-11-09 the history was rewritten once to replace the personal address, and the
  repository was deleted and recreated with the rewritten history. The commit IDs
  changed; their files, messages, names and dates did not.

## Consequences

- Dependabot's commits pass this check.
- The owner can also turn on "Keep my email addresses private" and "Block command line
  pushes that expose my email" in GitHub's email settings, as a second guard.
- A personal address or a secret that reaches a pushed commit is removed the same way:
  rewrite the history, then remove every copy on GitHub. A secret is also rotated.

## References

- GitHub documentation, [Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).
- GitHub documentation, [Blocking command line pushes that expose your personal email address](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/blocking-command-line-pushes-that-expose-your-personal-email-address).
