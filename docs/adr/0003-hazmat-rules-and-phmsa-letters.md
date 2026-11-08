<!-- Author: Nicola Antonello -->

# ADR-0003: US hazmat rules as the domain, graded by the regulator's letters

- Status: accepted
- Date: 2026-11-05

## Context

A RAG project is usually graded with questions its author wrote and answered, so its
answer key is only as good as the author's knowledge of the domain. This project needs a
corpus that anyone can download by script, rights that allow quoting it in a demo, and an
answer key that does not depend on the owner's expertise. The first choice,
microcontroller documentation, was dropped the same day for that last reason.

PHMSA, the US hazmat regulator, publishes interpretation letters that answer questions
from people such as shippers and inspectors. A typical letter restates the question,
answers it ("The answer is yes"), and names the sections behind the answer.

## Options

| Option | Why not |
|---|---|
| **The US hazmat regulations, graded by PHMSA's interpretation letters** | Chosen. The regulator has already answered real questions and cited the sections, so the labels are the regulator's, retrieval can be scored against the cited sections, and a yes or no can be scored by code with no model judge. GovInfo publishes the rules as dated XML editions and says US government works are generally public domain. |
| Microcontroller documentation: reference manuals, datasheets and errata | Chosen first, then dropped: the answer key would have needed expertise the project does not have. Vendor copyright also limits reuse, and one vendor's documents timed out for scripts. |
| Parcel carrier rules (USPS, UPS) | The project would write the whole answer key. USPS allows only private, non-business use of its content, and FedEx's guide could not be fetched by script. |
| Data science documentation | The project would write the whole answer key, and models probably know much of it already, so retrieval might not matter. |
| The EU's dangerous goods rules | EUR-Lex returned a bot challenge and UNECE refused the script, so a stranger's script could not fetch the corpus. |

## Decision

The corpus is the US hazardous materials regulations in 49 CFR, from GovInfo, and the
test questions come from PHMSA's interpretation letters. ADR-0006 fixes the parts and the
edition. ADR-0007 and ADR-0008 fix how letters become test items and how those are split.

## Consequences

- The labels are the regulator's own, and a yes or no is scored by code.
- When this was decided, the Internet Archive held 1,245 letters from 2015 to 2026, 621
  of them from 2019 to 2025. A sample of 78 letters gave about 0.5 usable questions per
  letter, and in two batches 44% and 55% of the yes-or-no answers were yes, so always
  answering yes would score only about half. ADR-0007 refines these counts.
- PHMSA's own site refuses scripts, so the letters come from the Internet Archive.
- The rules change over time, so an older letter may not match the edition. ADR-0007
  deals with this.
- Letters name real people, so only cleaned questions are kept.
- Public domain for the letters is an inference: GovInfo's statement is general, and
  data.gov lists the letters' rights only as "public".
- The owner checks labels against the letters, which needs care but not hazmat
  expertise. The demo says it is not compliance advice.

## References

- GovInfo, [Policies](https://www.govinfo.gov/about/policies).
- PHMSA, [Hazardous Materials Safety Interpretations](https://catalog.data.gov/dataset/hazardous-materials-safety-interpretations), on data.gov.
- Internet Archive, [Wayback Machine](https://web.archive.org/), which holds the copies of the letters.
- USPS, [Terms of Use](https://about.usps.com/who/legal/terms-of-use.htm).
