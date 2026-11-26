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

## 3. Setup

- **Stages:** E4's: BM25 with k1 1.2 and b 0.75, and Qwen3-Embedding-0.6B as E3 ran it,
  vectors SHA-256 `d15a9078ec8fc247ac72f005025347d25a240df8e08d089acebba08d49cc1ca8`.
  Each keeps its top 50 passages per question.
- **Fusion:** over the union of the two top-50 lists, a passage scores α times its
  dense score plus 1 − α times its BM25 score, each min-max normalized over its own list
  for the question. A passage missing from a list scores 0 there, and so does every
  passage of a list whose scores are all equal. Ties keep BM25's order, then the dense
  list's, and the top 50 are kept.
- **Tuning:** α is chosen from 0.0 to 1.0 in steps of 0.1 by 5-fold cross-validation
  on dev, with E4's folds and rule (ADR-0024). Every fold chose α = 0.3, and so did all
  of dev.
- **Config:** `eval/configs/hybrid-weighted-qwen3-embedding.toml`, run through the
  pipeline of [ADR-0023](../adr/0023-experiments-as-configs-run-by-one-cached-pipeline.md).
- **Runs:** the baseline `2026-11-24-bm25-dev-1` ran at commit `5cf37c3` (tree
  `68e22c96`); this experiment's `2026-11-26-hybrid-weighted-qwen3-embedding-dev-1` ran
  at commit `c3b844e` (tree `67ea0e56`), with no uncommitted changes to tracked files,
  right after E4's. That commit holds this report's question, hypothesis and related
  work, and the config. Both runs used corpus version `ecaac596…` and gold set
  `7bfdfdf9…`: 250 dev items, 214 of them answerable and scored.
- **Decision:** the paired randomization test of ADR-0024 on per-question section
  recall@10, 100,000 sign flips from the seed `phase-3-paired-2026-11-25`, and a 95%
  t-interval for the mean difference.
- **Machine and cost:** the Windows laptop with an RTX 4070 Laptop GPU (8 GB), Python
  3.14.7, idle. Everything ran locally, at no cost. The stages' answers came from E4's
  run through the cache, so each question's time is the seconds its stages took there
  plus the weighted sum's own.

## 4. Results

| Questions | n | Run | R@5 | R@10 | R@20 | R@50 | MRR | nDCG@10 |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| all | 214 | BM25 | 0.610 | 0.691 | 0.761 | 0.856 | 0.575 | 0.558 |
|  |  | weighted hybrid | 0.632 | 0.702 | 0.782 | 0.870 | 0.586 | 0.571 |
| lookup | 122 | BM25 | 0.639 | 0.721 | 0.779 | 0.869 | 0.514 | 0.559 |
|  |  | weighted hybrid | 0.672 | 0.738 | 0.811 | 0.902 | 0.537 | 0.579 |
| multi_passage | 49 | BM25 | 0.452 | 0.547 | 0.649 | 0.793 | 0.570 | 0.454 |
|  |  | weighted hybrid | 0.446 | 0.548 | 0.659 | 0.779 | 0.553 | 0.452 |
| table | 43 | BM25 | 0.707 | 0.770 | 0.838 | 0.893 | 0.754 | 0.675 |
|  |  | weighted hybrid | 0.729 | 0.778 | 0.838 | 0.885 | 0.765 | 0.682 |

The difference in section recall@10, the weighted hybrid minus BM25:

| Questions | n | Difference | 95% interval |
|---|---:|---:|---|
| all | 214 | +0.011 | [−0.007, +0.029] |
| lookup | 122 | +0.016 | [−0.006, +0.039] |
| multi_passage | 49 | +0.002 | [−0.052, +0.055] |
| table | 43 | +0.008 | [−0.008, +0.023] |

- **The paired randomization test gives p = 0.23.** The hybrid's recall@10 is 0.011
  above BM25's, inside the noise. The results by type are description, not tests.
- The spread of the per-question differences is 0.133, smaller than for any experiment
  so far, so the smallest difference this sample detects at power 0.8 is 0.026: the
  weighted sum changes few questions, 11 against E4's 29.
- As description, the hybrid is at or above BM25 at every cutoff and on every metric
  overall, and above E4 at 5, 10 and 50. Its difference against BM25, +0.011, is above
  E4's +0.006, as predicted.
- **Each α, fixed for every question,** recomputed from the committed BM25 and E3 runs,
  whose hits are this run's two stages: α = 0.3 scores best on all of dev, 0.702, the
  value every fold chose. α = 0 gives BM25's 0.691 exactly, the other values from 0.1 to
  0.6 score from 0.687 to 0.697, and the score falls as the dense weight grows past 0.6,
  to 0.626 at α = 1, Qwen3-Embedding's own; α = 0.9 and 1 are below BM25 with p = 0.013.
- **Latency per question:** median 0.140 s and 95th percentile 0.236 s for BM25,
  Qwen3-Embedding and the fusion together, against 0.050 s and 0.112 s for BM25 alone.

## 5. Flips

7 questions improved and 4 regressed; the comparison record lists them. The last three
columns use report 0001's rule: each question is sorted by its first match, a section
number of Parts 171 to 180 (`\b1(?:7[1-9]|80)\.\d+`), then a UN or NA identification
number (`\b(?:UN|NA)\s?\d{4}\b`), else neither.

| Questions | All | lookup | multi_passage | table | A section number in the question | A UN or NA number | Neither |
|---|---:|---:|---:|---:|---:|---:|---:|
| Improved | 7 | 2 | 4 | 1 | 5 | 1 | 1 |
| Regressed | 4 | 0 | 4 | 0 | 3 | 0 | 1 |
| All answerable | 214 | 122 | 49 | 43 | 130 | 16 | 68 |

- **The dense scores lift a cited section BM25 ranked lower.** In four improvements
  read in full, §173.307 (25-0133-Q1) rose from BM25's 14th to 4th, §175.75 (24-0047-Q2)
  from 21st to 5th, §171.1 (22-0038-Q2) from 28th to 10th, and §177.834 (19-0066-Q4)
  from 36th to 8th, while BM25's top passages mostly kept their places.
- **All four regressions are multi-passage questions** that lost one of their several
  cited sections from the top 10; none lost them all from the top 50. In the one read in
  full, 18-0027-Q2, §171.8 went from BM25's 2nd to 3rd and §173.421 from 5th to 4th,
  while §173.25 fell from 6th to 14th and §173.403 from 38th to outside the top 50.

The other 3 improvements and 3 regressions were classified by the table above, not read
one by one.

## 6. Threats to validity

- **One dense model.** E5 fuses BM25 with Qwen3-Embedding, picked by a rule whose margin
  is noise; another dense model might take another weight.
- **The record keeps the choices, not the scores.** The run file records each fold's α,
  all 0.3, and not each value's mean recall@10, so how close the other weights came is
  not published.
- **Questions from one letter are not independent.** Flipping all of a letter's
  questions together, with ADR-0024's test over each letter's summed differences
  (`compare.letter_sums`), gives p = 0.23: the result holds. This check is reported
  beside ADR-0024's decision, not as part of it.
- **The questions are written by professionals,** and **the labels are the regulator's
  citations,** as in reports 0001 to 0004.
- **Latency depends on the machine's load.** The stages' times were measured on the
  idle laptop in E4's run and reused through the cache.
- **Dev split only.** Cross-validation chose each question's α without that question,
  so its score is not inflated by the choice, but the held-out split has not been run.

## 7. Verdict

**Inconclusive.** The weighted hybrid raises section recall@10 by 0.011 (95% interval
−0.007 to +0.029, p = 0.23), so by ADR-0024 the simpler, cheaper setup stays: BM25
remains the baseline, and the rerankers that follow run over it. The hypothesis held:
every fold chose α = 0.3, at most 0.5, and the test supports no gain. The hybrid would
also cost a GPU and 0.09 s more per question. Configurations tried in phase 3 so far: 5.

## 8. Reproduction

From the repository root, after E4's reproduction, whose embedding step this run's
dense stage needs; its stage answers come from that run's cache when it is still there.

```
uv run --group models --env-file .env python -m regulator_graded_rag.run --split dev --config eval/configs/hybrid-weighted-qwen3-embedding.toml
uv run python -m regulator_graded_rag.compare 2026-11-24-bm25-dev-1 2026-11-26-hybrid-weighted-qwen3-embedding-dev-1
```

A rerun writes a new run folder and deals the same folds from the same seed. The
comparison record recomputes byte for byte from the two committed runs, which a unit test
checks.

## References

- Sebastian Bruch, Siyu Gai and Amir Ingber, [An Analysis of Fusion Functions for Hybrid Retrieval](https://doi.org/10.1145/3596512) (ACM Transactions on Information Systems, 2023).
