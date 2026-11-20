<!-- Author: Nicola Antonello -->

# ADR-0022: Code checks and an audit for the gold items

- Status: accepted
- Date: 2026-11-20

## Context

Every letter item is checked by the owner against its letter
([ADR-0007](0007-letter-items-and-drift-check.md)), one draft at a time on a local page
([ADR-0019](0019-a-local-review-page.md)). After 39 of the 240 kept dev drafts, over
several days, the check was measured on 2026-11-20:

- No decision found an error in the extractor's verdict, evidence or date.
- The changes that were needed were judgment calls, on six drafts: an answer about
  examples the requester sent, a question about photographs, an answer that turns on a
  special permit, a question that ended with "You state the criteria are:", and two
  questions about "your scenario", which only the letter's opening describes.
- Several edits only reworded questions that already stood on their own. Two evidence
  edits made a label wrong, and the build would have dropped one of them; the owner
  decided both again on 2026-11-17.

At that pace the 201 dev drafts left, and about 160 held-out drafts that the owner checks
alone, put the owner's time on the critical path, the risk the design named. The checks,
version 1, are measured: they leave the owner 97 of the 201 undecided dev drafts and
accept the other 104. On the 39 decided drafts, they flag all six that needed a change.

### Goals and limits

- **Goals.** The owner spends about 2–4 hours on the rest of dev, and about the same on
  held-out. Code runs every check it can and shows the result. The labels' quality is
  measured and published. Both splits go through the same process, and the owner runs
  every held-out command.
- **Not in scope.** No model takes part in the check. The extractor and the drafts do not
  change, so the decisions already made stay valid.
- **Failure even if it works.** A wrong label passing unmeasured; a question that no
  person has read reaching git; an audit sample chosen after the drafts were seen; checks
  tuned on held-out; the two splits checked differently.

## Options

| Option | Outcome |
|---|---|
| A focused page: code's checks shown beside each draft, each flag asked as one question, new flags, one key per decision, and buttons that fill a question by fixed rules. The owner still decides every draft | Chosen, with the next (the owner, 2026-11-20) |
| Code accepts the drafts its checks clear, and the owner audits a random sample of them, drawn by a committed seed | Chosen, with 40 drafts per split (the owner, 2026-11-20) |
| Accepted questions committed as they are | Rejected: the scrubber can miss a name or an address, and git keeps only questions the owner has read. The owner reads them for personal data instead, about 10 minutes per split (the owner, 2026-11-20) |
| Claude pre-checks the dev drafts and lists the ones to look at | Rejected: nothing like it exists for held-out, which Claude never reads, so dev would end cleaner than held-out and the held-out score would fall for a reason unrelated to the system |
| Code also decides the flagged drafts, by fixed rules | Rejected: the patterns flag many drafts the owner rightly kept, such as 4 of the 6 decided drafts that mention something shown or sent and 7 of the 8 that name another document, so fixed rules would drop good items |
| The full check, unchanged | Rejected: the design estimated 4–8 hours per split, and the measured pace is several times slower |

## Decision

- **Code's checks**, version 1, give each kept draft the reasons the owner must look at
  it. A draft with no reason is accepted by code. The reasons are:
  - the extractor's flags that need judgment: picture, not rewritten, answer continues,
    outside the corpus, known difference, date from the publish field, and scrubbed;
  - an unanswerable draft, which needs the owner's search of the corpus;
  - a draft whose letter holds no question with its number;
  - a draft whose verdict the letter's answer does not give;
  - a question ending with a colon, whose letter goes on with what it asks;
  - a pointer with no context in the question, such as "these packages" or "your
    scenario";
  - something shown or sent, such as photographs, examples or attachments, named in the
    question or its answer;
  - another document, such as a special permit or an approval, named in the question or
    its answer;
  - a name from the letter's salutation found in the question.

  The checks read a draft and its letter and write nothing. Their tests require a reason
  on each of the six decided dev drafts whose change was needed: 17-0034-Q1, 18-0081-Q1,
  18-0081-Q3, 18-0086-Q1, 19-0015-Q1 and 19-0038-Q1. Rewordings of questions that stood
  on their own are not among them. Held-out uses the version the dev audit used, or a
  later one tuned on dev only.
- **The draw**, once per split, before the owner checks any draft that code accepted. The
  accepted pool is the kept drafts with no decision and no reason. The audit sample is
  the 40 of them with the lowest draw keys from the split's committed seed, each key
  taken over `audit:` and the draft's ID; a pool of 40 or fewer is audited whole. The
  pool, the sample and the checks' version are written to `eval/<split>/audit.json`, which
  is never redrawn. The held-out draw needs the owner's flag and prints counts only.
- **The page** (amending ADR-0019) shows the drafts with a reason and the audit sample,
  oldest letter first:
  - each reason as one question beside the sentence that raised it, such as "The answer
    names a special permit: does the verdict depend on it?";
  - ticks for what code confirmed: the verdict sentence, each citation matched to its
    evidence label, where the date came from, and no salutation name in the question;
  - the letter's opening, the question and its answer first, and the whole letter folded
    below;
  - Approve, Save edits and Reject on Alt+A, Alt+S and Alt+R, with no script;
  - buttons that fill the question field by fixed rules, saving nothing: the opening's
    sentences in the requester's voice before the question, or the letter's next
    paragraph after a question ending with a colon;
  - the owner's bar, below.
- **The owner's bar.** Approve unless the verdict needs something nobody can see, the
  deciding rule is in a document outside the corpus, the question is incomplete or
  points at something only the letter shows, personal data is left, or the verdict,
  evidence or date does not match the letter. Wording that is stiff but clear stays.
  Evidence changes only to drop a citation that is not in the answer.
- **An audit error** is an audit draft the owner rejects or edits in any field, so the
  audit counts the drafts the owner would have changed, a wider class than wrong labels.
  The decision fixes it. With two or more errors in a split, every accepted draft of that
  split goes to the owner: the page shows them, and the build requires a decision on
  each.
- **The read for personal data.** Once the audit is done, one page lists every accepted
  question outside the sample. The owner reads them for personal data only, and a
  question with some goes to the normal check by its own button, which marks it so: the
  read can no longer cover it, and only the owner's decision builds it. The page records the read of each one, so
  git keeps only questions the owner has read: approved as drafted, or read for personal
  data.
- **The build** keeps the owner's decisions as now. An accepted draft outside the sample
  that the owner read becomes an item as drafted, written by "PHMSA, extractor 2" and
  verified by code's checks, version 1, with the date of the draw. The build prints the
  audit's result: the drafts the owner changed in the sample, and the exact 95% upper
  bound on how many of the items that only code verified the owner would have changed,
  for a pool of its real size. It is stated as a count, as a share of those items and as
  a share of the gold set: no change in 40 from a pool of 104 means at most 5 of the
  64 items, 7.8% of them and about 2% of the dev set. The README and the final report show
  it beside the gold set's counts.
- **The rule changes.** "Every gold label is checked by the owner" becomes: every gold
  label is either checked by the owner, or accepted by code's checks and covered by the
  owner's random audit; every question in git has been read by the owner; each record
  says who wrote and who verified it; and the audit's result is published. This
  supersedes the owner's check in ADR-0007, and the design changes with it.

## Consequences

- On dev the owner checks 97 flagged drafts and 40 audit drafts instead of 201, each
  with code's checks in view, and reads about 64 accepted questions for personal data.
  Held-out goes the same way.
- The gold set's claim changes from "every item checked" to a measured bound, about 2%
  of the dev set when the audit changes nothing. Each change the audit finds is fixed,
  and two send the whole accepted pool to the owner.
- Each item records whether the owner or code verified it, so a run can be scored on each
  group to show whether results differ by provenance.
- A draw fixes its pool and sample for good; a later version of the checks changes
  neither.
- The audit is not blind: the owner can tell a sample draft by its lack of reasons, and
  knows that two changes open the whole pool. The checks, version 1, were frozen before
  the dev draw computed any audit key.
- The decisions made so far stay valid, and those drafts count as checked by the owner.

## Left to the plan

The exact patterns and their tests, the page's layout and the context rules' details,
how the read and the draw are recorded, the build's output, how the bound is computed
with the standard library, and where the README shows the audit.

## References

- C. J. Clopper and E. S. Pearson, [The use of confidence or fiducial limits illustrated
  in the case of the binomial](https://doi.org/10.1093/biomet/26.4.404), Biometrika
  26(4), 404–413, 1934: the exact interval, which the bound follows with the
  hypergeometric distribution of a finite pool.
- Curtis G. Northcutt, Anish Athalye and Jonas Mueller, [Pervasive Label Errors in Test
  Sets Destabilize Machine Learning Benchmarks](https://datasets-benchmarks-proceedings.neurips.cc/paper_files/paper/2021/hash/f2217062e9a397a1dca429e7d70bc6ca-Abstract-round1.html),
  NeurIPS Datasets and Benchmarks Track, 2021: label errors average at least 3.3% across
  ten benchmark test sets, found by flagging candidates with code and confirming them by
  hand, which is why this gold set measures its own.
