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

## 3. Setup

- **Stages:** BM25 with k1 1.2 and b 0.75, the baseline's own stage, and
  Qwen3-Embedding-0.6B exactly as E3 ran it (report 0003): revision
  `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, its stored query instruction, up to 8,192
  tokens, float32, vectors SHA-256 `d15a9078ec8fc247ac72f005025347d25a240df8e08d089acebba08d49cc1ca8`.
  Each keeps its top 50 passages per question.
- **Fusion:** over the union of the two top-50 lists, a passage scores the sum of
  1/(k + rank) over the lists it is in, with ranks counted from 1. Ties keep BM25's
  order, then the dense list's, and the top 50 are kept.
- **Tuning:** k is chosen from 10, 30, 60 and 100 by 5-fold cross-validation on dev
  (ADR-0024). Within each question type, items are ordered by the SHA-256 of
  `phase-3-folds-2026-11-25:<item id>` and dealt into five folds; each fold gets the
  value with the highest mean recall@10 over the other four folds' answerable questions,
  ties going to the first value in grid order. Folds 0 and 4 chose k = 60, and folds 1,
  2 and 3 chose k = 10, so 85 of the 214 scored questions ran with k = 60 and 129 with
  k = 10. On all of dev the choice is 60, the value phase 4 would use.
- **Config:** `eval/configs/hybrid-rrf-qwen3-embedding.toml`, run through the pipeline
  of [ADR-0023](../adr/0023-experiments-as-configs-run-by-one-cached-pipeline.md).
- **Runs:** the baseline `2026-11-24-bm25-dev-1` ran at commit `5cf37c3` (tree
  `68e22c96`); this experiment's `2026-11-26-hybrid-rrf-qwen3-embedding-dev-1` ran at
  commit `c3b844e` (tree `67ea0e56`), with no uncommitted changes to tracked files. That
  commit holds this report's question, hypothesis and related work, and the config.
  Both runs used corpus version `ecaac596…` and gold set `7bfdfdf9…`: 250 dev items, 214
  of them answerable and scored.
- **Decision:** the paired randomization test of ADR-0024 on per-question section
  recall@10, 100,000 sign flips from the seed `phase-3-paired-2026-11-25`, and a 95%
  t-interval for the mean difference.
- **Machine and cost:** the Windows laptop with an RTX 4070 Laptop GPU (8 GB), Python
  3.14.7; the run record names the GPU and torch's and CUDA's versions. Everything ran
  locally, at no cost, on an idle machine. The run took 38 s: each stage answered each
  question once, and every value of k reused those answers through the cache.

## 4. Results

| Questions | n | Run | R@5 | R@10 | R@20 | R@50 | MRR | nDCG@10 |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| all | 214 | BM25 | 0.610 | 0.691 | 0.761 | 0.856 | 0.575 | 0.558 |
|  |  | RRF hybrid | 0.610 | 0.697 | 0.788 | 0.854 | 0.580 | 0.566 |
| lookup | 122 | BM25 | 0.639 | 0.721 | 0.779 | 0.869 | 0.514 | 0.559 |
|  |  | RRF hybrid | 0.623 | 0.730 | 0.844 | 0.885 | 0.518 | 0.561 |
| multi_passage | 49 | BM25 | 0.452 | 0.547 | 0.649 | 0.793 | 0.570 | 0.454 |
|  |  | RRF hybrid | 0.479 | 0.555 | 0.649 | 0.779 | 0.576 | 0.470 |
| table | 43 | BM25 | 0.707 | 0.770 | 0.838 | 0.893 | 0.754 | 0.675 |
|  |  | RRF hybrid | 0.722 | 0.768 | 0.789 | 0.850 | 0.759 | 0.688 |

The difference in section recall@10, the RRF hybrid minus BM25:

| Questions | n | Difference | 95% interval |
|---|---:|---:|---|
| all | 214 | +0.006 | [−0.031, +0.043] |
| lookup | 122 | +0.008 | [−0.051, +0.067] |
| multi_passage | 49 | +0.009 | [−0.054, +0.071] |
| table | 43 | −0.002 | [−0.040, +0.037] |

- **The paired randomization test gives p = 0.74.** The hybrid's recall@10 is 0.006
  above BM25's, well inside the noise. The results by type are description, not tests.
- The spread of the per-question differences is 0.274, so the smallest difference this
  sample detects at power 0.8 is 0.053; a gain that large lies outside the 95%
  interval.
- As description, the hybrid lifts passages from ranks 11 to 20 into the top 20
  (recall@20 0.788 against 0.761), while recall@5 and recall@50 stay level.
- **Latency per question:** median 0.140 s and 95th percentile 0.236 s for BM25,
  Qwen3-Embedding and the fusion together, against 0.050 s and 0.112 s for BM25 alone.

## 5. Flips

15 questions improved and 14 regressed; the comparison record lists them. The last three
columns use report 0001's rule: each question is sorted by its first match, a section
number of Parts 171 to 180 (`\b1(?:7[1-9]|80)\.\d+`), then a UN or NA identification
number (`\b(?:UN|NA)\s?\d{4}\b`), else neither.

| Questions | All | lookup | multi_passage | table | A section number in the question | A UN or NA number | Neither |
|---|---:|---:|---:|---:|---:|---:|---:|
| Improved | 15 | 7 | 6 | 2 | 11 | 1 | 3 |
| Regressed | 14 | 6 | 5 | 3 | 5 | 1 | 8 |
| All answerable | 214 | 122 | 49 | 43 | 130 | 16 | 68 |

- **Questions without an explicit number regress more often,** as with the dense models
  alone: 8 of the 14 regressions against 32% of all questions. Questions naming a
  section make up 11 of the 15 improvements.
- No regression lost every cited section from the top 50.

Seven regressions, read in full, show one failure pattern:

- **A section that only BM25 ranks high falls below passages both rankings find.** RRF
  adds a term for each list a passage is in, so passages that both rankings place
  fairly high outscore one that BM25 alone places high, and more so as k grows. With
  k = 60, the driver's licence rule §177.816, which BM25 ranked first for 22-0086-Q1 and
  Qwen3-Embedding left out of its top 50, fell to 29th. §173.56 (21-0009-Q3) fell from
  BM25's 6th to 11th and §173.241 (18-0009-Q2) from 7th to 15th, both missing from the
  dense top 50, and §179.7 (20-0039-Q2) from 4th to 12th, which the dense model ranked
  33rd. With k = 10 the same happens where the dense ranking is lower than BM25's:
  §173.301 (24-0042-Q2) went from 5th, and 10th in the dense list, to 13th, and §171.8
  (18-0081-Q1 and Q3) from 9th and 7th to 14th and 11th.

The other 7 regressions were classified by the table above, not read one by one.

## 6. Threats to validity

- **One dense model.** E4 fuses BM25 with Qwen3-Embedding, picked by a rule whose margin
  is noise. A dense model that missed fewer of BM25's best passages could fuse
  differently.
- **The record keeps the choices, not the scores.** The run file records each fold's k
  and the value chosen on all of dev, not each value's mean recall@10, so how close the
  other values came is not published.
- **Questions from one letter are not independent.** Flipping all of a letter's
  questions together, with ADR-0024's test over each letter's summed differences
  (`compare.letter_sums`), gives p = 0.76: the result holds. This check is reported
  beside ADR-0024's decision, not as part of it.
- **The questions are written by professionals,** and **the labels are the regulator's
  citations,** as in reports 0001 to 0003.
- **Latency depends on the machine's load.** This run's machine was idle, and each
  question's time is what its stages took to compute it, measured once and reused for
  every value of k.
- **Dev split only.** Cross-validation chose each question's k without that question,
  so its score is not inflated by the choice, but the held-out split has not been run.

## 7. Verdict

**Inconclusive.** The RRF hybrid raises section recall@10 by 0.006 (95% interval −0.031
to +0.043, p = 0.74), so by ADR-0024 the simpler, cheaper setup stays: BM25 remains the
baseline. The hypothesis held: the test supports no gain. The hybrid would also cost a
GPU and 0.09 s more per question. Configurations tried in phase 3 so far: 4.

## 8. Reproduction

From the repository root, with the database running and `DATABASE_URL` set as in
`.env.example`, and the corpus fetched and parsed as the README's quickstart shows. The
first command builds the passage index, and does nothing when the index already holds
the corpus; `--download` fetches Qwen3-Embedding's weights, about 1.2 GB, when they are
not cached.

```
uv run --env-file .env python -m regulator_graded_rag.index
uv sync --group models
uv run --group models --env-file .env python -m regulator_graded_rag.embed --config eval/configs/dense-qwen3-embedding.toml --download
uv run --group models --env-file .env python -m regulator_graded_rag.run --split dev --config eval/configs/hybrid-rrf-qwen3-embedding.toml
uv run python -m regulator_graded_rag.compare 2026-11-24-bm25-dev-1 2026-11-26-hybrid-rrf-qwen3-embedding-dev-1
```

A rerun writes a new run folder and deals the same folds from the same seed. The
comparison record recomputes byte for byte from the two committed runs, which a unit test
checks.

## References

- Sebastian Bruch, Siyu Gai and Amir Ingber, [An Analysis of Fusion Functions for Hybrid Retrieval](https://doi.org/10.1145/3596512) (ACM Transactions on Information Systems, 2023).
- Kyubyung Chae, Jewon Yeom, Jeongjae Park, Seunghyun Bae, Ijun Jang, Hyunbin Jin, Jinkwan Jang and Taesup Kim, [Beyond Case Law: Evaluating Structure-Aware Retrieval and Safety in Statute-Centric Legal QA](https://arxiv.org/abs/2604.06173) (arXiv, 2026).
- Gordon V. Cormack, Charles L. A. Clarke and Stefan Buettcher, [Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods](https://doi.org/10.1145/1571941.1572114) (SIGIR, 2009).
