# Author: Nicola Antonello
"""The owner's check of each kept draft, on a page served on 127.0.0.1 (ADR-0019).

Usage: python -m regulator_graded_rag.review_page --split {dev,heldout}
[--heldout-by-owner] [--port 8765], from the repository root.

The page shows one kept draft at a time, oldest letter first, beside the letter's text.
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

from regulator_graded_rag.citations import Cited, item_type, table_units
from regulator_graded_rag.drafts import DRAFTS, Draft, load_drafts, write_drafts
from regulator_graded_rag.extract import EXTRACTOR
from regulator_graded_rag.gold import EDITION, validate
from regulator_graded_rag.index import read_passages
from regulator_graded_rag.letter_page import read_page
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
Action = Literal["approve", "edit", "reject"]
ACTIONS: tuple[Action, ...] = ("approve", "edit", "reject")
_MAX_BODY = 1 << 20
# The page runs no script and loads nothing: its style sheet is inline, and its form
# posts back to it alone.
_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "frame-ancestors 'none'; base-uri 'none'"
)
_HINTS = {
    "picture": (
        "The letter mentions a picture, sample or attachment: reject the question if"
        " it needs one."
    ),
    "not rewritten": (
        "No fixed rule rewrote the question: check that it reads as a question on its"
        " own."
    ),
    "known difference": (
        "eCFR's text differs from the edition's for a cited section: compare the cited"
        " paragraphs by eye."
    ),
    "date from the publish field": (
        "The letter's first line is not a date, so its publish date is used: confirm"
        " it."
    ),
    "dates differ": (
        "The letter's own date and its publish date differ: confirm the letter's date."
    ),
    "outside the corpus": (
        "The answer also cites rules outside Parts 171-180. They are not evidence,"
        " since no run can retrieve them."
    ),
    "scrubbed": "Names, emails or phone numbers were removed: check that none is left.",
    "unnumbered": (
        "The letter numbers no question: check that the answer is this question's."
    ),
    "answer continues": (
        "The answer's later paragraphs add citations: keep only the answer's own."
    ),
}
_UNANSWERABLE_HINT = (
    "Search the corpus first. If nothing in Parts 171-180 answers the question, write"
    " what you searched under Evidence and save the edit; if something does, reject it."
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
"""


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
    draft: Draft, fields: Mapping[str, object], verified_on: date
) -> dict[str, object]:
    """The gold item a draft makes, with the fields the owner edited."""
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
        "verified": f"owner, {verified_on.isoformat()}",
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


def render(
    draft: Draft,
    letter_text: str,
    token: str,
    *,
    error: str = "",
    form: Mapping[str, str] | None = None,
) -> str:
    """One page: the draft's form beside the letter's text, every text escaped, with no
    script and nothing loaded. After a refused save, error says why and form keeps
    what the owner typed."""
    e = html.escape
    values = {
        "question": draft.question,
        "answer": draft.answer,
        "evidence": "\n".join(draft.evidence),
        "letter_date": draft.letter_date,
    }
    values |= {name: form[name] for name in values if form and name in form}
    notes = [f"<li><b>{e(f)}</b>: {e(_HINTS.get(f, ''))}</li>" for f in draft.flags]
    if draft.type == "unanswerable":
        notes.insert(0, f"<li><b>unanswerable</b>: {e(_UNANSWERABLE_HINT)}</li>")
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
    paragraphs = "\n".join(
        f"<p>{e(line)}</p>" for line in letter_text.splitlines() if line.strip()
    )
    rows = max(3, len(values["evidence"].splitlines()) + 1)
    body = f"""<section>
<h1>{e(draft.id)}</h1>
<p class="meta">Type {e(draft.type)}. Letter dated {e(draft.letter_date)}, from its
{"own first line" if draft.date_source == "letter" else "publish date"}.</p>
{f'<p class="error">{e(error)}</p>' if error else ""}
{f'<div class="note"><ul>{"".join(notes)}</ul></div>' if notes else ""}
<form method="post" action="/">
<button type="submit" disabled hidden aria-hidden="true"></button>
<input type="hidden" name="token" value="{e(token)}">
<input type="hidden" name="id" value="{e(draft.id)}">
<label for="question">Question</label>
<textarea id="question" name="question" rows="5">{e(values["question"])}</textarea>
{answer}
<label for="evidence">Evidence, one label per line</label>
<textarea id="evidence" name="evidence" rows="{rows}">{e(values["evidence"])}</textarea>
<label for="letter_date">Letter date</label>
<input id="letter_date" name="letter_date" value="{e(values["letter_date"])}">
<div class="actions">
<button name="action" value="approve">Approve as drafted</button>
<button name="action" value="edit">Save edits</button>
<button name="action" value="reject">Reject</button>
</div>
</form>
{f"<table><tr><th>Label</th><th>Drift check</th></tr>{drift}</table>" if drift else ""}
<p><a href="{e(draft.source)}" rel="noreferrer">The letter in the Internet Archive</a></p>
</section>
<section class="letter">
<h2>The letter</h2>
{paragraphs}
</section>"""
    return _page(f"{draft.id}: the owner's check", body)


class _Review(ThreadingHTTPServer):
    """The page's server, with the drafts still to check and where decisions go."""

    daemon_threads = True

    def __init__(
        self,
        port: int,
        token: str,
        queue: Sequence[Draft],
        drafts: Path,
        decisions: Path,
        tables: AbstractSet[str],
        units: AbstractSet[str],
        letter: Callable[[Draft], str],
    ) -> None:
        super().__init__(("127.0.0.1", port), _Handler)
        self.port = int(self.server_address[1])  # the bound one, when port is 0
        self.token = token
        self.drafts = {draft.id: draft for draft in queue}
        self.queue = list(queue)
        self.drafts_file = drafts
        self.decisions = decisions
        self.tables = tables
        self.units = units
        self.letter = letter
        self.lock = threading.Lock()


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
        if urlsplit(self.path).path != "/" or not _has_token(token, self.review.token):
            self._send(
                HTTPStatus.NOT_FOUND, _message("Open the address the command printed.")
            )
            return True
        return False

    def do_GET(self) -> None:
        given = parse_qs(urlsplit(self.path).query).get("token", [""])[0]
        if self._refused(given):
            return
        with self.review.lock:
            draft = self.review.queue[0] if self.review.queue else None
        if draft is None:
            text = "Every kept draft has a decision. Stop the command with Ctrl+C."
            self._send(HTTPStatus.OK, _message(text))
            return
        page = render(draft, self.review.letter(draft), self.review.token)
        self._send(HTTPStatus.OK, page)

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
        draft = self.review.drafts.get(form.get("id", ""))
        if draft is None:
            self._send(HTTPStatus.BAD_REQUEST, _message("No draft by that ID.", token))
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
                draft, self.review.letter(draft), token, error=str(err), form=form
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
            self.review.queue = [d for d in self.review.queue if d.id != draft.id]
            left = len(self.review.queue)
        print(f"{decision.id}: {decision.action}; {left} left to check", flush=True)
        self._send(HTTPStatus.SEE_OTHER, _message("Saved.", token), f"/?token={token}")


def _letters(splits: Mapping[str, str]) -> Callable[[Draft], str]:
    """The letter's response text for a draft, read from its split's folder."""

    def text(draft: Draft) -> str:
        path = letter_path(draft.letter, splits) if draft.letter in splits else None
        page = None
        if path is not None and path.is_file():
            page = read_page(path.read_text(encoding="utf-8"))
        if page is None:
            return "The letter's page is missing or unreadable."
        return "\n".join(page.paragraphs)

    return text


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
    decisions = args.decisions or DECISIONS[args.split]
    drafts_file = args.drafts or DRAFTS[args.split]
    try:
        drafts = load_drafts(drafts_file)
        queue = pending(drafts, decisions)
        splits = load_split(SPLIT_FILE)
        records = read_passages(DEFAULT_OUT, load_manifest(DEFAULT_MANIFEST))
    except FileNotFoundError as err:
        print(f"{err.filename} is missing")
        return 1
    except (KeyError, TypeError, ValueError) as err:
        print(f"an input is wrong: {err!r}")
        return 1
    units = frozenset(record["id"].rsplit(":", 1)[0] for record in records)
    token = secrets.token_urlsafe(32)
    try:
        server = _Review(
            args.port,
            token,
            queue,
            drafts_file,
            decisions,
            table_units(records),
            units,
            _letters(splits),
        )
    except OSError as err:
        print(f"port {args.port}: {err.strerror}")
        return 1
    print(f"{len(queue)} of {sum(d.kept for d in drafts)} kept drafts to check.")
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
