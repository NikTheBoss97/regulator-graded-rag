<!-- Author: Nicola Antonello -->

# ADR-0020: The sample size as a sensitivity table

- Status: accepted
- Date: 2026-11-24

## Context

[ADR-0008](0008-dev-and-held-out-split.md) estimated, before any letter was read, that
dev would hold about 120 answerable questions, and that on 120 paired questions a
10-point difference between two setups would be detected roughly 60% of the time if one
question in five changes outcome between them. It left the calculation to be redone on
dev with Sakai's method. With plan 2a, on 2026-11-14, the owner chose to report it as a
sensitivity table.

Dev now holds 250 items, 214 of them answerable, and BM25's first dev run,
[2026-11-24-bm25-dev-1](../../eval/runs/2026-11-24-bm25-dev-1/), scores each answerable
question's section recall@10. Across the 214, recall@10 has a sample standard deviation
s of 0.414.

A paired test compares two setups on the same questions, so its power depends on the
spread σd of the per-question differences. When both setups' scores spread by s and
correlate by ρ, σd² = 2s²(1 − ρ), and ρ is unknown until a second setup runs.

## Options

| Option | Verdict |
|---|---|
| A table of the minimum detectable difference for a range of assumed ρ, and for yes-or-no scores by the share of questions that change outcome | Chosen: it shows how much the answer depends on the one unknown |
| One required sample size, from an assumed effect and ρ | Rejected: it hides that assumption, and dev's size is fixed by the letters anyway |
| A bootstrap or simulation from BM25's scores | Rejected: one setup's scores cannot show how a second setup's will correlate with them |

## Decision

The minimum detectable difference (MDD) is the smallest true mean difference that a
two-sided paired t-test on n questions detects at α 0.05 with power 0.8:

MDD = (z₀.₉₇₅ + z₀.₈₀) · σd / √(n − z₀.₉₇₅²/2)

This is the paired t-test design of Sakai's topic set size design, solved for the
difference; the z₀.₉₇₅²/2 term corrects the normal approximation for the t test. The
project compares setups with a paired randomization test (ADR-0012), and the t-test's
power is taken for its power: on per-question scores the two tests largely agree, and
both hold their error rates (Smucker et al.; Urbano et al.).
`python -m regulator_graded_rag.power eval/runs/<name>` prints it from a dev run's
per-question recall@10, for ρ of 0, 0.3, 0.5 and 0.7, and for a yes-or-no score, such as
the supported verdict, with σd = √d for a share d of questions whose outcome changes
between the two setups. It also checks the answerable count against the 120 the design
expected, and refuses a held-out run without opening its scores. On BM25's dev run, with
n = 214 and s = 0.414:

| Assumption | σd | MDD |
|---|---:|---:|
| ρ = 0 | 0.586 | 0.113 |
| ρ = 0.3 | 0.490 | 0.094 |
| ρ = 0.5 | 0.414 | 0.080 |
| ρ = 0.7 | 0.321 | 0.062 |
| d = 0.1 | 0.316 | 0.061 |
| d = 0.2 | 0.447 | 0.086 |
| d = 0.3 | 0.548 | 0.105 |

## Consequences

- **No shortfall.** Dev has 214 answerable questions against the 120 expected, so the
  2017 cut-off stays.
- **What dev can tell apart.** Two setups whose recall@10 differs by less than about 6
  to 11 points, depending on ρ, may not differ significantly: such a result reads as
  "too small to see", never as "no difference". For ADR-0008's case, one question in
  five changing outcome, the same formula gives 11.5 points on the 120 questions it
  estimated and 8.6 points on the 214 dev has; at 120, a 10-point difference would have
  power 0.68, where ADR-0008 estimated about 60%.
- **Phase 3 measures the spread.** Its first dense run gives the actual spread of the
  per-question differences against BM25, and an amendment here replaces the assumed rows
  with it.
- **Held-out is left out.** Its only job is one final estimate (ADR-0008).
- **Checked.** The power of the two-sided paired t-test at each MDD, computed exactly
  from the noncentral t distribution, is 0.800 at n = 214 and 0.792 at n = 10; without
  the z₀.₉₇₅²/2 term it would be 0.796 and 0.704. A unit test keeps this.
- **Unverified.** The abstracts confirm that Sakai's design rests on the paired t-test,
  through Nagata's techniques, and that Guenther gives approximate t-test sample sizes
  from normal quantiles alone. Neither full text could be read, so which of them states
  the z₀.₉₇₅²/2 term was not checked; the exact power above stands in for it.

## References

- Tetsuya Sakai, [Topic Set Size Design](https://doi.org/10.1007/s10791-015-9273-z)
  (Information Retrieval Journal, 2015): the number of test questions worked out from
  statistical requirements, with a paired t-test design among its three.
- Tetsuya Sakai, [Laboratory Experiments in Information Retrieval: Sample Sizes, Effect
  Sizes, and Statistical Power](https://doi.org/10.1007/978-981-13-1199-4) (Springer,
  2018): how to plan and report an experiment statistically, including how many
  questions it needs.
- Julián Urbano, Harlley Lima and Alan Hanjalic, [Statistical Significance Testing in
  Information Retrieval: An Empirical Analysis of Type I, Type II and Type III
  Errors](https://doi.org/10.1145/3331184.3331259) (SIGIR, 2019): over 500 million
  simulated p-values, the t-test and the permutation test hold their error rates.
- Mark D. Smucker, James Allan and Ben Carterette, [A Comparison of Statistical
  Significance Tests for Information Retrieval Evaluation](https://doi.org/10.1145/1321440.1321528)
  (CIKM, 2007): the t-test, bootstrap and randomization tests largely agree.
- William C. Guenther, [Sample Size Formulas for Normal Theory *T*
  Tests](https://doi.org/10.1080/00031305.1981.10479363) (The American Statistician
  35(4), 243–244, 1981): approximate minimum sample sizes for t tests from normal
  quantiles alone, usually equal to the exact ones.
