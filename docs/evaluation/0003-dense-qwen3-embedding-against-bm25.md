<!-- Author: Nicola Antonello -->

# 0003: Dense retrieval with Qwen3-Embedding against BM25

- Experiment: E3 of phase 3
- Baseline: `2026-11-24-bm25-dev-1`, BM25 with k1 1.2 and b 0.75, still the baseline
  after E1 was rejected ([0001](0001-dense-bge-base-against-bm25.md))
- The one change: the first stage is dense retrieval with Qwen/Qwen3-Embedding-0.6B
  and its query instruction instead of BM25, in float32 as E1 ran
- Configurations tried in phase 3 so far: 3

## 1. Question and hypothesis

Written on 2026-11-25, before the runs of E2 and E3, and committed with this config
before them, so the run's commit shows the prediction came first.

**Question.** Does dense retrieval with Qwen3-Embedding-0.6B raise section recall@10
over BM25 on the dev split's answerable letter questions, and on which question types?

**Hypothesis.** It comes closer to BM25 than bge-base did, but does not beat it.
Qwen3-Embedding-0.6B is about five times bge-base's size (596M parameters) and follows
an instruction, and on real questions about Korean fire-safety statutes it doubled
BM25's recall@10. But E1 showed how well BM25 matches the requesters' own regulatory
terms on this corpus.

**Prediction.** The mean difference in section recall@10 against BM25 lies above E1's
−0.073, and the paired test does not support a gain. The hypothesis is refuted if
Qwen3-Embedding beats BM25 with p < 0.05, or if its mean difference falls below −0.073.

## 2. Related work

- **This corpus.** On the same questions, bge-base lost to BM25 by 0.073 of section
  recall@10 (p = 0.0062) ([0001](0001-dense-bge-base-against-bm25.md)).
- **The same model elsewhere.** On SearchFireSafety's real questions about Korean
  fire-safety statutes, Qwen3-Embedding-0.6B reached 48.70 recall@10 against BM25's
  23.39 (Chae et al., 2026, *read-part*; full reference in 0001).
