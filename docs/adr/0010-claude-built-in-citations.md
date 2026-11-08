<!-- Author: Nicola Antonello -->

# ADR-0010: Claude's built-in citations for answers

- Status: superseded by [ADR-0011](0011-local-generator-and-json-answers.md)
- Date: 2026-11-06

## Context

At this point, Claude was to write every answer. The generator receives a fixed system
prompt kept in code, the question and the top passages, each with its ID and section
heading, and gets no tools. Code then reads the verdict (yes, no or not covered), checks
every citation word for word, turns a yes or no with no verified citation into a
decline, and records safety refusals as their own outcome. The open question was how
citations are produced.

## Options

| Option | Why not |
|---|---|
| **Claude's built-in citations, with each passage sent as a search result** | Chosen on 2026-11-06. The API documentation guarantees that every citation points into the passages sent, so quotes cannot be invented, and the code check stays as a second guard. Cited text is not billed as output. The documentation recommends this pattern, one line per field read by code, when fields and citations are both needed. It is specific to Claude, and the verdict line has to be parsed, so format failures are counted. |
| A fixed JSON format, with quotes the model writes itself | It works with any provider that supports JSON formats, the verdict needs no parsing, and the code check genuinely catches mistakes. But the model will sometimes paraphrase a quote, which fails the check and turns a correct answer into a decline; quotes are billed as output; and the API cannot combine this format with built-in citations in one call. |

## Decision

Each passage goes in as a search result labelled with its passage ID. Claude answers in
plain text whose first line is "Verdict: yes", "Verdict: no" or "Verdict: not covered",
and the API attaches each citation to the sentence it supports. Code still checks every
citation. The JSON format would be tried as an experiment in phase 4.

## Consequences

- Superseded on 2026-11-07. When the default generator became a local open-weight model
  (ADR-0011), the default model no longer had built-in citations. Every model now answers
  in one JSON format with quotes it writes itself, and Claude's built-in citations became
  an experiment.
- What this comparison found still holds for that experiment: built-in citations cannot
  be combined with JSON output in the same call, so the experiment changes the answer
  format as well as the citation method.

## References

- Claude documentation, [Citations](https://platform.claude.com/docs/en/build-with-claude/citations).
- Claude documentation, [Search results](https://platform.claude.com/docs/en/build-with-claude/search-results).
- Claude documentation, [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).
