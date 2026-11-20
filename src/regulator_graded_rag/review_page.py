# Author: Nicola Antonello
"""The owner's check of each kept draft, on a page served on 127.0.0.1 (ADR-0019).

Usage: python -m regulator_graded_rag.review_page --split {dev,heldout}
[--heldout-by-owner] [--port 8765], from the repository root.

The page shows only the drafts the owner must judge (ADR-0022): those with a reason from
the checks, and the audit's sample of the drafts code accepted, which is drawn first
with python -m regulator_graded_rag.audit --split <split> --draw. Two changes in the
sample send the whole pool. The accepted drafts outside the sample are listed at /read
once the audit is done, for the owner to read their questions for personal data: one
button records a read for each, and a link sends one to the check. It shows one draft at a time, oldest letter first, with each
reason as a question, what code confirmed, and the letter's question and answer before
the letter, which is folded. Buttons add the letter's context to the question, by fixed
rules, and save nothing.
Approve keeps the draft as drafted, Save edits keeps the owner's corrections, and Reject
drops it. Each decision is appended to the split's decisions file at once, with the
digest of the draft it decides, so a draft extracted again is checked again. A rejected
draft, or one whose question the owner rewrote, stays in the drafts file without its
question, so only a question the owner approved as drafted reaches git. An edit is
refused unless the item it makes passes the gold checks and cites only the corpus, and
an edited evidence list brings the type it gives. Enter in a field submits nothing.
The page answers only on 127.0.0.1, to a request whose Host
names that address or localhost; it changes nothing without the session's token and
loads nothing from elsewhere. It opens only once the owner's unanswerable questions are
split, since the owner writes them before seeing any draft. Held-out drafts are checked
by the owner only (ADR-0014).
Exit code 0 when stopped, 1 when an input is missing or wrong, and 2 for a held-out run
without the owner's flag.
"""

import argparse
import hashlib
import html
import json
import os
import secrets
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal, cast
from urllib.parse import parse_qs, quote, urlsplit

from regulator_graded_rag.audit import AUDIT, Audit, changed, load_audit
from regulator_graded_rag.checks import (
    context_after,
    context_before,
    opening,
    pair_of,
    reasons,
    ticks,
)
from regulator_graded_rag.citations import Cited, item_type, table_units
from regulator_graded_rag.drafts import DRAFTS, Draft, load_drafts, write_drafts
from regulator_graded_rag.extract import EXTRACTOR
from regulator_graded_rag.gold import EDITION, validate
from regulator_graded_rag.index import read_passages
from regulator_graded_rag.letter_page import LetterPage, read_page
from regulator_graded_rag.letters import SPLIT_FILE, letter_path
from regulator_graded_rag.manifest import DEFAULT_MANIFEST, load_manifest
from regulator_graded_rag.passages import DEFAULT_OUT
from regulator_graded_rag.split import load_split

DECISIONS = {
    "dev": Path("eval/dev/decisions.jsonl"),
    "heldout": Path("eval/heldout/decisions.jsonl"),
}
UNANSWERABLE = {
    "dev": Path("eval/dev/unanswerable.jsonl"),
    "heldout": Path("eval/heldout/unanswerable.jsonl"),
}
Action = Literal["approve", "edit", "reject", "read", "check"]
# The form offers these three; the read list alone records a read or a check.
ACTIONS: tuple[Action, ...] = ("approve", "edit", "reject")
_MAX_BODY = 1 << 20
# The page runs no script and loads nothing: its style sheet is inline, and its form
# posts back to it alone.
_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "frame-ancestors 'none'; base-uri 'none'"
)
_STYLE = """
body { margin: 0; font: 16px/1.5 system-ui, sans-serif; color: #1d1d1b;
  background: #f7f6f2; }
main { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); gap: 32px;
  max-width: 1400px; margin: 0 auto; padding: 24px 16px; }
@media (max-width: 960px) { main { grid-template-columns: minmax(0, 1fr); } }
h1 { margin: 0 0 4px; font-size: 22px; }
h2 { margin: 0 0 12px; font-size: 18px; }
.meta { margin: 0 0 16px; color: #5c5b56; }
.note { margin: 0 0 16px; padding: 12px 16px; background: #fff4d6; border-radius: 6px; }
.note ul { margin: 0; padding-left: 20px; }
.error { margin: 0 0 16px; padding: 12px 16px; background: #fde2df; border-radius: 6px; }
label { display: block; margin: 16px 0 4px; font-weight: 600; }
textarea, input, select { width: 100%; box-sizing: border-box; font: inherit;
  padding: 8px; border: 1px solid #c9c7bf; border-radius: 6px; background: #fff; }
.actions { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0; }
button { font: inherit; padding: 8px 16px; border-radius: 6px;
  border: 1px solid #8f8d84; background: #fff; cursor: pointer; }
table { border-collapse: collapse; margin: 0 0 16px; }
th, td { padding: 4px 16px 4px 0; text-align: left; vertical-align: top; }
.letter { background: #fff; padding: 20px 24px; border-radius: 8px;
  border: 1px solid #e4e2da; overflow-wrap: anywhere; }
.letter p { margin: 0 0 12px; }
.letter details { margin: 16px 0 0; }
.ok { color: #1f6b34; }
.bad { color: #a3261b; font-weight: 600; }
ul.ticks { margin: 0 0 16px; padding-left: 20px; list-style: none; }
section > details { margin: 0 0 16px; }
"""
_BAR = (
    "Approve unless the verdict needs something nobody can see, the deciding rule is in"
    " a document outside the corpus, the question is incomplete or points at something"
    " only the letter shows, personal data is left, or the verdict, evidence or date"
    " does not match the letter. Wording that is stiff but clear stays. Evidence"
    " changes only to drop a citation that is not in the answer."
)


@dataclass(frozen=True)
class Decision:
    id: str
    action: Action
    fields: dict[str, object]  # the fields an edit changes, as the item holds them
    at: str
    digest: str  # the draft's, so a draft extracted again needs a new decision


def digest(draft: Draft) -> str:
    """The SHA-256 of the draft as its drafts file holds it."""
    text = json.dumps(asdict(draft), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def item_record(
    draft: Draft, fields: Mapping[str, object], verified_on: date, by: str = "owner"
) -> dict[str, object]:
    """The gold item a draft makes, with the fields the owner edited; by names who
    verified it, the owner or the checks of code."""
    record: dict[str, object] = {
        "id": draft.id,
        "question": draft.question,
        "type": draft.type,
        "answer": draft.answer,
        "evidence": list(draft.evidence),
        "letter_date": draft.letter_date,
        "source": draft.source,
        "split": draft.split,
        "written_by": f"PHMSA, extractor {EXTRACTOR}",
        "verified": f"{by}, {verified_on.isoformat()}",
        "edition": EDITION,
    }
    return record | dict(fields)


def _has_token(given: str, token: str) -> bool:
    return secrets.compare_digest(given.encode(), token.encode())


def _edited(
    draft: Draft, form: Mapping[str, str], tables: AbstractSet[str]
) -> dict[str, object]:
    """The fields the form changes. An edited evidence list brings the type it gives,
    since code, not the owner, assigns types."""
    fields: dict[str, object] = {}
    if "question" in form:
        question = " ".join(form["question"].split())
        if question != " ".join(draft.question.split()):
            fields["question"] = question
    for name, value in (("answer", draft.answer), ("letter_date", draft.letter_date)):
        if name in form and form[name].strip() != value:
            fields[name] = form[name].strip()
    if "evidence" in form:
        lines = (line.strip() for line in form["evidence"].splitlines())
        evidence = [line for line in lines if line]
        if tuple(evidence) != draft.evidence:
            fields["evidence"] = evidence
            if evidence and draft.type != "unanswerable":
                kind = item_type(Cited(tuple(evidence), ()), tables)
                if kind != draft.type:
                    fields["type"] = kind
    return fields


def kept_as(draft: Draft, action: str, fields: Mapping[str, object]) -> Draft:
    """The draft as the drafts file keeps it after the owner's decision: without its
    question when the owner rejects it or rewrites the question, so that only a
    question the owner approved as drafted reaches git (owner, 2026-11-16)."""
    if action == "reject" or "question" in fields:
        return replace(draft, question="")
    return draft


def decide(
    draft: Draft,
    form: Mapping[str, str],
    token: str,
    now: datetime,
    *,
    tables: AbstractSet[str],
    units: AbstractSet[str],
) -> Decision:
    """The owner's decision on a draft, from the page's form. A missing or wrong token
    is refused; so is an approval of an edited form, whose edits only Save edits keeps,
    and an approval or edit whose item breaks a gold rule, naming the field, or cites a
    unit outside units, the corpus's, which no run could retrieve. tables, the corpus's
    table sections, types an edited evidence list. The decision's digest is of the
    draft as the drafts file keeps it afterwards."""
    if not _has_token(form.get("token", ""), token):
        raise ValueError(
            "token: missing or wrong; open the address the command printed"
        )
    action = form.get("action", "")
    if action not in ACTIONS:
        raise ValueError(f"action: {action!r} is not one of {', '.join(ACTIONS)}")
    at = now.isoformat(timespec="seconds")
    if action == "reject":
        return Decision(draft.id, "reject", {}, at, digest(kept_as(draft, action, {})))
    fields = _edited(draft, form, tables)
    if action == "approve" and fields:
        raise ValueError(
            f"{draft.id}: {', '.join(fields)}: edited; Save edits keeps the edits, and"
            " reloading the page brings back the draft as drafted"
        )
    item = validate(item_record(draft, fields, now.date()), draft.id)
    outside = [
        label
        for label in item.evidence
        if item.answerable and label.split("(")[0] not in units
    ]
    if outside:
        raise ValueError(
            f"{draft.id}: evidence: {', '.join(outside)} not in the corpus; other"
            " parts' rules are not evidence, since no run can retrieve them"
        )
    kept = kept_as(draft, action, fields)
    return Decision(draft.id, cast(Action, action), fields, at, digest(kept))


def allowed_host(host: str, port: int) -> bool:
    """Whether a request's Host names this page: 127.0.0.1 or localhost, on its port.
    Any other name, such as one a hostile site rebinds to 127.0.0.1, is refused."""
    return host.lower() in {f"127.0.0.1:{port}", f"localhost:{port}"}


def append_decision(path: Path, decision: Decision) -> None:
    """The decision as one more JSON line, sorted keys and LF, flushed to the disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(asdict(decision), sort_keys=True, ensure_ascii=False) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(line)
        file.flush()
        os.fsync(file.fileno())


def rewrite_draft(path: Path, draft: Draft) -> None:
    """The drafts file with this draft's line replaced, and every other line kept."""
    drafts = load_drafts(path)
    write_drafts(path, [draft if old.id == draft.id else old for old in drafts])


def pending(drafts: Iterable[Draft], decisions: Path) -> list[Draft]:
    """The kept drafts with no decision on them as they now read, oldest letter
    first. A decision on another version of a draft does not count."""
    latest: dict[str, str] = {}
    if decisions.is_file():
        for line in decisions.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                latest[record["id"]] = record["digest"]
    return sorted(
        (
            draft
            for draft in drafts
            if draft.kept and latest.get(draft.id) != digest(draft)
        ),
        key=lambda draft: (draft.letter_date, draft.id),
    )


def current_actions(drafts: Iterable[Draft], decisions: Path) -> dict[str, str]:
    """Each draft's last decision, which counts only when its digest is the draft's as
    it now reads."""
    latest: dict[str, tuple[str, str]] = {}
    if decisions.is_file():
        for line in decisions.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                latest[record["id"]] = (record["action"], record["digest"])
    found: dict[str, str] = {}
    for draft in drafts:
        action, seen = latest.get(draft.id, ("", ""))
        if seen == digest(draft):
            found[draft.id] = action
    return found


def to_check(
    drafts: Iterable[Draft], actions: Mapping[str, str], audit: Audit
) -> list[Draft]:
    """The kept drafts with no approval, edit or rejection that the owner still checks,
    oldest letter first: those outside the audit's pool, which have a reason; those in
    its sample; and the whole pool once two sampled drafts have changed."""
    pool, sample = set(audit.pool), set(audit.sample)
    everything = changed(audit, actions) >= 2
    return sorted(
        (
            draft
            for draft in drafts
            if draft.kept
            and actions.get(draft.id) not in ACTIONS
            and (
                everything
                or draft.id not in pool
                or draft.id in sample
                or actions.get(draft.id) == "check"
            )
        ),
        key=lambda draft: (draft.letter_date, draft.id),
    )


def audit_left(audit: Audit, actions: Mapping[str, str]) -> int:
    """The sampled drafts the owner has not yet approved, edited or rejected."""
    return sum(actions.get(name) not in ACTIONS for name in audit.sample)


def to_read(
    drafts: Iterable[Draft], actions: Mapping[str, str], audit: Audit
) -> list[Draft]:
    """The kept drafts of the audit's pool outside its sample, with no action at all,
    oldest letter first: code accepted them, and the owner reads their questions for
    personal data. The list stays empty until the sample is decided, and for good once
    two sampled drafts have changed, since the whole pool then goes to the check."""
    if audit_left(audit, actions) or changed(audit, actions) >= 2:
        return []
    pool, sample = set(audit.pool), set(audit.sample)
    return sorted(
        (
            draft
            for draft in drafts
            if draft.kept
            and draft.id in pool
            and draft.id not in sample
            and draft.id not in actions
        ),
        key=lambda draft: (draft.letter_date, draft.id),
    )


def _page(title: str, body: str) -> str:
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n<style>{_STYLE}</style>\n</head>\n"
        f"<body>\n<main>\n{body}\n</main>\n</body>\n</html>\n"
    )


def _message(text: str, token: str = "") -> str:
    back = ""
    if token:
        href = html.escape(f"/?token={quote(token)}")
        back = f'<p><a href="{href}">Back to the drafts</a></p>'
    return _page(
        "The owner's check", f"<section>\n<p>{html.escape(text)}</p>{back}\n</section>"
    )


def _focus(draft: Draft, page: LetterPage | None) -> str:
    """The letter's opening, then the draft's question and its answer's paragraphs."""
    if page is None:
        return "<p>The letter's page is missing or unreadable.</p>"
    e = html.escape
    shown = [("Opening", opening(page))]
    if pair := pair_of(draft, page):
        shown += [("Question", pair.question), ("Answer", pair.answer)]
    return "\n".join(
        f"<h3>{label}</h3>\n"
        + "\n".join(f"<p>{e(line)}</p>" for line in text.splitlines() if line.strip())
        for label, text in shown
        if text.strip()
    )


def render(
    draft: Draft,
    page: LetterPage | None,
    token: str,
    *,
    error: str = "",
    form: Mapping[str, str] | None = None,
    units: Sequence[str] = (),
) -> str:
    """One page: the draft's form, with its reasons and what code confirmed, beside the
    letter's question and answer and then the letter folded, every text escaped, with
    no script and nothing loaded. After a refused save, error says why; form keeps what
    the owner typed, and units, the corpus's in order, lets the ticks read a range."""
    e = html.escape
    values = {
        "question": draft.question,
        "answer": draft.answer,
        "evidence": "\n".join(draft.evidence),
        "letter_date": draft.letter_date,
    }
    values |= {name: form[name] for name in values if form and name in form}
    found = reasons(draft, page)
    notes = [
        f"<li><b>{e(r.kind)}</b>: {e(r.ask)}"
        + (f" <i>{e(r.sentence)}</i>" if r.sentence else "")
        + "</li>"
        for r in found
    ]
    checked = "".join(
        f'<li class="{"ok" if holds else "bad"}">{"✓" if holds else "✗"} {e(text)}</li>'
        for holds, text in ticks(draft, page, units)
    )
    buttons = ""
    if page is not None and context_before(draft, page):
        buttons += (
            '<button name="action" value="before">'
            "Add the letter's context before the question</button>\n"
        )
    if page is not None and any(r.kind == "colon" for r in found):
        buttons += (
            '<button name="action" value="after">'
            "Add the next paragraph after the question</button>\n"
        )
    if draft.type == "unanswerable":
        answer = (
            '<input type="hidden" name="answer" value="">\n'
            "<p>No answer: the system must decline this question.</p>"
        )
    else:
        options = "".join(
            f'<option value="{v}"{" selected" if values["answer"] == v else ""}>{v}'
            "</option>"
            for v in ("yes", "no")
        )
        answer = (
            '<label for="answer">Answer</label>\n'
            f'<select id="answer" name="answer">{options}</select>'
        )
    drift = "".join(
        f"<tr><td>{e(label)}</td><td>{e(outcome)}</td></tr>"
        for label, outcome in draft.drift.items()
    )
    whole = "\n".join(
        f"<p>{e(line)}</p>"
        for line in (page.paragraphs if page is not None else ())
        if line.strip()
    )
    rows = max(3, len(values["evidence"].splitlines()) + 1)
    body = f"""<section>
<h1>{e(draft.id)}</h1>
<p class="meta">Type {e(draft.type)}. Letter dated {e(draft.letter_date)}, from its
{"own first line" if draft.date_source == "letter" else "publish date"}.</p>
<details><summary>The bar</summary><p>{e(_BAR)}</p></details>
{f'<p class="error">{e(error)}</p>' if error else ""}
{f'<div class="note"><ul>{"".join(notes)}</ul></div>' if notes else ""}
{f'<ul class="ticks">{checked}</ul>' if checked else ""}
<form method="post" action="/">
<button type="submit" disabled hidden aria-hidden="true"></button>
<input type="hidden" name="token" value="{e(token)}">
<input type="hidden" name="id" value="{e(draft.id)}">
<label for="question">Question</label>
<textarea id="question" name="question" rows="5">{e(values["question"])}</textarea>
{f'<div class="actions">{buttons}</div>' if buttons else ""}
{answer}
<label for="evidence">Evidence, one label per line</label>
<textarea id="evidence" name="evidence" rows="{rows}">{e(values["evidence"])}</textarea>
<label for="letter_date">Letter date</label>
<input id="letter_date" name="letter_date" value="{e(values["letter_date"])}">
<div class="actions">
<button name="action" value="approve" accesskey="a">Approve as drafted</button>
<button name="action" value="edit" accesskey="s">Save edits</button>
<button name="action" value="reject" accesskey="r">Reject</button>
</div>
</form>
{f"<table><tr><th>Label</th><th>Drift check</th></tr>{drift}</table>" if drift else ""}
<p><a href="{e(draft.source)}" rel="noreferrer">The letter in the Internet Archive</a></p>
</section>
<section class="letter">
<h2>The letter</h2>
{_focus(draft, page)}
<details><summary>The whole letter</summary>
{whole}
</details>
</section>"""
    return _page(f"{draft.id}: the owner's check", body)


def render_read(drafts: Sequence[Draft], token: str) -> str:
    """The questions to read, each with a form that sends it to the check, and one form
    that records them all as read. Every text escaped, no script."""
    e = html.escape
    if not drafts:
        return _message("Every accepted question has been read.", token)
    items = "\n".join(
        f"<li><b>{e(draft.id)}</b>: {e(draft.question)} "
        '<form method="post" action="/read">'
        f'<input type="hidden" name="token" value="{e(token)}">'
        f'<input type="hidden" name="id" value="{e(draft.id)}">'
        '<button name="action" value="check">Send to the check</button></form></li>'
        for draft in drafts
    )
    ids = e(" ".join(draft.id for draft in drafts))
    body = f"""<section>
<h1>Accepted questions to read</h1>
<p class="meta">Code accepted these. Read each question for personal data.</p>
<ul>
{items}
</ul>
<form method="post" action="/read">
<input type="hidden" name="token" value="{e(token)}">
<input type="hidden" name="ids" value="{ids}">
<div class="actions">
<button name="action" value="read">None of the rest holds personal data</button>
</div>
</form>
</section>"""
    return _page("The owner's read", body)


class _Review(ThreadingHTTPServer):
    """The page's server, with the drafts still to check and where decisions go. units
    are the corpus's, in corpus order."""

    daemon_threads = True

    def __init__(
        self,
        port: int,
        token: str,
        all_drafts: Sequence[Draft],
        drafts: Path,
        decisions: Path,
        tables: AbstractSet[str],
        units: Iterable[str],
        letter: Callable[[Draft], LetterPage | None],
        audit: Audit,
    ) -> None:
        super().__init__(("127.0.0.1", port), _Handler)
        self.port = int(self.server_address[1])  # the bound one, when port is 0
        self.token = token
        self.drafts = {draft.id: draft for draft in all_drafts}
        self.audit = audit
        self.actions = current_actions(all_drafts, decisions)
        self.queue = to_check(all_drafts, self.actions, audit)
        self.reading = to_read(all_drafts, self.actions, audit)
        self.drafts_file = drafts
        self.decisions = decisions
        self.tables = tables
        self.unit_order = tuple(units)
        self.units = frozenset(self.unit_order)
        self.letter = letter
        self.lock = threading.Lock()

    def refresh(self) -> None:
        """The lists again, after a decision or a read; the caller holds the lock."""
        self.queue = to_check(self.drafts.values(), self.actions, self.audit)
        self.reading = to_read(self.drafts.values(), self.actions, self.audit)


class _Handler(BaseHTTPRequestHandler):
    @property
    def review(self) -> _Review:
        return cast(_Review, self.server)

    def log_message(self, format: str, *args: object) -> None:
        """Nothing is logged, since a request's address carries the session's token."""

    def _send(self, status: HTTPStatus, page: str, location: str = "") -> None:
        body = page.encode("utf-8")
        self.send_response(status)
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", _CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _refused(self, token: str) -> bool:
        """Whether the request is refused, and answered so: one that names another
        host, or comes without the session's token, changes nothing."""
        if not allowed_host(self.headers.get("Host", ""), self.review.port):
            self._send(
                HTTPStatus.FORBIDDEN, _message("This page answers only locally.")
            )
            return True
        if urlsplit(self.path).path not in ("/", "/read") or not _has_token(
            token, self.review.token
        ):
            self._send(
                HTTPStatus.NOT_FOUND, _message("Open the address the command printed.")
            )
            return True
        return False

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        given = query.get("token", [""])[0]
        if self._refused(given):
            return
        token = self.review.token
        with self.review.lock:
            queue, reading = list(self.review.queue), list(self.review.reading)
            left = audit_left(self.review.audit, self.review.actions)
            changes = changed(self.review.audit, self.review.actions)
        if url.path == "/read":
            self._send(HTTPStatus.OK, self._read_list(reading, left, changes))
            return
        if "id" in query:
            draft = next((d for d in queue + reading if d.id == query["id"][0]), None)
            if draft is None:
                self._send(
                    HTTPStatus.NOT_FOUND, _message("No draft by that ID.", token)
                )
                return
        elif queue:
            draft = queue[0]
        else:
            self._send(HTTPStatus.OK, self._finished(len(reading)))
            return
        page = render(
            draft,
            self.review.letter(draft),
            self.review.token,
            units=self.review.unit_order,
        )
        self._send(HTTPStatus.OK, page)

    def _finished(self, unread: int) -> str:
        """The page for an empty queue: the read still to do, or the end."""
        done = "Every draft to check has a decision"
        if not unread:
            return _message(
                f"{done}, and every accepted question has been read."
                " Stop the command with Ctrl+C."
            )
        link = html.escape(f"/read?token={quote(self.review.token)}")
        text = f"{done}. {unread} accepted questions are left to read."
        return _message(text).replace(
            "</section>", f'<p><a href="{link}">Read them</a></p></section>'
        )

    def _read_list(self, reading: list[Draft], left: int, changes: int) -> str:
        """The read page: the list, or why it is empty."""
        token = self.review.token
        if left:
            text = f"The read opens once the audit is done: {left} audit drafts left."
        elif changes >= 2:
            text = "The audit found two changes, so every accepted draft goes to the check."
        else:
            return render_read(reading, token)
        return _message(text, token)

    def _with_context(
        self, draft: Draft, letter: LetterPage | None, form: Mapping[str, str]
    ) -> str:
        """The form again, its question field with the letter's context added by a fixed
        rule to what the owner typed; everything else typed stays as typed."""
        question = form.get("question", draft.question)
        if letter is not None:
            if form["action"] == "before":
                question = f"{context_before(draft, letter)} {question}".strip()
            else:
                question = f"{question} {context_after(draft, letter)}".strip()
        return render(
            draft,
            letter,
            self.review.token,
            form={**form, "question": question},
            units=self.review.unit_order,
        )

    def _read(self, form: Mapping[str, str]) -> None:
        """Record a read for each listed ID still to read, or a check for the one sent
        to the check, and show the list again, or that draft."""
        token = self.review.token
        at = datetime.now(UTC).isoformat(timespec="seconds")
        sent = form.get("action") == "check"
        listed = set(
            form.get("id", "").split() if sent else form.get("ids", "").split()
        )
        action: Action = "check" if sent else "read"
        where = f"/read?token={token}"
        with self.review.lock:
            for draft in [d for d in self.review.reading if d.id in listed]:
                append_decision(
                    self.review.decisions,
                    Decision(draft.id, action, {}, at, digest(draft)),
                )
                self.review.actions[draft.id] = action
                if sent:
                    where = f"/?token={token}&id={quote(draft.id)}"
            self.review.refresh()
            left = len(self.review.reading)
        print(f"{action}; {left} left to read", flush=True)
        self._send(HTTPStatus.SEE_OTHER, _message("Saved.", token), where)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = 0
        if not 0 < length <= _MAX_BODY:
            self._send(HTTPStatus.BAD_REQUEST, _message("Not a decision."))
            return
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        form = {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}
        if self._refused(form.get("token", "")):
            return
        token = self.review.token
        if urlsplit(self.path).path == "/read":
            self._read(form)
            return
        with self.review.lock:
            was = self.review.actions.get(form.get("id", ""))
            open_drafts = self.review.queue + self.review.reading
            draft = next((d for d in open_drafts if d.id == form.get("id")), None)
        if draft is None:
            self._send(HTTPStatus.BAD_REQUEST, _message("No draft by that ID.", token))
            return
        letter = self.review.letter(draft)
        if form.get("action") in ("before", "after"):
            self._send(HTTPStatus.OK, self._with_context(draft, letter, form))
            return
        try:
            decision = decide(
                draft,
                form,
                token,
                datetime.now(UTC),
                tables=self.review.tables,
                units=self.review.units,
            )
        except ValueError as err:
            page = render(
                draft,
                letter,
                token,
                error=str(err),
                form=form,
                units=self.review.unit_order,
            )
            self._send(HTTPStatus.BAD_REQUEST, page)
            return
        with self.review.lock:
            # The decision first: if the rewrite then fails, the digests differ, and
            # the draft comes back for a new decision rather than losing its question.
            append_decision(self.review.decisions, decision)
            kept = kept_as(draft, decision.action, decision.fields)
            if kept != draft:
                rewrite_draft(self.review.drafts_file, kept)
            self.review.drafts[draft.id] = kept
            self.review.actions[draft.id] = decision.action
            self.review.refresh()
            left = len(self.review.queue)
        print(f"{decision.id}: {decision.action}; {left} left to check", flush=True)
        where = f"/read?token={token}" if was == "check" else f"/?token={token}"
        self._send(HTTPStatus.SEE_OTHER, _message("Saved.", token), where)


def start_line(queue: Sequence[Draft], audit: Audit, actions: Mapping[str, str]) -> str:
    """How many drafts wait, by why: a reason from the checks, the audit's sample, the
    pool, which is in the queue only once two sampled drafts have changed, or the read,
    which sent them."""
    sampled = sum(d.id in audit.sample for d in queue)
    sent = sum(d.id not in audit.sample and actions.get(d.id) == "check" for d in queue)
    pooled = sum(
        d.id in audit.pool and d.id not in audit.sample and actions.get(d.id) != "check"
        for d in queue
    )
    line = (
        f"{len(queue)} to check: {len(queue) - sampled - sent - pooled} with a reason,"
        f" {sampled} in the audit sample"
    )
    line += f", {pooled} from the pool" if pooled else ""
    return line + (f", {sent} sent from the read" if sent else "")


def _letters(splits: Mapping[str, str]) -> Callable[[Draft], LetterPage | None]:
    """The letter's page for a draft, read from its split's folder; None when it is
    missing or unreadable."""

    def page(draft: Draft) -> LetterPage | None:
        path = letter_path(draft.letter, splits) if draft.letter in splits else None
        if path is None or not path.is_file():
            return None
        return read_page(path.read_text(encoding="utf-8"))

    return page


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.review_page",
        description="The owner's check of each kept draft, on a page on 127.0.0.1.",
    )
    parser.add_argument("--split", required=True, choices=sorted(DRAFTS))
    parser.add_argument(
        "--heldout-by-owner",
        action="store_true",
        help="the owner checks the held-out drafts (ADR-0014)",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--drafts", type=Path, help="default: the split's drafts")
    parser.add_argument("--decisions", type=Path, help="default: the split's decisions")
    parser.add_argument(
        "--unanswerable", type=Path, help="default: the split's unanswerable questions"
    )
    args = parser.parse_args(argv)
    if args.split == "heldout" and not args.heldout_by_owner:
        print("held-out drafts are checked by the owner only (ADR-0014)")
        return 2
    unanswerable = args.unanswerable or UNANSWERABLE[args.split]
    if not unanswerable.is_file():
        print(
            f"{unanswerable} is missing: the owner writes and splits the unanswerable"
            " questions before seeing any draft"
        )
        return 1
    audit_file = AUDIT[args.split]
    if not audit_file.is_file():
        print(
            "the audit is not drawn: run python -m regulator_graded_rag.audit"
            f" --split {args.split} --draw"
        )
        return 1
    decisions = args.decisions or DECISIONS[args.split]
    drafts_file = args.drafts or DRAFTS[args.split]
    try:
        drafts = load_drafts(drafts_file)
        audit = load_audit(audit_file)
        splits = load_split(SPLIT_FILE)
        records = read_passages(DEFAULT_OUT, load_manifest(DEFAULT_MANIFEST))
    except FileNotFoundError as err:
        print(f"{err.filename} is missing")
        return 1
    except (KeyError, TypeError, ValueError) as err:
        print(f"an input is wrong: {err!r}")
        return 1
    units = tuple(dict.fromkeys(record["id"].rsplit(":", 1)[0] for record in records))
    token = secrets.token_urlsafe(32)
    try:
        server = _Review(
            args.port,
            token,
            drafts,
            drafts_file,
            decisions,
            table_units(records),
            units,
            _letters(splits),
            audit,
        )
    except OSError as err:
        print(f"port {args.port}: {err.strerror}")
        return 1
    queue = server.queue
    print(start_line(queue, audit, server.actions))
    print(f"{len(server.reading)} accepted questions to read at /read")
    print(f"Open http://127.0.0.1:{args.port}/?token={token}", flush=True)
    print("Stop with Ctrl+C; every decision is saved as it is made.", flush=True)
    with server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
