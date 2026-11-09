# Author: Nicola Antonello
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from tools.trailers import email_problems, main, message_problems


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[str], str]:
    """A throwaway repository that ignores the developer's git settings.

    Returns a helper that makes an empty commit with a message and returns its SHA.
    """
    empty_config = tmp_path / "empty.gitconfig"
    empty_config.write_bytes(b"")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "main"], check=True)

    def commit(message: str) -> str:
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=1+test@users.noreply.github.com",
                "commit",
                "--allow-empty",
                "-q",
                "-F",
                "-",
            ],
            input=message,
            encoding="utf-8",
            check=True,
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        return head.stdout.strip()

    return commit


def test_refs_trailer_is_allowed() -> None:
    assert message_problems("feat: add x\n\nWhy it matters.\n\nRefs: ADR-0005\n") == []


def test_any_other_trailer_is_rejected() -> None:
    message = (
        "fix: y\n\nSigned-off-by: A <a@example.com>\nReviewed-by: B <b@example.com>\n"
        "Refs: ADR-0001\n"
    )
    assert message_problems(message) == [
        'trailer "Signed-off-by" is not allowed',
        'trailer "Reviewed-by" is not allowed',
    ]


def test_trailer_keys_are_case_sensitive() -> None:
    assert message_problems("fix: y\n\nrefs: ADR-0002\n") == [
        'trailer "refs" is not allowed'
    ]


def test_co_author_line_is_rejected_even_inside_prose() -> None:
    message = (
        "feat: z\n\nPaired on this.\nCo-authored-by: Someone <someone@example.com>\n"
        "Thanks for the review.\n"
    )
    assert message_problems(message) == ["co-author line"]


def test_generated_with_line_is_rejected() -> None:
    message = "docs: a\n\n🤖 Generated with [Some Tool](https://example.com)\n"
    assert message_problems(message) == ["generated-with line"]


def test_generated_with_inside_a_sentence_is_allowed() -> None:
    assert (
        message_problems("docs: b\n\nThe table is generated with one command.\n") == []
    )


def test_body_text_that_looks_like_a_trailer_is_allowed() -> None:
    assert (
        message_problems("docs: c\n\nNote: this is prose.\n\nMore prose follows.\n")
        == []
    )


def test_trailer_after_a_dashed_line_is_rejected() -> None:
    # Dependabot's shape: a "---" block of metadata, then a sign-off. Git reads the whole
    # message for a commit's trailers, so the check must not stop at the dashes.
    message = (
        "build(deps): bump x from 1 to 2\n\nBumps x from 1 to 2.\n\n---\n"
        "updated-dependencies:\n- dependency-name: x\n...\n\n"
        "Signed-off-by: dependabot[bot] <support@github.com>\n"
    )
    assert message_problems(message) == ['trailer "Signed-off-by" is not allowed']


def test_github_no_reply_emails_are_allowed() -> None:
    assert email_problems("1+me@users.noreply.github.com", "noreply@github.com") == []


def test_personal_author_email_is_rejected() -> None:
    problems = email_problems("me@example.com", "noreply@github.com")
    assert problems == ["author email is not a GitHub no-reply address"]


def test_personal_committer_email_is_rejected() -> None:
    problems = email_problems("1+me@users.noreply.github.com", "me@example.com")
    assert problems == ["committer email is not a GitHub no-reply address"]


def test_lookalike_no_reply_domains_are_rejected() -> None:
    author = "me@users.noreply.github.com.example.com"
    committer = "me@evilusers.noreply.github.com"
    assert email_problems(author, committer) == [
        "author email is not a GitHub no-reply address",
        "committer email is not a GitHub no-reply address",
    ]


def test_main_reports_only_offending_commits(
    repo: Callable[[str], str], capsys: pytest.CaptureFixture[str]
) -> None:
    clean = repo("chore: clean\n")
    repo("feat: tainted\n\nCo-authored-by: X <x@example.com>\n")
    assert main(["--base", clean]) == 1
    out = capsys.readouterr().out
    assert "feat: tainted: co-author line" in out and "chore: clean" not in out


def test_main_with_zero_base_checks_every_commit(repo: Callable[[str], str]) -> None:
    repo("feat: tainted\n\nSigned-off-by: X <x@example.com>\n")
    assert main(["--base", "0" * 40]) == 1


def test_main_with_unknown_base_exits_2(
    repo: Callable[[str], str], capsys: pytest.CaptureFixture[str]
) -> None:
    repo("chore: clean\n")
    assert main(["--base", "deadbeef" * 5]) == 2
    assert "deadbeef" in capsys.readouterr().out


def test_main_passes_on_clean_history(repo: Callable[[str], str]) -> None:
    base = repo("chore: one\n")
    repo("docs: two\n\nRefs: ADR-0001\n")
    assert main(["--base", base]) == 0


def test_main_says_how_many_commits_it_checked(
    repo: Callable[[str], str], capsys: pytest.CaptureFixture[str]
) -> None:
    base = repo("chore: one\n")
    repo("docs: two\n")
    repo("docs: three\n")
    assert main(["--base", base]) == 0
    assert "2 commit(s) checked" in capsys.readouterr().out


def test_main_reports_a_personal_email_without_printing_it(
    repo: Callable[[str], str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # CI logs are public, so the problem names the role and never the address.
    base = repo("chore: one\n")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "me@example.com")
    repo("feat: two\n")
    assert main(["--base", base]) == 1
    out = capsys.readouterr().out
    assert "feat: two: author email is not a GitHub no-reply address" in out
    assert "me@example.com" not in out
