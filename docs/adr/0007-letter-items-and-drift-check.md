<!-- Author: Nicola Antonello -->

# ADR-0007: Test items from the letters, kept only where the rules did not change

- Status: accepted
- Date: 2026-11-06

## Context

ADR-0003 grades the system with PHMSA's interpretation letters. PHMSA's site refuses
scripts (HTTP 403), so the letters come from the Internet Archive's copies, and 871 of
them date from 2017 to 2025.

A letter was answered under the rules of its own date. If a paragraph it relies on
changed before the edition, 1 October 2025, its yes or no may be wrong for this corpus.
eCFR serves each section as it read on any date since 2017, with its own paragraph IDs
such as `173.150(b)(2)`, so the cited text can be compared. A sample of 81 letters, 9 per
year from 2017 to 2025, measured the problem. The script printed counts only, so these
letters stay eligible for held-out.

- About a third of letters use numbered questions and answers. 34 questions qualified as
  items, about 0.42 per letter, and about half were answered yes.
- 19 of the 34 cite a section that eCFR's history marks as substantively amended between
  the letter and the edition. That flag is blunt: §171.8, the definitions, was the most
  cited section, and it changes in almost every rule.
- Comparing the exact cited paragraphs, 15 of the 19 flagged questions rest on a
  paragraph whose text really changed, and 4 do not.
- All 15 unflagged questions compared unchanged. This is the control: the check raises no
  false alarms.
- None cited only rules outside the corpus.

## Options

| Option | Why not |
|---|---|
| **Keep a question only when every paragraph it cites reads the same on the letter's date and in the edition, checked by code** | Chosen. Fully automatic and repeatable, and every kept label rests on unchanged text. It keeps about 56% of questions, roughly 200 from 2017 to 2025; the sample is small, so anything from about 120 to 300 would not be surprising. |
| The same, plus the owner's review of each changed paragraph | It recovers some of the 44% that the rule drops, but takes several more hours and asks a non-specialist for a legal judgment, which the owner would make alone for held-out items. |
| Drop every question whose cited section changed at all, from eCFR's section history | The simplest, but it also drops questions whose paragraph did not change (4 of the 19 flagged), keeping about 44%, roughly 160. |
| Keep every question | For 15 of the 34 sampled questions, the paragraph the answer rests on now reads differently, so their labels may be wrong for this corpus. |

## Decision

- **An item** is one numbered question from a letter dated 2017 or later whose answer
  starts with yes or no, cites at least one section, and needs no picture or attachment.
  Letters from before 2017 are left out because eCFR's dated text starts in 2017.
- **Each item stores** an ID made of the letter's reference number and the question
  number; the letter's date and its address in the archive; the question; the
  regulator's verdict and the sections and paragraphs it cites; a type; and who wrote and
  checked it. A fixed rule, not a model, turns "You ask whether..." into a direct
  question.
- **Types**, first match wins: `unanswerable`, `table` (it cites a table section such as
  §172.101), `multi_passage` (it cites several sections) and `lookup`.
- **The drift rule.** An item is kept only when every paragraph it cites reads the same,
  compared by code, on the letter's date and on 1 October 2025. Letters written after
  the edition qualify the same way. A test checks that eCFR's text for 1 October 2025
  matches the GovInfo edition, since the two are separate publications of the same
  rules.
- **Unanswerable items**, about one in five, measure declining. The owner writes most of
  them, about rules clearly outside the corpus, such as the international air or sea
  rules or another country's. Letter questions whose answers cite only rules outside
  Parts 171–180, such as Part 107 permits, also count when code finds them.
- **Personal data.** Items keep only the question and the answer. A script removes the
  names, emails and phone numbers it can recognise.
- **The owner's check.** The owner checks every item against its letter: the verdict, the
  cited sections, the date, that the question makes sense on its own, and that no
  personal data is left.

## Consequences

- The labels stay the regulator's own, and code proves they still apply, so nobody has to
  make legal judgments.
- If about 200 questions turn out to be too few, the remedy is to extract more questions
  from more letters, tested on dev, rather than loosening the rule.
- Fetching all 871 letters politely takes about an hour, so it is the first task of
  phase 2. The full count of usable questions, the supply of unanswerable letter
  questions and the yes-or-no balance are unverified until then.
- The letters are public, so a model may have read them in training. ADR-0012 measures
  this with the closed-book run and with letters dated after the model's training cutoff.

## References

- eCFR, [API documentation](https://www.ecfr.gov/developers/documentation/api/v1).
- PHMSA, [Hazardous Materials Safety Interpretations](https://catalog.data.gov/dataset/hazardous-materials-safety-interpretations), on data.gov.
- Internet Archive, [Wayback Machine](https://web.archive.org/), which holds the copies of the letters.
- Jonathan H. Clark et al., [TyDi QA: A Benchmark for Information-Seeking Question Answering in Typologically Diverse Languages](https://doi.org/10.1162/tacl_a_00317) (TACL, 2020).
- Pranav Rajpurkar, Robin Jia and Percy Liang, [Know What You Don't Know: Unanswerable Questions for SQuAD](https://doi.org/10.18653/v1/P18-2124) (ACL, 2018).
- Pranab Islam et al., [FinanceBench: A New Benchmark for Financial Question Answering](https://arxiv.org/abs/2311.11944) (arXiv, 2023).
