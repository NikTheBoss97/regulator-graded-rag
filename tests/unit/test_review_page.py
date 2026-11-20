# Author: Nicola Antonello
import http.client
import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlencode

import pytest

from regulator_graded_rag.audit import Audit
from regulator_graded_rag.drafts import Draft, load_drafts, write_drafts
from regulator_graded_rag.letter_page import LetterPage
from regulator_graded_rag.review_page import (
    Decision,
    _Review,
    allowed_host,
    append_decision,
    current_actions,
    decide,
    digest,
    item_record,
    main,
    pending,
    render,
    rewrite_draft,
    to_check,
)
from tests.unit.test_checks import letter

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
THIRD = replace(
    DRAFT,
    id="99-0003-Q1",
    letter="99-0003",
    letter_date="2022-01-01",
    question="Is it the case that § 171.1 covers a packaging's marking?",
)
NO_AUDIT = Audit("dev", "1", "2026-11-21", (), ())
ANSWER = "The answer is yes. A person who marks a packaging is subject to § 171.1(a)."
FACTS = "You state that Jane Doe ships widgets by road."


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
    page = render(draft, letter("Dear <script>x</script>,"), "t")
    assert "&lt;script&gt;" in page
    assert "<script" not in page


def test_the_page_loads_nothing_from_elsewhere() -> None:
    page = render(DRAFT, letter(f"Q1. {DRAFT.question}", f"A1. {ANSWER}"), "t")
    for tag in ("<link", "<img", "<iframe", "src="):
        assert tag not in page
    assert 'name="token" value="t"' in page


def test_enter_in_a_field_submits_nothing() -> None:
    # A browser submits a form on Enter through its first submit button; a disabled
    # one submits nothing, so Enter in the date field approves no draft.
    page = render(DRAFT, None, "t")
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


Serve = Callable[..., tuple[_Review, Path, Path]]


@pytest.fixture
def serve(tmp_path: Path) -> Iterator[Serve]:
    """A factory for the page's real server on 127.0.0.1, on a port the system picks."""
    started: list[_Review] = []

    def start(
        drafts: list[Draft],
        audit: Audit = NO_AUDIT,
        letter_of: Callable[[Draft], LetterPage | None] = lambda draft: None,
    ) -> tuple[_Review, Path, Path]:
        path = tmp_path / "drafts.jsonl"
        write_drafts(path, drafts)
        decisions = tmp_path / "decisions.jsonl"
        server = _Review(
            0,
            "t",
            drafts,
            path,
            decisions,
            NO_TABLES,
            sorted(UNITS),
            letter_of,
            audit,
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        started.append(server)
        return server, path, decisions

    yield start
    for server in started:
        server.shutdown()
        server.server_close()


@pytest.fixture
def page(serve: Serve) -> tuple[_Review, Path, Path]:
    return serve([DRAFT, LATER])


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


def contextual() -> LetterPage:
    return LetterPage(
        "article",
        None,
        "",
        "Jane Doe",
        (
            "June 1, 2020",
            "Dear Ms. Doe:",
            f"This letter is in response to your email. {FACTS}",
            f"Q1. {DRAFT.question}",
            f"A1. {ANSWER}",
        ),
    )


COLON = replace(DRAFT, question="Is it the case that the following apply:")


def test_the_page_asks_each_reason_beside_its_sentence() -> None:
    draft = replace(DRAFT, question="Is it the case that this applies?")
    text = render(draft, letter(f"Q1. {draft.question}", f"A1. {ANSWER}"), "t")
    assert "points at something it does not say" in text
    assert "<i>this</i>" in text
    assert "Add the next paragraph after the question" not in text
    colon = render(COLON, letter(f"Q1. {COLON.question}", f"A1. {ANSWER}"), "t")
    assert 'value="after"' in colon
    assert "Add the next paragraph after the question" in colon


def test_the_page_ticks_what_code_confirmed() -> None:
    wrong = replace(DRAFT, evidence=("172.101",))
    units = sorted(UNITS)
    page_text = letter(f"Q1. {DRAFT.question}", f"A1. {ANSWER}")
    text = render(wrong, page_text, "t", units=units)
    assert '<li class="ok">✓ The question holds no name</li>' in text
    assert '<li class="bad">✗ The answer cites 172.101</li>' in text


def test_the_page_puts_the_question_and_its_answer_first_and_folds_the_letter() -> None:
    other = "A paragraph that belongs to neither the question nor the answer."
    page_text = letter(other, f"Q1. {DRAFT.question}", f"A1. {ANSWER}")
    text = render(DRAFT, page_text, "t")
    fold = text.index("<details><summary>The whole letter</summary>")
    start = text.index('class="letter"')
    assert start < text.index(DRAFT.question, start) < fold
    assert text.index(ANSWER, start) < fold
    assert text.index("This letter is in response", start) < fold
    assert other not in text[:fold]
    assert other in text[fold:]


def test_decisions_have_access_keys() -> None:
    text = render(DRAFT, None, "t")
    for value, key in (("approve", "a"), ("edit", "s"), ("reject", "r")):
        assert f'<button name="action" value="{value}" accesskey="{key}">' in text


def test_the_page_states_the_bar() -> None:
    text = render(DRAFT, None, "t")
    assert "<details><summary>The bar</summary>" in text
    assert "Approve unless the verdict needs something nobody can see" in text
    assert "only to drop a citation that is not in the answer." in text


def test_a_context_button_fills_the_question_and_saves_nothing(serve: Serve) -> None:
    server, drafts, decisions = serve([DRAFT], letter_of=lambda draft: contextual())
    before = drafts.read_bytes()
    form = {"token": "t", "id": DRAFT.id, "action": "before", "question": "Typed?"}
    status, text = ask(server, "POST", form=form)
    assert status == 200
    assert "ships widgets by road. Typed?</textarea>" in text
    assert not decisions.exists() and drafts.read_bytes() == before


def test_a_context_button_adds_the_next_paragraph_after_the_question(
    serve: Serve,
) -> None:
    page_text = letter(
        f"Q1. {COLON.question}", "Both of them, in a drum.", f"A1. {ANSWER}"
    )
    server, _, _ = serve([COLON], letter_of=lambda draft: page_text)
    form = {"token": "t", "id": COLON.id, "action": "after", "question": "Typed:"}
    status, text = ask(server, "POST", form=form)
    assert status == 200
    assert "Typed: Both of them, in a drum.</textarea>" in text


def test_context_through_a_button_is_scrubbed(serve: Serve) -> None:
    server, _, _ = serve([DRAFT], letter_of=lambda draft: contextual())
    form = {"token": "t", "id": DRAFT.id, "action": "before", "question": "Q?"}
    status, text = ask(server, "POST", form=form)
    field = text.split('name="question" rows="5">')[1].split("</textarea>")[0]
    assert status == 200 and "ships widgets" in field and "Jane Doe" not in field


def test_a_context_button_needs_the_token_and_the_host(serve: Serve) -> None:
    server, _, _ = serve([DRAFT], letter_of=lambda draft: contextual())
    form = {"id": DRAFT.id, "action": "before", "question": "Q?"}
    assert ask(server, "POST", form=form | {"token": "u"})[0] == 404
    bad = ask(server, "POST", form=form | {"token": "t"}, host="evil.example:1")
    assert bad[0] == 403


def test_to_check_holds_the_drafts_with_a_reason_and_the_sample() -> None:
    pool = (DRAFT.id, LATER.id, THIRD.id)
    audit = Audit("dev", "1", "2026-11-21", pool, (DRAFT.id, THIRD.id))
    reasoned = replace(
        DRAFT, id="99-0004-Q1", letter="99-0004", letter_date="2023-01-01"
    )
    unkept = replace(reasoned, id="99-0005-Q1", kept=False)
    drafts = [reasoned, THIRD, unkept, LATER, DRAFT]
    assert to_check(drafts, {}, audit) == [DRAFT, THIRD, reasoned]
    assert to_check(drafts, {DRAFT.id: "approve"}, audit) == [THIRD, reasoned]
    assert to_check(drafts, {THIRD.id: "reject"}, audit) == [DRAFT, reasoned]


def test_two_changes_send_the_whole_pool_to_the_owner() -> None:
    pool = (DRAFT.id, LATER.id, THIRD.id)
    audit = Audit("dev", "1", "2026-11-21", pool, (DRAFT.id, LATER.id))
    drafts = [DRAFT, LATER, THIRD]
    one = {DRAFT.id: "edit"}
    assert to_check(drafts, one, audit) == [LATER]
    two = one | {LATER.id: "reject"}
    assert to_check(drafts, two, audit) == [THIRD]


def test_the_page_serves_the_pool_after_two_changes(serve: Serve) -> None:
    pool = (DRAFT.id, LATER.id, THIRD.id)
    audit = Audit("dev", "1", "2026-11-21", pool, (DRAFT.id, LATER.id))
    server, _, _ = serve([DRAFT, LATER, THIRD], audit)
    edit = {"token": "t", "action": "edit"}
    assert THIRD.id not in ask(server, "GET", "/?token=t")[1]
    first = edit | {"id": DRAFT.id, "letter_date": "2020-03-03"}
    assert ask(server, "POST", form=first)[0] == 303
    text = ask(server, "GET", "/?token=t")[1]
    assert LATER.id in text and THIRD.id not in text
    second = edit | {"id": LATER.id, "letter_date": "2021-04-02"}
    assert ask(server, "POST", form=second)[0] == 303
    assert THIRD.id in ask(server, "GET", "/?token=t")[1]


def test_a_read_is_not_an_owner_decision(tmp_path: Path) -> None:
    audit = Audit("dev", "1", "2026-11-21", (DRAFT.id, LATER.id), (DRAFT.id,))
    path = tmp_path / "decisions.jsonl"
    line = {"id": DRAFT.id, "action": "read", "fields": {}, "at": "x"}
    path.write_text(
        json.dumps(line | {"digest": digest(DRAFT)}) + "\n", encoding="utf-8"
    )
    actions = current_actions([DRAFT, LATER], path)
    assert actions == {DRAFT.id: "read"}
    assert to_check([DRAFT, LATER], actions, audit) == [DRAFT]


def test_current_actions_counts_only_the_draft_as_it_now_reads(
    tmp_path: Path,
) -> None:
    path = tmp_path / "decisions.jsonl"
    append_decision(path, Decision(DRAFT.id, "approve", {}, "x", digest(DRAFT)))
    append_decision(path, Decision(DRAFT.id, "reject", {}, "x", digest(BLANK)))
    append_decision(path, Decision(LATER.id, "edit", {}, "x", "an older draft's"))
    assert current_actions([DRAFT, LATER], path) == {}
    assert current_actions([BLANK, LATER], path) == {DRAFT.id: "reject"}
    assert current_actions([DRAFT], tmp_path / "none.jsonl") == {}


def test_the_page_needs_the_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "unanswerable.jsonl").write_text("", encoding="utf-8")
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
    out = capsys.readouterr().out
    assert "the audit is not drawn" in out
    assert "regulator_graded_rag.audit --split dev --draw" in out


def test_code_verified_items_name_their_verifier() -> None:
    record = item_record(DRAFT, {}, date(2026, 11, 21), by="code checks 1")
    assert record["verified"] == "code checks 1, 2026-11-21"
    assert item_record(DRAFT, {}, date(2026, 11, 21))["verified"] == "owner, 2026-11-21"
