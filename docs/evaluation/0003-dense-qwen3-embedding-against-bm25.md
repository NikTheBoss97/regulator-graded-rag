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

## 3. Setup

- **Model:** Qwen/Qwen3-Embedding-0.6B at revision
  `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, weights `model.safetensors` with SHA-256
  `0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`, checked before
  loading. The weights hold 595,776,512 parameters in 28 layers, stored in bfloat16 and
  loaded in float32, as the config states. A text's vector is the state of its last
  token, the end-of-text token the tokenizer appends, 1,024 dimensions. Questions get
  the model's stored query instruction,
  `Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:`;
  passages get none. The model reads up to 8,192 tokens here, and no passage is longer,
  so none is cut.
- **Libraries:** torch 2.14.1 (CUDA 12.6), sentence-transformers 6.3.0, transformers
  5.23.0 ([ADR-0009](../adr/0009-local-retrieval-models-and-exact-search.md)), as in E1.
- **Search:** the passages' vectors, SHA-256
  `d15a9078ec8fc247ac72f005025347d25a240df8e08d089acebba08d49cc1ca8`, are compared with
  the question's by cosine distance in PostgreSQL 18 with pgvector, exactly, over every
  passage, with ties broken by passage order. Each question keeps its top 50 passages.
- **Config:** `eval/configs/dense-qwen3-embedding.toml`, run through the pipeline of
  [ADR-0023](../adr/0023-experiments-as-configs-run-by-one-cached-pipeline.md).
- **Runs:** the baseline `2026-11-24-bm25-dev-1` ran at commit `5cf37c3` (tree
  `68e22c96`); this experiment's `2026-11-26-dense-qwen3-embedding-dev-1` ran at commit
  `72b6f90` (tree `a82118ef`), with no uncommitted changes to tracked files. That commit
  holds this report's question, hypothesis and related work, and the config. Both runs
  used corpus version `ecaac596…` and gold set `7bfdfdf9…`: 250 dev items, 214 of them
  answerable and scored.
- **Decision:** the paired randomization test of ADR-0024 on per-question section
  recall@10, 100,000 sign flips from the seed `phase-3-paired-2026-11-25`, and a 95%
  t-interval for the mean difference.
- **Machine and cost:** the Windows laptop with an RTX 4070 Laptop GPU (8 GB), Python
  3.14.7; the run record names the GPU and torch's and CUDA's versions. Everything ran
  locally, at no cost. Embedding the passages took 11 min 41 s, the 1.2 GB download and
  model loading included, and the GPU slowed itself at 88 °C on the way. The run took
  25 s for 250 questions, on an idle machine.

## 4. Results

| Questions | n | Run | R@5 | R@10 | R@20 | R@50 | MRR | nDCG@10 |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| all | 214 | BM25 | 0.610 | 0.691 | 0.761 | 0.856 | 0.575 | 0.558 |
|  |  | Qwen3-Embedding | 0.534 | 0.626 | 0.727 | 0.791 | 0.528 | 0.511 |
| lookup | 122 | BM25 | 0.639 | 0.721 | 0.779 | 0.869 | 0.514 | 0.559 |
|  |  | Qwen3-Embedding | 0.566 | 0.664 | 0.762 | 0.820 | 0.483 | 0.518 |
| multi_passage | 49 | BM25 | 0.452 | 0.547 | 0.649 | 0.793 | 0.570 | 0.454 |
|  |  | Qwen3-Embedding | 0.367 | 0.490 | 0.633 | 0.720 | 0.506 | 0.401 |
| table | 43 | BM25 | 0.707 | 0.770 | 0.838 | 0.893 | 0.754 | 0.675 |
|  |  | Qwen3-Embedding | 0.636 | 0.671 | 0.733 | 0.791 | 0.681 | 0.617 |

The difference in section recall@10, Qwen3-Embedding minus BM25:

| Questions | n | Difference | 95% interval |
|---|---:|---:|---|
| all | 214 | −0.065 | [−0.117, −0.014] |
| lookup | 122 | −0.057 | [−0.135, +0.020] |
| multi_passage | 49 | −0.056 | [−0.150, +0.038] |
| table | 43 | −0.099 | [−0.187, −0.011] |

- **The paired randomization test gives p = 0.013.** Qwen3-Embedding retrieves worse
  than BM25, by 6.5 points of section recall@10. The results by type are description,
  not tests.
- The spread of the per-question differences is 0.383, so the smallest difference this
  sample detects at power 0.8 is 0.074.
- Qwen3-Embedding is behind BM25 at every cutoff, on every type and on every metric.
- Next to the two smaller models, as description: it finds slightly more by rank 10 and
  20 (recall@10 0.626 against 0.618 and 0.612) but ranks it lower, with the lowest
  recall@5 (0.534), MRR (0.528) and nDCG@10 (0.511) of the three.
- Table questions lost most, −0.099, and lookup and multi-passage questions about 0.06.
- **Latency per question:** median 0.095 s and 95th percentile 0.117 s, embedding the
  question on the GPU included, against 0.050 s and 0.112 s for BM25.

## 5. Flips

18 questions improved and 37 regressed; the comparison record lists them. The last three
columns use report 0001's rule: each question is sorted by its first match, a section
number of Parts 171 to 180 (`\b1(?:7[1-9]|80)\.\d+`), then a UN or NA identification
number (`\b(?:UN|NA)\s?\d{4}\b`), else neither.

| Questions | All | lookup | multi_passage | table | A section number in the question | A UN or NA number | Neither |
|---|---:|---:|---:|---:|---:|---:|---:|
| Improved | 18 | 8 | 8 | 2 | 12 | 1 | 5 |
| Regressed | 37 | 15 | 13 | 9 | 21 | 4 | 12 |
| All answerable | 214 | 122 | 49 | 43 | 130 | 16 | 68 |

- **Multi-passage questions regress most often,** as with both smaller models: 23% of
  the answerable questions but 35% of the regressions.
- **Unlike E1 and E2, questions without an explicit number regress in proportion:** 32%
  of the regressions and 32% of all questions.
- **The definitions are kept.** Of the 25 answerable questions that cite §171.8, the
  regulation's definitions, Qwen3-Embedding ranks it in the top 10 for 8, against 10 for
  BM25, 6 for bge-base and 3 for gte-modernbert. It never leaves the top 50 in a
  regression, and 5 of the 18 improvements cite it.
- **The Hazardous Materials Table attracts.** Qwen3-Embedding ranks a passage of
  §172.101 first for 28 of the 214 questions, though only 4 cite that section; BM25 does
  so for 5, bge-base for 5 and gte-modernbert for 7.
- **In 8 regressions every cited section left the top 50** (E1: 4, E2: 15).
- 18 questions regressed under all three dense models, and 8 improved under all three;
  7 regressions are Qwen3-Embedding's alone.

Six of the sharpest regressions, read in full, show three failure patterns:

- **The table wins when a question names a material.** For "UN1044, Fire
  extinguishers" (23-0036-Q2) and "UN2794, Batteries, wet, filled with acid"
  (17-0032-Q1), Qwen3-Embedding ranked passages of the Hazardous Materials Table and its
  special provisions, §§172.101 and 172.102, first. The cited §173.309 on fire
  extinguishers fell from rank 1 out of the top 50, and §173.159 on wet batteries from
  rank 1 to 11, although the second question names § 173.159(e).
- **An explicit section number is ignored.** A question naming the exception for
  naturally occurring radioactive material in § 173.401 (17-0114-Q1) sent BM25 to
  §173.401 at rank 1; Qwen3-Embedding ranked the applicability section §171.1 and table
  passages first, and none of the four cited sections in its top 50. A question about
  § 178.345-9(h) and the vent of a DOT 406 cargo tank motor vehicle (25-0043-Q1) got the
  pressure relief rules of tank cars (§§179.400-20, 179.15), cylinders (§173.301) and UN
  pressure receptacles (§178.75) first, and §178.345-9 16th; BM25 ranked it first.
- **A neighbouring rule on the same idea wins.** Asked whether "CA" may abbreviate
  "case" on a shipping paper (18-0068-Q1), Qwen3-Embedding ranked §172.308, which allows
  abbreviations in markings, above the cited shipping paper rule §172.202, which fell
  from rank 1 to 30. For a repackaged explosive's approval (21-0009-Q3), it ranked five
  passages of §173.62, the explosives packing instructions, first, and the cited
  approval rule §173.56 outside its top 50 (BM25: rank 6).

The other 31 regressions were classified by the table above, not read one by one.

## 6. Threats to validity

- **One model, one setting.** The result concerns Qwen3-Embedding-0.6B with its stored
  instruction, written for web search queries. An instruction written for regulatory
  questions might rank differently, but choosing one on the dev split would be tuning,
  and counts as a configuration tried.
- **The questions are written by professionals.** Requesters often quote the
  regulation's terms and section numbers, which favours keyword matching. This is the
  distribution the system will serve, but it limits how far the result carries to lay
  questions.
- **The labels are the regulator's citations.** A passage that answers a question in a
  section the regulator did not cite counts as a miss, for both methods alike.
- **Questions from one letter are not independent.** The 214 questions come from 155
  letters, up to 5 from one, and the paired test flips each question's sign on its own.
  Flipping all of a letter's questions together instead, with ADR-0024's test over each
  letter's summed differences (`compare.letter_sums`), keeps the difference and gives
  p = 0.016: the result holds. This check is reported beside ADR-0024's decision, not as
  part of it.
- **The dense models are not compared with each other.** Each is tested against BM25.
  Qwen3-Embedding's recall@10 is 0.008 above bge-base's, a tenth of the smallest
  difference this sample detects, so these runs do not show that one dense model
  retrieves better than another.
- **Latency depends on the machine's load.** A run times each question as it is
  computed, so other programs on the laptop slow it. This run's machine was idle.
- **Machine-dependent numerics.** The vectors were computed once on one GPU; another
  machine may round differently and swap near-tied passages, which is why the vectors'
  SHA-256 is recorded and published runs come from one machine.
- **Dev split only.** Nothing was tuned, so the dev score is not inflated by a choice
  among settings, but the held-out split has not been run.

## 7. Verdict

**Rejected.** Qwen3-Embedding-0.6B lowers section recall@10 by 0.065 (95% interval −0.117
to −0.014, p = 0.013), so BM25 remains the baseline. The hypothesis held as written: the
difference lies above E1's −0.073, and the test supports no gain. But the margin over
E1, 0.008, is far too small to show that this model retrieves better than bge-base.
Configurations tried in phase 3 so far: 3.

## 8. Reproduction

From the repository root, with the database running and `DATABASE_URL` set as in
`.env.example`, and the corpus fetched and parsed as the README's quickstart shows. The
first command builds the passage index, and does nothing when the index already holds
the corpus; `--download` fetches the model's weights, about 1.2 GB, when they are not
cached.

```
uv run --env-file .env python -m regulator_graded_rag.index
uv sync --group models
uv run --group models --env-file .env python -m regulator_graded_rag.embed --config eval/configs/dense-qwen3-embedding.toml --download
uv run --group models --env-file .env python -m regulator_graded_rag.run --split dev --config eval/configs/dense-qwen3-embedding.toml
uv run python -m regulator_graded_rag.compare 2026-11-24-bm25-dev-1 2026-11-26-dense-qwen3-embedding-dev-1
```

A rerun writes a new run folder. The comparison record recomputes byte for byte from the
two committed runs, which a unit test checks.
