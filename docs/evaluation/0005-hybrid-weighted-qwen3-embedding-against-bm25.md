<!-- Author: Nicola Antonello -->

# 0005: Hybrid retrieval, BM25 and Qwen3-Embedding fused by a weighted sum

- Experiment: E5 of phase 3
- Baseline: `2026-11-24-bm25-dev-1`, BM25 with k1 1.2 and b 0.75, still the baseline
  after E1, E2 and E3 were rejected; E4 runs beside this experiment, and each is
  compared with BM25
- The one change: the first stage is BM25 together with Qwen3-Embedding-0.6B, as in E4,
  fused by α times the dense score plus 1 − α times BM25's, each min-max normalized over
  its own top 50, with α chosen by 5-fold cross-validation on dev from 0.0 to 1.0 in
  steps of 0.1 (ADR-0024)
- The dense model: Qwen3-Embedding, by the rule report 0004 states
- Configurations tried in phase 3 so far: 5, a cross-validated method counting as one

## 1. Question and hypothesis

Written on 2026-11-26, before the runs of E4 and E5, and committed with this config
before them, so the run's commit shows the prediction came first.

**Question.** Does a weighted sum of BM25's and Qwen3-Embedding's scores, with its
weight chosen by cross-validation, raise section recall@10 over BM25 alone on the dev
split's answerable letter questions?

**Hypothesis.** Cross-validation leans the sum on BM25, the stronger ranking, and the
result does not beat BM25 by more than this sample can detect. α = 0 gives exactly
BM25's ranking, so the method can fall back to it.

**Prediction.** Every fold chooses α of 0.5 or less, and the paired test does not
support a gain over BM25: p is 0.05 or more, or the mean difference is 0 or below. As
description, not a test, E5's difference against BM25 is above E4's, as Bruch et al.
found the convex combination above RRF. The hypothesis is refuted if any fold chooses α
above 0.5, or if E5 beats BM25 with p < 0.05 and a positive mean difference.

## 2. Related work

- **A convex combination beats RRF and needs few examples.** Bruch et al. found a
  convex combination of lexical and semantic scores better than reciprocal rank fusion
  in and out of domain, generally agnostic to the score normalization chosen, and tuned
  from a small set of examples (Bruch et al., 2023, *read-part*).
- **This corpus.** Alone, Qwen3-Embedding is 0.065 below BM25 in section recall@10
  (report 0003), and E4 tests RRF on the same two stages (report 0004).

*read-part*: the abstract was read, not the whole paper.

## References

- Sebastian Bruch, Siyu Gai and Amir Ingber, [An Analysis of Fusion Functions for Hybrid Retrieval](https://doi.org/10.1145/3596512) (ACM Transactions on Information Systems, 2023).
