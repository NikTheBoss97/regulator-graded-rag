# Author: Nicola Antonello
import http.client
import json
import threading
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import pytest

from regulator_graded_rag.drafts import Draft, load_drafts, write_drafts
from regulator_graded_rag.review_page import (
    Decision,
    _Review,
    allowed_host,
    append_decision,
    decide,
    digest,
    main,
    pending,
    render,
    rewrite_draft,
)

DRAFT = Draft(
    id="99-0001-Q1",
    letter="99-0001",
    number=1,
    numbered=True,
    question="Is it the case that § 171.1 applies to a person who marks a packaging?",
    rewritten=True,
    answer="yes",
    evidence=("171.1(a)",),
    outside=(),
    type="lookup",
    letter_date="2020-03-02",
    date_source="letter",
    source="https://web.archive.org/web/20260101000000/https://www.phmsa.dot.gov/99-0001",
    split="dev",
    drift={"171.1(a)": "unchanged"},
    kept=True,
    flags=(),
)
LATER = replace(
    DRAFT,
    id="99-0002-Q1",
    letter="99-0002",
    letter_date="2021-04-01",
    question="Is it the case that § 172.101 lists the material?",
    evidence=("172.101",),
    drift={"172.101": "unchanged"},
)
NOW = datetime(2026, 11, 20, 10, tzinfo=UTC)
NO_TABLES: frozenset[str] = frozenset()
UNITS = frozenset({"171.1", "172.101"})
BLANK = replace(DRAFT, question="")


@pytest.mark.parametrize(
    "form", [{"action": "approve"}, {"token": "u", "action": "approve"}]
)
def test_a_post_without_the_token_is_refused(form: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="token"):
        decide(DRAFT, form, "t", NOW, tables=NO_TABLES, units=UNITS)


def test_an_edit_that_breaks_the_gold_format_is_refused_with_its_field() -> None:
    form = {"token": "t", "action": "edit", "answer": "maybe"}
    with pytest.raises(ValueError, match=": answer:"):
        decide(DRAFT, form, "t", NOW, tables=NO_TABLES, units=UNITS)


def test_an_approval_records_the_id_the_action_and_the_time() -> None:
    form = {"token": "t", "action": "approve"}
    decision = decide(DRAFT, form, "t", NOW, tables=NO_TABLES, units=UNITS)
    assert decision == Decision(
        "99-0001-Q1", "approve", {}, "2026-11-20T10:00:00+00:00", digest(DRAFT)
    )


def test_an_edit_records_only_the_fields_it_changes() -> None:
    form = {
        "token": "t",
        "action": "edit",
        "question": "  Does § 171.1 apply\r\n to a person who marks a packaging?",
        "answer": "yes",
        "evidence": "171.1(a)\r\n",
        "letter_date": "2020-03-02",
    }
    decision = decide(DRAFT, form, "t", NOW, tables=NO_TABLES, units=UNITS)
    assert decision.action == "edit"
    assert decision.fields == {
        "question": "Does § 171.1 apply to a person who marks a packaging?"
    }


@pytest.mark.parametrize(
    ("evidence", "tables", "kind"),
    [
        ("171.1(a)\n172.101", NO_TABLES, "multi_passage"),
        ("171.1(a)\n172.101", frozenset({"172.101"}), "table"),
        ("171.1(b)", NO_TABLES, None),
    ],
)
def test_edited_evidence_brings_the_type_it_gives(
    evidence: str, tables: frozenset[str], kind: str | None
) -> None:
    form = {"token": "t", "action": "edit", "evidence": evidence}
    decision = decide(DRAFT, form, "t", NOW, tables=tables, units=UNITS)
    assert decision.fields["evidence"] == evidence.split("\n")
    assert decision.fields.get("type") == kind


@pytest.mark.parametrize(
    ("draft", "form"),
    [
        (DRAFT, {"action": "edit", "evidence": "171.1(a)\n107.105\n390.5"}),
        (replace(DRAFT, evidence=("390.5",)), {"action": "approve"}),
    ],
)
def test_a_label_outside_the_corpus_is_refused(
    draft: Draft, form: dict[str, str]
) -> None:
    # Other parts' rules are not evidence: no run can retrieve them (ADR-0021).
    with pytest.raises(ValueError, match=r"evidence: .*390\.5.* not in the corpus"):
        decide(draft, form | {"token": "t"}, "t", NOW, tables=NO_TABLES, units=UNITS)


def test_an_unanswerable_items_evidence_may_say_what_was_searched() -> None:
    draft = replace(
        DRAFT,
        type="unanswerable",
        answer="",
        evidence=("PHMSA's answer cites only 107.105, outside Parts 171-180",),
        drift={},
    )
    form = {"token": "t", "action": "edit", "evidence": "Parts 171-180 for 107.105"}
    decision = decide(draft, form, "t", NOW, tables=NO_TABLES, units=UNITS)
    assert decision.fields == {"evidence": ["Parts 171-180 for 107.105"]}


def test_approving_an_edited_form_is_refused() -> None:
    form = {"token": "t", "action": "approve", "letter_date": "2020-03-03"}
    with pytest.raises(ValueError, match="Save edits"):
        decide(DRAFT, form, "t", NOW, tables=NO_TABLES, units=UNITS)


def test_a_rejection_needs_no_valid_item() -> None:
    form = {"token": "t", "action": "reject", "answer": "maybe"}
    decision = decide(DRAFT, form, "t", NOW, tables=NO_TABLES, units=UNITS)
    assert (decision.action, decision.fields) == ("reject", {})


@pytest.mark.parametrize(
    ("form", "kept"),
    [
        ({"action": "approve"}, DRAFT),
        ({"action": "edit", "letter_date": "2020-03-03"}, DRAFT),
        ({"action": "edit", "question": "Does § 171.1 apply to a carrier?"}, BLANK),
        ({"action": "reject"}, BLANK),
    ],
)
def test_only_an_approved_question_stays_in_the_drafts_file(
    form: dict[str, str], kept: Draft
) -> None:
    # The owner's ruling of 2026-11-16: a rejected draft, or one whose question the
    # owner rewrote, is kept without its question, and the decision says so.
    decision = decide(
        DRAFT, form | {"token": "t"}, "t", NOW, tables=NO_TABLES, units=UNITS
    )
    assert decision.digest == digest(kept)


def test_rewriting_a_draft_changes_its_line_alone(tmp_path: Path) -> None:
    path = tmp_path / "drafts.jsonl"
    write_drafts(path, [DRAFT, LATER])
    before = path.read_bytes().split(b"\n")
    rewrite_draft(path, BLANK)
    after = path.read_bytes().split(b"\n")
    assert load_drafts(path) == [BLANK, LATER]
    assert after[1:] == before[1:] and after[0] != before[0]
    assert not path.with_name("drafts.jsonl.part").exists()


def test_the_page_escapes_letter_and_draft_text() -> None:
    draft = replace(DRAFT, question="Is it <script>alert(1)</script>?")
    page = render(draft, "Dear <script>x</script>,\nThe answer is yes.", "t")
    assert "&lt;script&gt;" in page
    assert "<script" not in page


def test_the_page_loads_nothing_from_elsewhere() -> None:
    page = render(DRAFT, "The answer is yes.", "t")
    for tag in ("<link", "<img", "<iframe", "src="):
        assert tag not in page
    assert 'name="token" value="t"' in page


def test_enter_in_a_field_submits_nothing() -> None:
    # A browser submits a form on Enter through its first submit button; a disabled
    # one submits nothing, so Enter in the date field approves no draft.
    page = render(DRAFT, "The answer is yes.", "t")
    first = page[page.index("<button") :].split(">", 1)[0]
    assert "disabled" in first
    assert page.index("<button") < page.index('value="approve"')


@pytest.mark.parametrize(
    ("host", "allowed"),
    [
        ("127.0.0.1:8765", True),
        ("localhost:8765", True),
        ("evil.example:8765", False),
        ("127.0.0.1:9999", False),
        ("", False),
    ],
)
def test_only_local_hosts_are_served(host: str, allowed: bool) -> None:
    assert allowed_host(host, 8765) is allowed


def test_a_decision_is_appended_as_one_sorted_line(tmp_path: Path) -> None:
    path = tmp_path / "eval" / "decisions.jsonl"
    first = Decision(
        "99-0001-Q1", "edit", {"answer": "no"}, "2026-11-20T10:00:00+00:00", "d"
    )
    append_decision(path, first)
    append_decision(path, replace(first, action="reject", fields={}))
    lines = path.read_bytes().split(b"\n")
    assert lines[-1] == b"" and len(lines) == 3
    assert json.loads(lines[0]) == {
        "action": "edit",
        "at": "2026-11-20T10:00:00+00:00",
        "digest": "d",
        "fields": {"answer": "no"},
        "id": "99-0001-Q1",
    }
    assert list(json.loads(lines[0])) == sorted(json.loads(lines[0]))


def test_a_draft_changed_since_its_decision_is_checked_again(tmp_path: Path) -> None:
    older = replace(DRAFT, id="98-0002-Q1", letter="98-0002", letter_date="2018-05-01")
    changed = replace(
        DRAFT, id="97-0003-Q1", letter="97-0003", letter_date="2019-01-01"
    )
    unkept = replace(DRAFT, id="96-0004-Q1", kept=False)
    path = tmp_path / "decisions.jsonl"
    append_decision(path, Decision(DRAFT.id, "approve", {}, "x", digest(DRAFT)))
    append_decision(path, Decision(changed.id, "approve", {}, "x", "an older draft's"))
    assert pending([DRAFT, changed, unkept, older], path) == [older, changed]
    assert pending([DRAFT], tmp_path / "none.jsonl") == [DRAFT]


@pytest.fixture
def page(tmp_path: Path) -> Iterator[tuple[_Review, Path, Path]]:
    """The page's real server on 127.0.0.1, on a port the system picks."""
    drafts = tmp_path / "drafts.jsonl"
    write_drafts(drafts, [DRAFT, LATER])
    decisions = tmp_path / "decisions.jsonl"
    server = _Review(
        0,
        "t",
        [DRAFT, LATER],
        drafts,
        decisions,
        NO_TABLES,
        UNITS,
        lambda draft: "The answer is yes.",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, drafts, decisions
    server.shutdown()
    server.server_close()


def ask(
    server: _Review,
    method: str,
    path: str = "/",
    form: dict[str, str] | None = None,
    host: str = "",
) -> tuple[int, str]:
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    headers = {"Host": host or f"127.0.0.1:{server.port}"}
    body = None if form is None else urlencode(form)
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    text = response.read().decode("utf-8")
    connection.close()
    return response.status, text


def test_a_request_from_another_host_changes_nothing(
    page: tuple[_Review, Path, Path],
) -> None:
    server, drafts, decisions = page
    before = drafts.read_bytes()
    host = f"evil.example:{server.port}"
    assert ask(server, "GET", "/?token=t", host=host)[0] == 403
    form = {"token": "t", "id": DRAFT.id, "action": "reject"}
    status, text = ask(server, "POST", form=form, host=host)
    assert status == 403 and DRAFT.question not in text
    assert not decisions.exists() and drafts.read_bytes() == before


def test_a_request_without_the_token_reads_and_changes_nothing(
    page: tuple[_Review, Path, Path],
) -> None:
    server, drafts, decisions = page
    before = drafts.read_bytes()
    status, text = ask(server, "GET", "/")
    assert status == 404 and DRAFT.question not in text
    form = {"id": DRAFT.id, "action": "reject"}
    assert ask(server, "POST", form=form)[0] == 404
    assert ask(server, "POST", form=form | {"token": "u"})[0] == 404
    assert not decisions.exists() and drafts.read_bytes() == before


def test_a_decision_is_saved_and_the_next_draft_served(
    page: tuple[_Review, Path, Path],
) -> None:
    server, _, decisions = page
    status, text = ask(server, "GET", "/?token=t")
    assert status == 200 and DRAFT.id in text
    form = {"token": "t", "id": DRAFT.id, "action": "approve"}
    assert ask(server, "POST", form=form)[0] == 303
    [line] = decisions.read_text(encoding="utf-8").splitlines()
    assert json.loads(line)["digest"] == digest(DRAFT)
    status, text = ask(server, "GET", "/?token=t")
    assert status == 200 and LATER.id in text and DRAFT.id not in text


def test_a_rejection_takes_the_question_out_of_the_drafts_file(
    page: tuple[_Review, Path, Path],
) -> None:
    server, drafts, decisions = page
    form = {"token": "t", "id": DRAFT.id, "action": "reject"}
    assert ask(server, "POST", form=form)[0] == 303
    assert load_drafts(drafts) == [BLANK, LATER]
    assert DRAFT.question.encode() not in drafts.read_bytes()
    assert pending(load_drafts(drafts), decisions) == [LATER]


def test_the_page_waits_for_the_unanswerable_split(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    drafts = tmp_path / "drafts.jsonl"
    write_drafts(drafts, [DRAFT])
    code = main(
        [
            "--split",
            "dev",
            "--drafts",
            str(drafts),
            "--decisions",
            str(tmp_path / "decisions.jsonl"),
            "--unanswerable",
            str(tmp_path / "unanswerable.jsonl"),
        ]
    )
    assert code == 1
    assert "unanswerable" in capsys.readouterr().out
    assert not (tmp_path / "decisions.jsonl").exists()


def test_held_out_review_needs_the_owners_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # From an empty folder, so the refusal comes before any file is read.
    monkeypatch.chdir(tmp_path)
    assert main(["--split", "heldout"]) == 2
