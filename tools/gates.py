# Author: Nicola Antonello
"""Run every quality gate in order, stopping at the first failure (ADR-0015).

Usage: python -m tools.gates [--trailer-base REV]. gitleaks and actionlint run from their
official images, pinned by digest; ruff, mypy, pytest and zizmor come from uv.lock. A gate
that does not apply is announced with a SKIP line, never left out silently. Run it from
the main checkout: git in the containers cannot follow a linked worktree's .git file, so
there the first gate fails.
"""

import argparse
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

GITLEAKS_IMAGE = "zricethezav/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"  # v8.30.1
ACTIONLINT_IMAGE = "rhysd/actionlint@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667"  # 1.7.12

Runner = Callable[[Sequence[str]], int]


@dataclass(frozen=True)
class Gate:
    name: str
    argv: tuple[str, ...]


def docker_run(
    image: str, repo: Path, *args: str, entrypoint: str | None = None
) -> tuple[str, ...]:
    """A command that runs an image on the repository, mounted read-only at /repo."""
    override = ("--entrypoint", entrypoint) if entrypoint else ()
    return (
        "docker",
        "run",
        "--rm",
        "--mount",
        f"type=bind,source={repo},target=/repo,readonly",
        "--workdir",
        "/repo",
        # Marks /repo as safe, or git in the container refuses a repository it does not own.
        "-e",
        "GIT_CONFIG_COUNT=1",
        "-e",
        "GIT_CONFIG_KEY_0=safe.directory",
        "-e",
        "GIT_CONFIG_VALUE_0=/repo",
        *override,
        image,
        *args,
    )


def plan_gates(
    repo: Path, *, has_workflows: bool, trailer_base: str | None
) -> list[Gate]:
    """The gates that apply, in the order they run."""
    gates = [
        # When git in the container cannot open the repository, as in a linked worktree,
        # gitleaks scans nothing and still exits 0; this gate fails first instead.
        Gate(
            "gitleaks reads git",
            docker_run(
                GITLEAKS_IMAGE, repo, "rev-parse", "--verify", "HEAD", entrypoint="git"
            ),
        ),
        Gate(
            "gitleaks history",
            docker_run(GITLEAKS_IMAGE, repo, "git", "--redact", "--no-banner", "/repo"),
        ),
        Gate(
            "gitleaks staged",
            docker_run(
                GITLEAKS_IMAGE,
                repo,
                "git",
                "--pre-commit",
                "--staged",
                "--redact",
                "--no-banner",
                "/repo",
            ),
        ),
    ]
    if has_workflows:
        gates.append(Gate("actionlint", docker_run(ACTIONLINT_IMAGE, repo)))
        gates.append(Gate("zizmor", ("zizmor", "--offline", ".github/workflows")))
    gates += [
        Gate("ruff format", ("ruff", "format", "--check", ".")),
        Gate("ruff check", ("ruff", "check", ".")),
        Gate("mypy", ("mypy",)),
        Gate("pytest unit", ("pytest", "tests/unit", "-q")),
    ]
    if trailer_base is not None:
        gates.append(
            Gate(
                "trailers",
                (sys.executable, "-m", "tools.trailers", "--base", trailer_base),
            )
        )
    return gates


def run_gates(gates: Sequence[Gate], runner: Runner) -> int:
    """Run each gate in order; stop at the first failure and return its exit code."""
    for gate in gates:
        start = time.monotonic()
        code = runner(gate.argv)
        if code != 0:
            print(f"FAIL {gate.name}", flush=True)
            return code
        print(f"PASS {gate.name} ({time.monotonic() - start:.1f}s)", flush=True)
    return 0


def _default_trailer_base() -> str | None:
    """main, when a local main branch exists and HEAD is not on it."""
    has_main = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "refs/heads/main"],
        capture_output=True,
        check=False,
    )
    head = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return (
        "main" if has_main.returncode == 0 and head.stdout.strip() != "main" else None
    )


def main(argv: Sequence[str] | None = None, *, runner: Runner | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.gates",
        description="Run every quality gate in order, stopping at the first failure.",
    )
    parser.add_argument(
        "--trailer-base",
        help="check commit trailers after this revision; default $TRAILER_BASE, "
        "else main when on another branch",
    )
    args = parser.parse_args(argv)
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    repo = Path(top.stdout.strip())
    workflows = repo / ".github" / "workflows"
    has_workflows = any(workflows.glob("*.yml")) or any(workflows.glob("*.yaml"))
    trailer_base = (
        args.trailer_base or os.environ.get("TRAILER_BASE") or _default_trailer_base()
    )
    if not has_workflows:
        print("SKIP actionlint: no workflows", flush=True)
        print("SKIP zizmor: no workflows", flush=True)
    if trailer_base is None:
        print("SKIP trailers: no base", flush=True)
    if runner is None:

        def runner(command: Sequence[str]) -> int:
            return subprocess.run(command, cwd=repo, check=False).returncode

    return run_gates(
        plan_gates(repo, has_workflows=has_workflows, trailer_base=trailer_base), runner
    )


if __name__ == "__main__":
    raise SystemExit(main())
