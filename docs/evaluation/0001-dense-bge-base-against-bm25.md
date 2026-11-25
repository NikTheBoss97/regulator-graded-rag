<!-- Author: Nicola Antonello -->

# 0001: Dense retrieval with bge-base against BM25

- Experiment: E1 of phase 3
- Baseline: `2026-11-24-bm25-dev-1`, BM25 with k1 1.2 and b 0.75 ([ADR-0005](../adr/0005-bm25-written-in-sql.md))
- The one change: the first stage is dense retrieval with BAAI/bge-base-en-v1.5 instead of BM25
- Configurations tried in phase 3 so far: 1

## 1. Question and hypothesis

Written on 2026-11-25, before the run.

**Question.** Does dense retrieval with bge-base-en-v1.5 raise section recall@10 over BM25
on the dev split's answerable letter questions, and on which question types?

**Hypothesis.** It does. The letters are real questions in a requester's words, which
often differ from the regulation's own wording, and an embedding model matches meaning
across different words where BM25 needs shared ones. Everything but the first stage
stays as it was: the corpus and its passages, the gold set, the depth of 50 and the
metric.

**Prediction.** The mean difference in section recall@10 is positive and the paired
randomization test supports it at 5%
([ADR-0024](../adr/0024-paired-comparisons-cross-validated-tuning-and-adoption.md)).
Studies of real regulatory questions found large dense gains (below), but they used
larger models than bge-base, which has 109M parameters and reads at most 512 tokens, so
the gain here may be smaller. By question type, the gain should be larger on `lookup`
and `multi_passage` questions than on `table` questions, whose rows are codes and
numbers that keyword matching finds well. The hypothesis is refuted if the mean
difference is zero or negative, or if the test does not support it (p ≥ 0.05).

## 2. Related work

- **Real questions favour dense retrieval.** On SearchFireSafety's real questions about
  Korean fire-safety statutes, recall@10 was 23.39 for BM25 and 53.77 for BGE-M3
  (Chae et al., 2026, *read-part*). On RegOps-Bench, dense retrieval reached 55.9
  top-10 recall against BM25's 34.8 (Ju and Lee, 2026, *read-part*).
- **Generated questions narrow the gap.** On ObliQA, whose questions were generated from
  the regulatory passages, BM25 reached 76.1 recall@10 and the best dense model 79.5
  (Gokhan et al., 2024, *read-part*).
- **Zero-shot dense models can fail on statutes.** On BSARD, a dataset of lay questions
  about Belgian statutes, zero-shot CamemBERT scored 4.21 recall@100 against BM25's
  51.33, while a fine-tuned model reached 74.78. The authors name the gap between lay and
  legal wording, long articles and general definitional provisions as the difficulties
  (Louis and Spanakis, 2021, *read-part*).
- These compare different corpora, languages and models, so none predicts this
  corpus's numbers. bge-base is a general English model, not tuned on regulations.

*read-part*: the abstract and the sections reporting these results were read, not the
whole paper.

## 3. Setup

- **Model:** BAAI/bge-base-en-v1.5 at revision
  `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`, weights `model.safetensors` with SHA-256
  `c7c1988aae201f80cf91a5dbbd5866409503b89dcaba877ca6dba7dd0a5167d7`, checked before
  loading. Questions get the model card's instruction,
  `Represent this sentence for searching relevant passages: `; passages get none. The
  model reads at most 512 tokens, and 20 of the 13,539 passages are longer, so their ends
  are cut. The embed command counts them and keeps the count in the vectors file's
  header, which is not committed; running it again recomputes the count.
- **Libraries:** torch 2.14.1 (CUDA 12.6), sentence-transformers 6.3.0, transformers
  5.23.0 ([ADR-0009](../adr/0009-local-retrieval-models-and-exact-search.md)).
- **Search:** the passages' 768-dimension vectors, SHA-256
  `3c0748cc66466f00b7b0016ce6471ee9295489c7bdb9646ee67128fe2be25cb1`, are compared with
  the question's by cosine distance in PostgreSQL 18 with pgvector, exactly, over every
  passage, with ties broken by passage order. Each question keeps its top 50 passages, as
  BM25's run did.
- **Config:** `eval/configs/dense-bge-base.toml`, run through the pipeline of
  [ADR-0023](../adr/0023-experiments-as-configs-run-by-one-cached-pipeline.md).
- **Runs:** the baseline `2026-11-24-bm25-dev-1` ran at commit `5cf37c3` (tree
  `68e22c96`); this experiment's `2026-11-25-dense-bge-base-dev-1` ran at commit
  `05ea125` (tree `bf4e56a0`), with no uncommitted changes to tracked files. Its config
  was not yet committed then; run.json holds its whole text, which equals the config
  committed with the records. Both ran on corpus version
  `ecaac596…` and gold set `7bfdfdf9…`: 250 dev items, 214 of them answerable and scored.
- **Decision:** the paired randomization test of ADR-0024 on per-question section
  recall@10, 100,000 sign flips from the seed `phase-3-paired-2026-11-25`, and a 95%
  t-interval for the mean difference.
- **Machine and cost:** the Windows laptop with an RTX 4070 Laptop GPU (8 GB), Python
  3.14.7. Everything ran locally, at no cost. Embedding the passages took 3 min 54 s,
  model loading included, and the run took 70 s for 250 questions.

## 4. Results

| Questions | n | Run | R@5 | R@10 | R@20 | R@50 | MRR | nDCG@10 |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| all | 214 | BM25 | 0.610 | 0.691 | 0.761 | 0.856 | 0.575 | 0.558 |
|  |  | bge-base | 0.552 | 0.618 | 0.725 | 0.821 | 0.541 | 0.520 |
| lookup | 122 | BM25 | 0.639 | 0.721 | 0.779 | 0.869 | 0.514 | 0.559 |
|  |  | bge-base | 0.582 | 0.639 | 0.762 | 0.852 | 0.501 | 0.525 |
| multi_passage | 49 | BM25 | 0.452 | 0.547 | 0.649 | 0.793 | 0.570 | 0.454 |
|  |  | bge-base | 0.359 | 0.473 | 0.595 | 0.698 | 0.438 | 0.363 |
| table | 43 | BM25 | 0.707 | 0.770 | 0.838 | 0.893 | 0.754 | 0.675 |
|  |  | bge-base | 0.686 | 0.724 | 0.769 | 0.871 | 0.773 | 0.682 |

The difference in section recall@10, bge-base minus BM25:

| Questions | n | Difference | 95% interval |
|---|---:|---:|---|
| all | 214 | −0.073 | [−0.125, −0.021] |
| lookup | 122 | −0.082 | [−0.160, −0.004] |
| multi_passage | 49 | −0.074 | [−0.174, +0.027] |
| table | 43 | −0.046 | [−0.128, +0.036] |

- **The paired randomization test gives p = 0.0062.** bge-base retrieves worse than BM25,
  by 7.3 points of section recall@10. The results by type are description, not tests.
- The spread of the per-question differences is 0.388, so the smallest difference this
  sample detects at power 0.8 is 0.075.
- bge-base is behind at every cutoff and on every type, with two exceptions on table
  questions, where it ranks the first cited section slightly higher: MRR 0.773 against
  0.754, and nDCG@10 0.682 against 0.675.
- The prediction by type failed as well: table questions lost least (−0.046) and
  lookup questions most (−0.082), though results by type are description only.
- **Latency per question:** median 0.278 s and 95th percentile 0.393 s for bge-base,
  embedding the question on the GPU included, against 0.050 s and 0.112 s for BM25.

## 5. Flips

15 questions improved and 38 regressed; the comparison record lists them. The last three
columns sort each question by its first match, in this order: a section number of Parts
171 to 180 (the regular expression `\b1(?:7[1-9]|80)\.\d+`), then a UN or NA
identification number (`\b(?:UN|NA)\s?\d{4}\b`), else neither. They are computed from
`eval/dev/items.jsonl` and the comparison record.

| Questions | All | lookup | multi_passage | table | A section number in the question | A UN or NA number | Neither |
|---|---:|---:|---:|---:|---:|---:|---:|
| Improved | 15 | 7 | 5 | 3 | 11 | 2 | 2 |
| Regressed | 38 | 17 | 16 | 5 | 17 | 4 | 17 |
| All answerable | 214 | 122 | 49 | 43 | 130 | 16 | 68 |

- **Multi-passage questions regress most.** They are 23% of the answerable questions but
  42% of the regressions: bge-base finds fewer of the several sections the regulator
  cited.
- **Questions without an explicit number regress more often:** 45% of the regressions
  against 32% of all questions. So BM25's advantage is not only exact section numbers.
  One explanation, not tested here, is that the requesters write in the regulation's
  own terms, which BM25 matches word for word.
- **In 4 regressions the cited section left the top 50 entirely,** and in many others it
  fell from BM25's ranks 1 to 3 to ranks 11 to 48.

Four of the sharpest regressions, read in full, show three failure patterns:

- **A neighbouring section wins.** For a question about portable tank instruction T8
  (24-0108-Q1), bge-base ranked §§178.275 and 178.276 above the cited §178.273: sibling
  specifications with nearly the same wording. For a question about retrofitting
  DOT-111 tank cars (18-0036-Q1), it ranked the DOT-117 specification, §179.202-13,
  above the retrofit rule the regulator cited, §174.310.
- **The topic drifts away from the asked obligation.** Asked whether drivers need a
  hazmat endorsement to carry lithium batteries (22-0086-Q1), bge-base ranked a passage
  of §171.12, on North American shipments, first, and two special provisions next, on
  battery-powered vehicles and on lithium batteries. The driver's licence rule the
  regulator cited, §177.816, fell from rank 1 to rank 25.
- **An exact identifier is blurred.** A question naming § 173.403 and the term "CSI"
  (18-0004-Q1) sent BM25 to that definition at rank 1. bge-base ranked the neighbouring
  fissile-transport section first and the definition 18th.

The other 34 regressions were classified by the table above, not read one by one.

## 6. Threats to validity

- **One model, one setting.** The result concerns bge-base with its card's instruction
  and 512 tokens, not dense retrieval in general. The studies that found large dense
  gains used larger models; E2 and E3 test two larger models on the same questions.
- **The questions are written by professionals.** Requesters often quote the
  regulation's terms and section numbers, which favours keyword matching. This is the
  distribution the system will serve, not a bias of the measurement, but it limits how
  far the result carries to lay questions.
- **The labels are the regulator's citations.** A passage that answers a question in a
  section the regulator did not cite counts as a miss, for both methods alike.
- **Truncation.** 20 passages are cut at 512 tokens; a section whose only matching text
  lies past the cut cannot be found by bge-base.
- **Machine-dependent numerics.** The vectors were computed once on one GPU; another
  machine may round differently and swap near-tied passages, which is why the vectors'
  SHA-256 is recorded and published runs come from one machine.
- **Dev split only.** Nothing was tuned, so the dev score is not inflated by a choice
  among settings, but the held-out split has not been run.

## 7. Verdict

**Rejected.** bge-base lowers section recall@10 by 0.073 (95% interval −0.125 to −0.021,
p = 0.0062), so BM25 remains the baseline. Configurations tried in phase 3 so far: 1.

## 8. Reproduction

From the repository root, with the database running and `DATABASE_URL` set as in
`.env.example`, and the corpus fetched and parsed as the README's quickstart shows. The
first command builds the passage index, and does nothing when the index already holds
the corpus; `--download` fetches the model's weights, about 440 MB, when they are not
cached.

```
uv run --env-file .env python -m regulator_graded_rag.index
uv sync --group models
uv run --group models --env-file .env python -m regulator_graded_rag.embed --config eval/configs/dense-bge-base.toml --download
uv run --group models --env-file .env python -m regulator_graded_rag.run --split dev --config eval/configs/dense-bge-base.toml
uv run python -m regulator_graded_rag.compare 2026-11-24-bm25-dev-1 2026-11-25-dense-bge-base-dev-1
```

A rerun writes a new run folder. The comparison record recomputes byte for byte from the
two committed runs, which a unit test checks.

## References

- Kyubyung Chae, Jewon Yeom, Jeongjae Park, Seunghyun Bae, Ijun Jang, Hyunbin Jin, Jinkwan Jang and Taesup Kim, [Beyond Case Law: Evaluating Structure-Aware Retrieval and Safety in Statute-Centric Legal QA](https://arxiv.org/abs/2604.06173) (arXiv, 2026).
- Yeong-Joon Ju and Seong-Whan Lee, [Citation-Closure Retrieval and Per-Rule Attribution for Real-World Regulatory Compliance Question Answering](https://arxiv.org/abs/2605.29742) (arXiv, 2026).
- Tuba Gokhan, Kexin Wang, Iryna Gurevych and Ted Briscoe, [RIRAG: Regulatory Information Retrieval and Answer Generation](https://arxiv.org/abs/2409.05677) (arXiv, 2024).
- Antoine Louis and Gerasimos Spanakis, [A Statutory Article Retrieval Dataset in French](https://arxiv.org/abs/2108.11792) (arXiv, 2021).
