<!-- Author: Nicola Antonello -->

# 0002: Dense retrieval with gte-modernbert against BM25

- Experiment: E2 of phase 3
- Baseline: `2026-11-24-bm25-dev-1`, BM25 with k1 1.2 and b 0.75, still the baseline
  after E1 was rejected ([0001](0001-dense-bge-base-against-bm25.md))
- The one change: the first stage is dense retrieval with
  Alibaba-NLP/gte-modernbert-base instead of BM25, in float32 as E1 ran
- Configurations tried in phase 3 so far: 2

## 1. Question and hypothesis

Written on 2026-11-25, before the runs of E2 and E3, and committed with this config
before them, so the run's commit shows the prediction came first.

**Question.** Does dense retrieval with gte-modernbert-base raise section recall@10 over
BM25 on the dev split's answerable letter questions, and on which question types?

**Hypothesis.** It does not. E1 found bge-base 7.3 points below BM25, losing most on
multi-passage questions and on questions without an explicit section or UN number.
gte-modernbert-base is a general English model of a similar size (149M parameters).
Its newer architecture and its longer input should help little here, since only 20
passages exceed even bge-base's 512 tokens.

**Prediction.** The mean difference in section recall@10 against BM25 is negative, and
of a similar size to E1's. The hypothesis is refuted if the mean difference is zero or
positive.

## 2. Related work

- **This corpus.** On the same questions, bge-base lost to BM25 by 0.073 of section
  recall@10 (p = 0.0062) ([0001](0001-dense-bge-base-against-bm25.md)).
- **Other corpora.** The studies 0001 summarises found large dense gains on real
  regulatory questions, with models larger than gte-modernbert-base, and small
  differences on questions generated from the passages.
