<!-- Author: Nicola Antonello -->

# ADR-0024: Paired comparisons, cross-validated tuning and adoption

- Status: accepted
- Date: 2026-11-25

## Context

[ADR-0012](0012-main-numbers-and-run-records.md) decides that a difference between two
setups counts only when a paired randomization test on per-question scores supports it,
with a 95% interval, but leaves the test's details open.
[ADR-0020](0020-sample-size-as-a-sensitivity-table.md) shows that 214 answerable dev
questions detect a recall@10 difference of about 6 to 11 points. Phase 3 also has three
settings to choose (the fusion weight, the reciprocal rank fusion constant and the
reranking depth), and the dev questions are both where they would be chosen and where
they are scored.

## Options

| Question | Chosen | Rejected |
|---|---|---|
| How settings are chosen | 5-fold cross-validation on dev (the owner, 2026-11-24) | Published defaults: nothing fitted, but a tuned weight may do better. A grid searched on all of dev: the search inflates the winner's score |
| The interval | Student's t, matching ADR-0020's t-based sample size | A bootstrap interval, which Bowyer et al. find covers less than its nominal level on small sets; inverting the randomization test, which is exact but harder to explain and to compute |
| What the test covers | The main number, once per comparison | A test per question type, which multiplies the chances of a false difference |

## Decision

**The comparison.** On the answerable questions both runs scored, the difference is B's
section recall@10 minus A's, question by question.

- The mean difference has a 95% interval of the mean ± t₀.₉₇₅,ₙ₋₁ · s / √n, where s is
  the standard deviation of the per-question differences (ADR-0020's s is that of
  recall@10 itself).
- The two-sided p-value comes from 100,000 random sign flips of the differences, drawn
  with Python's `random.Random` from the committed seed `phase-3-paired-2026-11-25`, so
  the same draws can be regenerated. p = (1 + the number of draws at least as far from
  zero as the observed sum) / (1 + 100,000), so p is never 0.
- To regenerate the draws: the differences are taken in item-ID order, each draw is one
  `getrandbits(n)` call, and bit i flips the i-th difference. Python guarantees the
  sequence of `random()` across versions but not that of `getrandbits()`, so a test pins
  a known p-value, and a change would fail it rather than change the draws silently.
- Results by question type are description only.
- The record also gives the spread of the differences and the minimum detectable
  difference it implies, and the questions that improved and regressed.
- Only complete dev runs are compared, and runs on different corpus or gold-set versions
  are refused. A held-out comparison comes with the owner's single held-out run
  (ADR-0014).
- `python -m regulator_graded_rag.compare` writes each comparison to
  `eval/comparisons/`, and a test recomputes every committed one byte for byte.

**Adoption.** A change is adopted when p < 0.05 and the mean difference is positive, and
rejected when p < 0.05 and it is negative. Otherwise it is inconclusive, and the simpler,
cheaper setup stays. Every report names the current baseline and also shows BM25's row.

**Cross-validated tuning.**

- Folds: within each question type, items are ordered by the SHA-256 of
  `phase-3-folds-2026-11-25:<item id>` and dealt in turn into 5 folds.
- For each fold, the setting with the highest mean recall@10 on the other four folds'
  answerable items is applied to that fold's items; ties go to the first value in the
  grid's order. Unanswerable items are searched with their fold's setting and never
  scored.
- The setting phase 4 uses is chosen on all of dev.
- A cross-validated method counts as one configuration, and its run record lists the
  grid, the seed and each fold's choice.

**The grids, fixed before any run:** the fusion weight 0.0 to 1.0 in steps of 0.1;
reciprocal rank fusion's constant 10, 30, 60 or 100; the reranking depth 10, 20, 30 or
50.

## Consequences

- Each question's score from a tuned method comes from settings chosen without it, so
  the tuned methods' dev numbers are honest estimates rather than best-of-grid scores.
- The fixed seed lets later analyses replay exactly the same draws, for example with
  edited gold labels.
- With 100,000 draws the smallest possible p is about 1 in 100,000, far below 0.05.
- Bowyer et al. find that intervals from the central limit theorem and the bootstrap
  cover less than their nominal 95% on small evaluation sets (92.5% at 100 binary
  scores). Whether the t-interval on recall@10 falls short at n = 214, or at the 43 to
  122 questions of a type, is not measured. Verdicts rest on the randomization test,
  which needs no normal approximation.
- Eight adoption decisions run in sequence, each in effect a one-sided test at 2.5%, so
  if no change truly helped, the chance of at least one false adoption would be about
  18% (1 − 0.975⁸). The single held-out run is the check.
- Small true gains will often read as inconclusive, since the detectable difference is 6
  to 11 points of recall@10.

## References

- Mark D. Smucker, James Allan and Ben Carterette, [A Comparison of Statistical Significance Tests for Information Retrieval Evaluation](https://doi.org/10.1145/1321440.1321528) (CIKM, 2007).
- Julián Urbano, Harlley Lima and Alan Hanjalic, [Statistical Significance Testing in Information Retrieval: An Empirical Analysis of Type I, Type II and Type III Errors](https://doi.org/10.1145/3331184.3331259) (SIGIR, 2019).
- Sebastian Bruch, Siyu Gai and Amir Ingber, [An Analysis of Fusion Functions for Hybrid Retrieval](https://doi.org/10.1145/3596512) (ACM Transactions on Information Systems, 2023).
- Evan Miller, [Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations](https://arxiv.org/abs/2411.00640) (arXiv, 2024).
- Sam Bowyer, Laurence Aitchison and Desi R. Ivanova, [Position: Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints](https://arxiv.org/abs/2503.01747) (ICML, 2025).
