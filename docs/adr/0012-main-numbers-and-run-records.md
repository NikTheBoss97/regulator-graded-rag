<!-- Author: Nicola Antonello -->

# ADR-0012: The main numbers and run records

- Status: accepted
- Date: 2026-11-07

## Context

Each stage needs one main number fixed before any results exist, so that no number can be
picked after seeing which one looks best. Retrieval and generation are measured
separately, so a failure can be pinned to a stage. The labels are the regulator's yes or
no and the sections it cited (ADR-0007), so most measures can be computed by code.

## Options

For generation's main number; all three are reported either way:

| Option | Why not |
|---|---|
| **The supported verdict: the yes or no matches the regulator's, and at least one verified quote comes from a section the regulator cited** | Chosen. It means right for the right reason, which is what the system promises, and it is zero without retrieval, so it shows what retrieval adds. Its weakness is that the regulator does not cite every relevant section, so a correct answer quoting another valid section scores as wrong; verdict accuracy, shown next to it, reveals how often. |
| Verdict accuracy alone | Simple, objective and unaffected by incomplete citations. But it counts an answer that is right for the wrong reason, and with about half the answers being yes, a coin flip scores near 50%, so real gains are harder to see. |
| A judge model grading the whole explanation against the regulator's answer | Closest to how a person would grade. But it costs money or GPU time, varies between runs, and has to be checked against the owner's labels before its numbers count. |

## Decision

**Code computes every main number, and no model judges them.** Code compares each
verdict with the regulator's, checks quotes word for word, and gets sections from passage
IDs, so scores are free, repeatable, and recomputed from stored outputs.

**Retrieval** needs no model calls.

- The gold sections are the sections the regulator cited, and a cited paragraph counts
  for its section.
- The main number is section recall@10: the share of a question's cited sections that
  appear in the top 10 passages, averaged over questions.
- Also reported: the same share at 5, 20 and 50, MRR and nDCG@10.

**Generation** runs three ways.

- **Closed-book:** no passages, showing what the model knows on its own. There is nothing
  to quote, so only the verdict is scored and the decline rule does not apply.
- **Oracle:** the passages of the sections the regulator cited, showing generation with
  perfect retrieval. For a large table section such as §172.101, the oracle gets the 10
  rows closest to the question by BM25, an approximation.
- **End-to-end:** the retrieved passages.

Its main number is the supported verdict, with verdict accuracy and the false-answer
rate, which counts a yes or no given where the system should have declined, always next
to it. Also reported, by question type: the decline rate on answerable questions,
citation precision and recall, quote failures, format failures and refusals, cost
(dollars for Claude, time for the local model) and speed.

**Comparisons.** Each experiment changes one stage and is judged by that stage's main
number, with everything else fixed. The test is a paired randomization test on
per-question scores, with a 95% interval for the difference. The number of configurations
tried is recorded.

**Run records**, one committed folder per run:

- **The run file:** the git commit and whether the tree had uncommitted changes, the
  corpus version, the gold-set checksum, the split, the full settings, model IDs or file
  checksums, the prompt version, the machine, token counts, cost and the running total,
  and for held-out runs, how many there have been so far.
- **Per question:** the top 50 passage IDs with scores, the raw output, the parsed verdict
  and quotes, each quote's check, the final verdict, time and tokens. Records hold IDs
  only, with no passage or letter text.
- **Resumable:** each question is saved as it finishes, so a run stopped by closing the
  laptop picks up where it left off.

One command builds the README's results table from the run records.

## Consequences

- The gap between oracle and end-to-end is what retrieval costs, and the gap between
  closed-book and oracle is what reading the rules adds.
- For questions about a big table, the oracle is only approximately perfect retrieval;
  results by question type show those questions separately.
- A correct answer that quotes an uncited but valid section counts as unsupported. Dev
  runs show how often the regulator's citations miss a relevant section.
- A model judge, if one is ever needed, first has its verdicts compared with labels the
  owner wrote, and the agreement is reported.
- Recording how many configurations were tried guards against finding a difference only
  because many were tested.

## References

- Kalervo Järvelin and Jaana Kekäläinen, [Cumulated Gain-Based Evaluation of IR Techniques](https://doi.org/10.1145/582415.582418) (ACM Transactions on Information Systems, 2002).
- Mark D. Smucker, James Allan and Ben Carterette, [A Comparison of Statistical Significance Tests for Information Retrieval Evaluation](https://doi.org/10.1145/1321440.1321528) (CIKM, 2007).
- Julián Urbano, Harlley Lima and Alan Hanjalic, [Statistical Significance Testing in Information Retrieval: An Empirical Analysis of Type I, Type II and Type III Errors](https://doi.org/10.1145/3331184.3331259) (SIGIR, 2019).
- Benjamin A. Carterette, [Multiple Testing in Statistical Analysis of Systems-Based Information Retrieval Experiments](https://doi.org/10.1145/2094072.2094076) (ACM Transactions on Information Systems, 2012).
- Nelson F. Liu, Tianyi Zhang and Percy Liang, [Evaluating Verifiability in Generative Search Engines](https://doi.org/10.18653/v1/2023.findings-emnlp.467) (Findings of EMNLP, 2023).
- Scott Barnett et al., [Seven Failure Points When Engineering a Retrieval Augmented Generation System](https://doi.org/10.1145/3644815.3644945) (CAIN, 2024).
- Joelle Pineau et al., [Improving Reproducibility in Machine Learning Research (A Report from the NeurIPS 2019 Reproducibility Program)](https://jmlr.org/papers/v22/20-303.html) (JMLR, 2021).
- Shreya Shankar et al., [Who Validates the Validators? Aligning LLM-Assisted Evaluation of LLM Outputs with Human Preferences](https://doi.org/10.1145/3654777.3676450) (UIST, 2024).
