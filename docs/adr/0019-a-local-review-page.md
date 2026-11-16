<!-- Author: Nicola Antonello -->

# ADR-0019: A local review page for the owner's check

- Status: accepted
- Date: 2026-11-16

## Context

A gold label is human-verified ([ADR-0007](0007-letter-items-and-drift-check.md)): code
drafts each letter item, and only the owner approves it. The owner checks that the yes or
no matches the letter, that the cited sections and paragraphs match it, that the letter's
date is right, that the question makes sense on its own, and that no personal data is
left. On dev that is about 240 kept drafts. The owner checks the held-out ones alone
([ADR-0014](0014-when-the-held-out-split-runs.md)).

The check needs three things: the letter's text beside the draft, a way to correct a
field, and a record of every decision from which code can rebuild the items. Plan 2a
chose a local page on 2026-11-14, and plan 2c built it.

## Options

| Question | Chosen | Rejected |
|---|---|---|
| The tool | A page that Python's standard library serves on 127.0.0.1, one draft at a time beside its letter, with Approve, Save edits and Reject | A spreadsheet: the letter's text is not beside the row, a cell takes any value, and a sort or a paste can shift rows silently. Editing the JSON by hand: nothing checks an edit until the items are built |
| The record | Each decision appended to a JSON-lines file, the last one per draft winning | Editing the drafts file in place, which mixes the extractor's output with the owner's corrections, so the next extraction erases them |
| A question the owner rejects or rewrites | Taken out of the committed drafts file, which then holds only questions the owner approved as drafted | Left in it, so personal data the owner catches still reaches git; no question text in the drafts file at all, which changes the drafts' format; or not committing the drafts, which loses why each one was dropped |
| Who can use it | The owner's browser on this machine, through the address, the Host, a session token and a page that loads nothing | A login or a hosted page: more to build and to secure, for one user |

## Decision

- **The page** shows the kept drafts that have no decision, oldest letter first. Each one
  stands beside its letter's text, with its flags explained and its drift outcomes.
  - **Approve** keeps the draft as drafted. Approving an edited form is refused, so an
    edit is never dropped silently.
  - **Save edits** records only the fields that changed. The item it makes must pass the
    gold checks, or the edit is refused with the field and why. Its evidence must lie in
    the corpus, since no run can retrieve another part's rule. An edited evidence list
    brings the type it gives, since code, not the owner, assigns types. An edited date
    or evidence list is checked for drift again when the items are built.
  - **Reject** drops the draft.
  - Pressing Enter in a field submits nothing, so no draft is approved by accident.
- **Each decision** is appended to `eval/<split>/decisions.jsonl` and flushed to the disk
  at once, with its time and the SHA-256 of the draft it decides. A draft that a new
  extraction changes is shown again, so an old decision never vouches for new text.
- **The drafts file.** A rejected draft, or one whose question the owner rewrote, stays
  in `eval/<split>/drafts.jsonl` without its question, and the decision's digest is of
  the draft so kept. The committed file then holds only questions the owner approved as
  drafted, since the owner may have caught personal data in the others (the owner,
  2026-11-16).
- **Security.** Python's `http.server` implements only basic security checks, so the page
  adds its own:
  - it binds 127.0.0.1 only, so no other machine reaches it;
  - it answers only a request whose Host is `127.0.0.1:<port>` or `localhost:<port>`, so
    a hostile site that points its own name at 127.0.0.1 is refused;
  - every start makes a fresh `secrets.token_urlsafe(32)`, carried by the address the
    command prints and by every form, and compared in constant time. A request without
    it reads and changes nothing, so another site's form cannot post a decision;
  - the page runs no script, and every text from a letter or a draft is escaped. Its
    Content-Security-Policy lets it load nothing, sit in no frame and post only to
    itself;
  - requests are not logged, since their addresses carry the token.
- **Order.** The page opens only once `eval/<split>/unanswerable.jsonl` exists, since the
  owner writes the unanswerable questions before seeing any draft. Held-out drafts need
  the owner's flag. Without it the command exits 2 before reading any file.

## Consequences

- The owner checks one draft per page at their own pace, and no decision is lost to a
  closed browser or a stopped command.
- The decisions file records who verified what and when. Code rebuilds the items from
  the drafts and the decisions, and nobody edits them by hand.
- A new extractor version sends every draft it changes back to the owner, so extractor
  fixes land before the owner's check, not after it.
- Nothing the page shows leaves the machine, and the only letter text the committed
  drafts file keeps is what the owner approved as drafted.

## References

- Python, [`http.server` — HTTP servers](https://docs.python.org/3.14/library/http.server.html) (Python documentation): not recommended for production, since it implements only basic security checks.
- Python, [`secrets` — Generate secure random numbers for managing secrets](https://docs.python.org/3.14/library/secrets.html) (Python documentation): `token_urlsafe`, and the constant-time `compare_digest`.
- OWASP, [Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) (OWASP Cheat Sheet Series): a token unique per session, secret and unpredictable, and a request without it rejected.
- MDN, [Content-Security-Policy (CSP) header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy) (MDN Web Docs): the `default-src`, `form-action`, `frame-ancestors` and `base-uri` directives.
