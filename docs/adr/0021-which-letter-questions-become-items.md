<!-- Author: Nicola Antonello -->

# ADR-0021: Which letter questions become items

- Status: accepted
- Date: 2026-11-16
- Supersedes: the first line of [ADR-0007](0007-letter-items-and-drift-check.md)'s
  Decision, which made an item only of a numbered question

## Context

ADR-0007 makes an item of a question whose answer starts with yes or no and cites at
least one section, and turns "You ask whether…" into a direct question by a fixed rule.
Before the extractor was built, the 543 dev letters were measured on 2026-11-16, by
scripts that print counts and by reading four letters in full. Nothing under `heldout/`
was read.

- **Numbered questions.** 213 letters number their questions ("Q1. …"/"A1. …"): 684
  questions, 252 of them answered with yes or no and at least one cited section.
- **Unnumbered questions.** 108 more letters ask a single "You ask whether…" question
  whose next paragraph answers it the same way.
- **The question's form.** Questions read "You ask whether X" (286) or "You ask if X"
  (82). Others ask for confirmation, put context sentences first, or are already direct
  ("May a shipper…?").
- **§171.8.** 31 of the 252 cite §171.8, the definitions, which change in almost every
  rule. eCFR keys each definition by its term, such as `171.8(Hazmat%20employee)`.
- **Pictures.** 20 mention a picture, photo, attachment or sample.
- **Tables.** 128 sections hold table rows. §171.8 is among them, with 5 rows beside 43
  text passages.
- **Dates.** A letter's own first line and its publish date differ in 48 letters, 7 of
  them by more than a month.

## Options

| Question | Chosen | Rejected |
|---|---|---|
| Which questions | Numbered ones, and a letter's only unnumbered one | Numbered only, as ADR-0007 said: about 140 dev items after the drift check instead of about 200 |
| The direct question | "Is it the case that X?" | Moving X's first modal or auxiliary to the front: it reads naturally, but a wrong inversion garbles a question |
| A §171.8 citation | The definition it names | The whole section, which drops nearly every definition question |
| Pictures and attachments | Flagged for the owner's check | Dropped, which loses answerable questions |
| A table section | Its table rows outnumber its text passages | Any table row: 102 of 246 candidates would be `table`, 30 of them for §171.8 |
| The letter's date | Its own first line, then its publish date | The publish date alone |
| How far an answer runs | To the next question, the requester's next words or the letter's closing, flagged when its later paragraphs add citations | Its first paragraph, which leaves later citations out of the evidence and the drift check |
| An unkept draft in the committed drafts file | Without its question | With it, unchecked; or not committed, which loses why it was dropped |

The owner chose the first four on 2026-11-16 and accepted the next two with plan 2c. A
fresh review of the extractor then found that answers run past their first paragraph and
that unkept drafts would put unchecked letter text into git, and the owner chose the last
two the same day. The same review brought the citation rules for ranges and bare
paragraphs below. Rerunning the dev drafts then showed a paragraph that sets up the next
question dropping a draft the owner would never see, so an answer also ends where the
requester speaks again.

## Decision

- **An item** is a numbered question, or the only question of a letter that numbers
  none, from a letter dated 2017 or later, whose answer starts with "The answer is
  yes/no", "The answer to your question is yes/no", or "Yes"/"No" as a word, cites at
  least one section, and needs no picture or attachment.
  - Only the answer's own citations are evidence. The answer runs from its first
    paragraph to the next question, the letter's closing, or a paragraph in the
    requester's voice ("You ask about…", "You describe…"), which opens the next
    question's context; PHMSA's advice ("You may…", "You should…") stays in the
    answer. A draft whose later paragraphs add citations is flagged, since other text,
    such as a list of frequently asked questions, can sit there.
  - A letter with two or more unnumbered questions gives no item, so a question is never
    paired with another's answer.
  - This replaces the first line of ADR-0007's Decision. Its other rules stand.
- **The direct question.** The asking clause becomes "Is it the case that X?", and PHMSA's
  other words stay as written.
  - The asking clauses are "You ask whether X", "You ask if X", "You ask for confirmation
    that X" and "… and ask whether X".
  - A discourse marker before the clause ("Specifically,", "Therefore,") goes. Any other
    phrase ending in a comma is a condition of the question and stays: "For an approved
    explosive, is it the case that X?".
  - A question that is already direct stays as written.
  - A question with no rule, or with two asking clauses, is kept as written and flagged.
- **Citations** are read after "§", "§§", "Section" or "49 CFR", as "paragraph (b) of
  § 173.24", or as "Appendix B to Part 172".
  - A range gives every member: paragraphs along the CFR's levels, (a), (1), (i), (A),
    and sections in the corpus's order.
  - A bare paragraph after a deeper one replaces the level of its kind, so "§ 173.115(b)(1)
    and (2)" gives (b)(2).
  - Other parts' citations are kept apart, and an answer that cites only those is an
    unanswerable candidate.
- **A §171.8 citation** whose sentence names a definition gives eCFR's key for it, and
  the drift check compares that definition alone.
  - An unquoted term counts only when eCFR defines it, since nothing else marks where it
    ends. A quoted term eCFR defines counts anywhere in the sentence.
  - A key naming two terms, such as "Gross weight or Gross mass", answers to either.
  - A term eCFR does not hold reads "missing", so the item is dropped.
- **Pictures, photos, attachments and samples** are flagged for the owner's check.
- **The committed drafts file** holds an unkept draft without its question, since the
  owner checks only kept drafts, and no unchecked letter text reaches git.
- **Types**, first match wins: `unanswerable`, `table` (a cited section whose table rows
  outnumber its text passages), `multi_passage` (two or more sections) and `lookup`.
- **The letter's date** is its own first line, else its publish date. The owner confirms
  it at the check, and an edited date is checked for drift again.

## Consequences

- The dev split should give about 200 items after the drift check, instead of about 140,
  so smaller differences become detectable. The owner checks about 60 more, and the
  held-out split grows alike.
- A question about a definition survives when that definition did not change, instead of
  falling with the whole of §171.8.
- The fixed rule reads stiffly, but it never garbles a question. A question it cannot
  rewrite reaches the owner flagged, never silently.

## Amendments

- 2026-11-16: Measured on the 240 kept dev drafts before the owner's check, five rules
  were refined. Together they touch 12 drafts, and the extractor became version 2.
  - A phrase that is only a pointer to the requester's letters ("In your most recent
    letter,", "In your email dated May 5, 2019,") goes, like a discourse marker. A
    phrase that goes on past the pointer stays whole, and so does a pointer to another
    question ("In connection to question Q1,"), which tells the owner the question
    leans on that one.
  - A letter's opening sentence leaves the question whether it reads "This letter is in
    response to…", "This is in response to…" or "This responds to…", unless it asks
    the question itself.
  - A quoted ending loses the period before its closing quote, so the question ends
    `an "unsafe condition"?`. A quotation's own "?" or "!", and an abbreviation's
    period, stay.
  - "…and, if so, whether…", "…and, if not, …" and "…and—if so—…" ask a second
    question, so the question is kept as written and flagged.
  - What the requester showed or sent ("as shown in your incoming email", "the example
    included with your email") is flagged with the pictures.
- 2026-11-17: The owner ruled that a draft whose verdict also depends on a rule outside
  the corpus stays, with only its in-corpus citations as evidence, as the Decision
  implies. The first such draft asked whether a driver needs a hazmat endorsement, which
  Part 383 governs, for a Class 9 shipment, and §172.504(f)(9) decided it: a Class 9
  placard is not required for domestic transportation.
  [ADR-0022](0022-code-checks-and-an-audit-for-gold-items.md)'s bar sets the limit: a
  draft whose deciding rule is in a document outside the corpus is rejected. Of the dev
  set's 207 letter items, 12 come from such drafts; the drafts file's `outside` field
  names their other rules, so results can be reported with and without them.
- 2026-11-20: Under [ADR-0022](0022-code-checks-and-an-audit-for-gold-items.md), a date
  taken from the publish date is a reason for the owner's check, where the owner
  confirms it; a date from the letter's own first line raises none, so in the drafts
  code accepts, the random audit covers it.

## References

- eCFR, [API documentation](https://www.ecfr.gov/developers/documentation/api/v1), whose
  renderer keys each §171.8 definition by its term.
