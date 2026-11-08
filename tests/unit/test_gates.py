# Author: Nicola Antonello
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from tools.gates import (
    ACTIONLINT_IMAGE,
    GITLEAKS_IMAGE,
    Gate,
    docker_run,
    main,
    plan_gates,
    run_gates,
)


def test_gates_run_in_the_documented_order(tmp_path: Path) -> None:
    names = [
        g.name for g in plan_gates(tmp_path, has_workflows=True, trailer_base="main")
    ]
    assert names == [
        "gitleaks reads git",
        "gitleaks history",
        "gitleaks staged",
        "actionlint",
        "zizmor",
        "ruff format",
        "ruff check",
        "mypy",
        "pytest unit",
        "trailers",
    ]


def test_workflow_gates_need_workflows(tmp_path: Path) -> None:
    names = [
        g.name for g in plan_gates(tmp_path, has_workflows=False, trailer_base="main")
    ]
    assert "actionlint" not in names and "zizmor" not in names


def test_trailer_gate_needs_a_base(tmp_path: Path) -> None:
    names = [
        g.name for g in plan_gates(tmp_path, has_workflows=True, trailer_base=None)
    ]
    assert "trailers" not in names


def test_docker_gates_use_the_pinned_digests(tmp_path: Path) -> None:
    gates = {
        g.name: g.argv
        for g in plan_gates(tmp_path, has_workflows=True, trailer_base=None)
    }
    assert (
        GITLEAKS_IMAGE in gates["gitleaks history"]
        and GITLEAKS_IMAGE in gates["gitleaks staged"]
    )
    assert ACTIONLINT_IMAGE in gates["actionlint"]
    assert "@sha256:" in GITLEAKS_IMAGE and "@sha256:" in ACTIONLINT_IMAGE


def test_gitleaks_gates_first_check_that_git_can_read_the_repository(
    tmp_path: Path,
) -> None:
    # In a linked worktree, git in the container cannot open the repository, and
    # gitleaks then scans nothing yet exits 0. The run must fail before that.
    gates = plan_gates(tmp_path, has_workflows=False, trailer_base=None)
    first = gates[0].argv
    assert gates[0].name == "gitleaks reads git"
    assert first[first.index("--entrypoint") + 1] == "git"
    assert first[first.index(GITLEAKS_IMAGE) + 1 :] == ("rev-parse", "--verify", "HEAD")
    assert [g.name for g in gates[1:3]] == ["gitleaks history", "gitleaks staged"]


def test_gates_pin_their_exact_commands(tmp_path: Path) -> None:
    # The arguments carry the safety: --redact keeps a found secret out of public CI
    # logs, --staged scans what is about to be committed, readonly protects the files.
    repo = tmp_path / "AI Engineering"
    docker = (
        "docker",
        "run",
        "--rm",
        "--mount",
        f"type=bind,source={repo},target=/repo,readonly",
        "--workdir",
        "/repo",
        "-e",
        "GIT_CONFIG_COUNT=1",
        "-e",
        "GIT_CONFIG_KEY_0=safe.directory",
        "-e",
        "GIT_CONFIG_VALUE_0=/repo",
    )
    gitleaks_args = ("git", "--redact", "--no-banner", "/repo")
    expected = [
        (
            "gitleaks reads git",
            (
                *docker,
                "--entrypoint",
                "git",
                GITLEAKS_IMAGE,
                "rev-parse",
                "--verify",
                "HEAD",
            ),
        ),
        ("gitleaks history", (*docker, GITLEAKS_IMAGE, *gitleaks_args)),
        (
            "gitleaks staged",
            (
                *docker,
                GITLEAKS_IMAGE,
                "git",
                "--pre-commit",
                "--staged",
                "--redact",
                "--no-banner",
                "/repo",
            ),
        ),
        ("actionlint", (*docker, ACTIONLINT_IMAGE)),
        ("zizmor", ("zizmor", "--offline", ".github/workflows")),
        ("ruff format", ("ruff", "format", "--check", ".")),
        ("ruff check", ("ruff", "check", ".")),
        ("mypy", ("mypy",)),
        ("pytest unit", ("pytest", "tests/unit", "-q")),
        ("trailers", (sys.executable, "-m", "tools.trailers", "--base", "main")),
    ]
    gates = plan_gates(repo, has_workflows=True, trailer_base="main")
    assert [(g.name, g.argv) for g in gates] == expected


def test_repository_is_mounted_read_only_as_one_argument(tmp_path: Path) -> None:
    repo = tmp_path / "AI Engineering"
    argv = docker_run(GITLEAKS_IMAGE, repo, "git")
    assert argv.count("--mount") == 1
    assert (
        argv[argv.index("--mount") + 1]
        == f"type=bind,source={repo},target=/repo,readonly"
    )


def test_run_stops_at_the_first_failure() -> None:
    calls: list[Sequence[str]] = []
    codes = iter([0, 3, 0])

    def runner(argv: Sequence[str]) -> int:
        calls.append(argv)
        return next(codes)

    gates = [Gate("a", ("a",)), Gate("b", ("b",)), Gate("c", ("c",))]
    assert run_gates(gates, runner) == 3
    assert calls == [("a",), ("b",)]


def test_run_returns_zero_when_every_gate_passes() -> None:
    assert run_gates([Gate("a", ("a",)), Gate("b", ("b",))], lambda argv: 0) == 0


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated repository on main with one commit, as the working directory."""
    empty_config = tmp_path / "empty.gitconfig"
    empty_config.write_bytes(b"")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("TRAILER_BASE", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    git = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com"]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run(
        [*git, "commit", "-q", "--allow-empty", "-m", "chore: start"], check=True
    )
    return repo


def recording_runner() -> tuple[list[tuple[str, ...]], Callable[[Sequence[str]], int]]:
    """A runner that records each gate's command instead of running it."""
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str]) -> int:
        calls.append(tuple(argv))
        return 0

    return calls, runner


def test_main_announces_every_gate_it_skips(
    git_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls, runner = recording_runner()
    assert main([], runner=runner) == 0
    out = capsys.readouterr().out
    assert "SKIP actionlint: no workflows" in out
    assert "SKIP zizmor: no workflows" in out
    assert "SKIP trailers: no base" in out
    assert not any(
        ACTIONLINT_IMAGE in argv or "tools.trailers" in argv for argv in calls
    )


def test_main_runs_the_workflow_gates_when_a_workflow_exists(git_repo: Path) -> None:
    workflows = git_repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yaml").write_bytes(b"name: ci\n")
    calls, runner = recording_runner()
    main([], runner=runner)
    assert any(ACTIONLINT_IMAGE in argv for argv in calls)
    assert ("zizmor", "--offline", ".github/workflows") in calls


def test_main_reads_the_trailer_base_from_the_environment(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRAILER_BASE", "abc1234")
    calls, runner = recording_runner()
    main([], runner=runner)
    assert calls[-1][-2:] == ("--base", "abc1234")


def test_main_prefers_the_option_to_the_environment(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRAILER_BASE", "abc1234")
    calls, runner = recording_runner()
    main(["--trailer-base", "def5678"], runner=runner)
    assert calls[-1][-2:] == ("--base", "def5678")


def test_main_checks_trailers_against_main_from_another_branch(git_repo: Path) -> None:
    subprocess.run(["git", "switch", "-q", "-c", "feature"], check=True)
    calls, runner = recording_runner()
    main([], runner=runner)
    assert calls[-1][-2:] == ("--base", "main")
