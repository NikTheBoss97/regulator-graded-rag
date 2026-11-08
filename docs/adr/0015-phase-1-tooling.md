<!-- Author: Nicola Antonello -->

# ADR-0015: Phase 1 tooling: Python 3.14, mypy and pinned gate tools

- Status: accepted
- Date: 2026-11-08

## Context

ADR-0002 chose Python, managed with uv, with ruff, a type checker and pytest as gates,
and left the Python version and the type checker to phase 1. ADR-0013 lists the checks
every change must pass: gitleaks, actionlint, zizmor, ruff, the type checker and a check
on commit-message trailers, with every tool pinned to verified bytes. Phase 1 has to
decide the type checker, how each gate tool reaches a developer's machine and CI, and
which trailers are allowed. Docker is already required, for Postgres (ADR-0004).

Checked on 2026-11-08 on PyPI, GitHub and Docker Hub:

- Every package the plan needs publishes Python 3.14 wheels for Windows and Linux, among
  them psycopg 3.3.8, lxml 6.1.3, numpy 2.5.4, sentence-transformers 6.2.0, bm25s 0.3.16,
  ruff 0.17.4, zizmor 1.32.0, pytest 9.2.0 and mypy 2.4.1. PyTorch's CUDA builds for
  Python 3.14 on Windows were confirmed on 2026-11-06 (ADR-0009).
- gitleaks v8.30.1 and actionlint v1.7.12, both under MIT, are each project's latest
  release, and each has an official image with amd64 and arm64 builds.
- uv's lock file records a SHA-256 hash for every file it resolves: uv's own lock file
  holds 1,025 of them.

## Options

The type checker:

| Option | Why not |
|---|---|
| **mypy** | Chosen. The reference type checker for Python, under MIT, marked stable on PyPI, and published as plain wheels, so uv's lock pins it by hash like any other dependency. It is slower than the alternatives, which does not matter at this project's size. |
| pyright | Fast, from Microsoft, but written in TypeScript. Its PyPI package is a wrapper that, when Node.js is missing, downloads it at run time and then installs pyright with npm, so the code that runs is not pinned by uv's lock. The basedpyright fork ships as wheels, at the cost of depending on a fork. |
| A Rust-based checker: pyrefly or ty | Very fast. pyrefly (1.4.1) is marked stable, and ty (0.0.99) is still in beta. Both are much newer than mypy. |

How the gate tools are installed:

| Option | Why not |
|---|---|
| **Python tools from uv's lock; gitleaks and actionlint from their official images, pinned by digest** | Chosen. ruff, zizmor, mypy and pytest are dev dependencies pinned by hash in `uv.lock`. gitleaks and actionlint run through `docker run` from their official images, pinned by digest, which run natively on the Windows laptop, the Mac and CI. There is no image of the project's own to maintain. |
| One toolbox image, built from a Dockerfile that pins every tool by checksum | Every tool in one place, but an image to maintain, built for one architecture unless built twice, and the Python tools would be pinned twice: in the image and in `uv.lock`. |
| pre-commit | It runs the gates on every commit by itself, and its hooks can be frozen to commit hashes. But it builds each hook's environment itself, outside `uv.lock`, so the tools would be pinned in a second place. |

## Decision

- **Python 3.14**, managed by uv.
- **mypy** is the type checker. The phase 1 plan sets its configuration.
- **Gate tools.** ruff, zizmor, mypy and pytest are uv dev dependencies. gitleaks and
  actionlint run from their official images, `zricethezav/gitleaks` and
  `rhysd/actionlint`, each pinned by digest. One Python script runs the gates in order,
  stops at the first failure, and is the same command on every machine and in CI.
- **Trailers.** The commit check allows only `Refs:`, which the commit rules use to point
  at decision records and issues, and rejects every other trailer.

## Consequences

- Phase 1 needs no Node.js toolchain and no Dockerfile, so hadolint and shellcheck have
  nothing to check until a Dockerfile or a shell script appears.
- A digest fixes an image's bytes, so updating gitleaks or actionlint means changing the
  digest by hand.
- The images are pulled from Docker Hub on first use, so the gates need the network once
  per machine.
- When the options were presented, pre-commit was described as pinning hooks only to git
  tags. Its documentation shows that `autoupdate --freeze` pins them to commit hashes.
  The reason it was not chosen is the second set of pinned environments.
- Unverified: how long mypy takes on this codebase, and how the image-based gates handle
  Windows paths. Phase 1 measures both.

## Amendments

- 2026-11-08: Phase 1 measured both on the Windows laptop. mypy checks the seven source
  files in about two seconds from a cold cache, and all ten gates run in about twelve
  seconds. The image-based gates mount the repository by its Windows path, which
  contains a space, without trouble. They cannot work in a linked git worktree, whose
  `.git` file names a host path that does not exist in the container: there gitleaks
  scanned nothing and still passed. The gates now first check that git in the container
  can read the repository, and fail when it cannot, so they run from the main checkout.
  The Mac is not measured yet.

## References

- mypy, [documentation](https://mypy.readthedocs.io/en/stable/).
- Pyright for Python, [PyPI page](https://pypi.org/project/pyright/), section "How Pyright for Python Works".
- [ty](https://pypi.org/project/ty/) and [pyrefly](https://pypi.org/project/pyrefly/) on PyPI.
- [gitleaks](https://github.com/gitleaks/gitleaks) and [actionlint](https://github.com/rhysd/actionlint) on GitHub.
- uv documentation, [Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/), and uv's own [lock file](https://github.com/astral-sh/uv/blob/main/uv.lock).
- [pre-commit](https://pre-commit.com/) documentation, on `autoupdate --freeze`.
- Git documentation, [git-interpret-trailers](https://git-scm.com/docs/git-interpret-trailers).
