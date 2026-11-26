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
| [0001](0001-dense-bge-base-against-bm25.md) | Dense retrieval with bge-base-en-v1.5 | BM25, `2026-11-24-bm25-dev-1` | Rejected: section recall@10 −0.073 (95% interval −0.125 to −0.021), p = 0.0062 | 1 |
| [0002](0002-dense-gte-modernbert-against-bm25.md) | Dense retrieval with gte-modernbert-base | BM25, `2026-11-24-bm25-dev-1` | Rejected: section recall@10 −0.079 (95% interval −0.138 to −0.021), p = 0.0083 | 2 |
| [0003](0003-dense-qwen3-embedding-against-bm25.md) | Dense retrieval with Qwen3-Embedding-0.6B | BM25, `2026-11-24-bm25-dev-1` | Rejected: section recall@10 −0.065 (95% interval −0.117 to −0.014), p = 0.013 | 3 |
| [0004](0004-hybrid-rrf-qwen3-embedding-against-bm25.md) | Hybrid: BM25 and Qwen3-Embedding fused by RRF, k by cross-validation | BM25, `2026-11-24-bm25-dev-1` | Inconclusive: section recall@10 +0.006 (95% interval −0.031 to +0.043), p = 0.74 | 4 |
