<!-- Author: Nicola Antonello -->

# Experiments

Each retrieval or generation change is an experiment against a named baseline on the dev
split. Its report is written while it runs and kept when it loses. A report gives:

- the question and the hypothesis;
- related work;
- the setup;
- results overall, decided by the paired test of
  [ADR-0024](../adr/0024-paired-comparisons-cross-validated-tuning-and-adoption.md), and
  by question type as description;
- the questions that improved and regressed;
- threats to validity;
- the verdict;
- the commands that reproduce it.

Every number comes from a committed run record in `eval/runs/` or comparison record in
`eval/comparisons/`.

| # | Experiment | Baseline | Verdict | Configurations so far |
|---|---|---|---|---|

No experiment yet: the first is phase 3's dense retrieval against BM25.
