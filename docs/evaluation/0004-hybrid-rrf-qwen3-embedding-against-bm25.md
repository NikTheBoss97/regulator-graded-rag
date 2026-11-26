<!-- Author: Nicola Antonello -->

# 0004: Hybrid retrieval, BM25 and Qwen3-Embedding fused by RRF

- Experiment: E4 of phase 3
- Baseline: `2026-11-24-bm25-dev-1`, BM25 with k1 1.2 and b 0.75, still the baseline
  after E1, E2 and E3 were rejected
- The one change: the first stage is BM25 together with Qwen3-Embedding-0.6B, as E3 ran
  it, fused by reciprocal rank fusion, with its constant k chosen by 5-fold
  cross-validation on dev from 10, 30, 60 and 100 (ADR-0024)
- The dense model: none was adopted, so the plan's rule takes the one with the highest
  dev recall@10, Qwen3-Embedding at 0.626 against 0.618 for bge-base and 0.612 for
  gte-modernbert. Its lead over bge-base, 0.007, is far below what the sample detects;
  the owner kept the rule on 2026-11-26, since it was fixed before any result.
- Configurations tried in phase 3 so far: 4, a cross-validated method counting as one

## 1. Question and hypothesis

Written on 2026-11-26, before the runs of E4 and E5, and committed with this config
before them, so the run's commit shows the prediction came first.

**Question.** Does fusing BM25 with Qwen3-Embedding by reciprocal rank fusion raise
section recall@10 over BM25 alone on the dev split's answerable letter questions?

**Hypothesis.** It does not. RRF gives the two rankings equal say, and here the dense
ranking is the weaker one: alone, Qwen3-Embedding is 0.065 below BM25 (report 0003).
The committed runs of BM25 and E3 already show the risk: BM25's top 5 passages together
with Qwen3-Embedding's top 5 hold 0.676 of the cited sections, against 0.691 in BM25's
own top 10.

**Prediction.** The paired test does not support a gain over BM25: p is 0.05 or more,
or the mean difference is 0 or below. The hypothesis is refuted if E4 beats BM25 with
p < 0.05 and a positive mean difference.

## 2. Related work

- **RRF depends on its constant, and a convex combination beats it.** Bruch et al.
  found reciprocal rank fusion sensitive to its parameters, and a convex combination of
  lexical and semantic scores better in and out of domain, tuned from a small set of
  examples (Bruch et al., 2023, *read-part*). E5 tests that combination on the same
  stages.
- **RRF with a weak second ranking lowers the stronger one.** On SearchFireSafety's
  real questions about Korean fire-safety statutes, fusing BM25 (recall@10 23.39) into
  Qwen3-Embedding-0.6B by RRF lowered its recall@10 from 48.70 to 45.13, and into
  BGE-M3 from 53.77 to 49.77; the authors suggest that rank fusion adds noise when the
  auxiliary ranking is weak (Chae et al., 2026, *read-part*). Here the roles are
  reversed: BM25 is the stronger ranking.
- **Where RRF comes from.** Cormack et al. combined rankings by rank alone, so the
  scores need no calibration (Cormack et al., 2009, *not read*: cited from the reading
  list).

*read-part*: the abstract and the sections reporting these results were read, not the
whole paper.

## References

- Sebastian Bruch, Siyu Gai and Amir Ingber, [An Analysis of Fusion Functions for Hybrid Retrieval](https://doi.org/10.1145/3596512) (ACM Transactions on Information Systems, 2023).
- Kyubyung Chae, Jewon Yeom, Jeongjae Park, Seunghyun Bae, Ijun Jang, Hyunbin Jin, Jinkwan Jang and Taesup Kim, [Beyond Case Law: Evaluating Structure-Aware Retrieval and Safety in Statute-Centric Legal QA](https://arxiv.org/abs/2604.06173) (arXiv, 2026).
- Gordon V. Cormack, Charles L. A. Clarke and Stefan Buettcher, [Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods](https://doi.org/10.1145/1571941.1572114) (SIGIR, 2009).
