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

## 3. Setup

- **Model:** Alibaba-NLP/gte-modernbert-base at revision
  `e7f32e3c00f91d699e8c43b53106206bcc72bb22`, weights `model.safetensors` with SHA-256
  `3e85899d5728cb7de79781c0c3acfb91ccef9f875f1f7e0b3c9f3dd4b6a724ba`, checked before
  loading. The weights hold 149,014,272 parameters in 22 layers, stored in 16 bits and
  loaded in float32, as the config states. A text's vector is its first token's state,
  768 dimensions. Neither questions nor passages get a prompt, since the model stores
  none. The model reads up to 8,192 tokens, and no passage is longer, so none is cut.
- **Libraries:** torch 2.14.1 (CUDA 12.6), sentence-transformers 6.3.0, transformers
  5.23.0 ([ADR-0009](../adr/0009-local-retrieval-models-and-exact-search.md)), as in E1.
- **Search:** the passages' vectors, SHA-256
  `fbb5ca3f2b950d02941b0201a03d04811e30112a88b8ac12d9a4abe48cb12267`, are compared with
  the question's by cosine distance in PostgreSQL 18 with pgvector, exactly, over every
  passage, with ties broken by passage order. Each question keeps its top 50 passages.
- **Config:** `eval/configs/dense-gte-modernbert.toml`, run through the pipeline of
  [ADR-0023](../adr/0023-experiments-as-configs-run-by-one-cached-pipeline.md).
- **Runs:** the baseline `2026-11-24-bm25-dev-1` ran at commit `5cf37c3` (tree
  `68e22c96`); this experiment's `2026-11-25-dense-gte-modernbert-dev-1` ran at commit
  `72b6f90` (tree `a82118ef`), with no uncommitted changes to tracked files. That commit
  holds this report's question, hypothesis and related work, and the config. Both runs
  used corpus version `ecaac596…` and gold set `7bfdfdf9…`: 250 dev items, 214 of them
  answerable and scored.
- **Decision:** the paired randomization test of ADR-0024 on per-question section
  recall@10, 100,000 sign flips from the seed `phase-3-paired-2026-11-25`, and a 95%
  t-interval for the mean difference.
- **Machine and cost:** the Windows laptop with an RTX 4070 Laptop GPU (8 GB), Python
  3.14.7; the run record names the GPU and torch's and CUDA's versions. Everything ran
  locally, at no cost. Embedding the passages took 2 min 43 s, download and model
  loading included, while another program shared the GPU, so that time is not compared
  with E1's. The run took 30 s for 250 questions, while other commands ran on the
  laptop (section 6).

## 4. Results

| Questions | n | Run | R@5 | R@10 | R@20 | R@50 | MRR | nDCG@10 |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| all | 214 | BM25 | 0.610 | 0.691 | 0.761 | 0.856 | 0.575 | 0.558 |
|  |  | gte-modernbert | 0.567 | 0.612 | 0.680 | 0.775 | 0.555 | 0.525 |
| lookup | 122 | BM25 | 0.639 | 0.721 | 0.779 | 0.869 | 0.514 | 0.559 |
|  |  | gte-modernbert | 0.598 | 0.656 | 0.713 | 0.803 | 0.506 | 0.537 |
| multi_passage | 49 | BM25 | 0.452 | 0.547 | 0.649 | 0.793 | 0.570 | 0.454 |
|  |  | gte-modernbert | 0.401 | 0.452 | 0.556 | 0.714 | 0.537 | 0.404 |
| table | 43 | BM25 | 0.707 | 0.770 | 0.838 | 0.893 | 0.754 | 0.675 |
|  |  | gte-modernbert | 0.664 | 0.669 | 0.729 | 0.764 | 0.716 | 0.629 |

The difference in section recall@10, gte-modernbert minus BM25:

| Questions | n | Difference | 95% interval |
|---|---:|---:|---|
| all | 214 | −0.079 | [−0.138, −0.021] |
| lookup | 122 | −0.066 | [−0.157, +0.026] |
| multi_passage | 49 | −0.094 | [−0.203, +0.015] |
| table | 43 | −0.101 | [−0.166, −0.036] |

- **The paired randomization test gives p = 0.0083.** gte-modernbert retrieves worse
  than BM25, by 7.9 points of section recall@10, close to bge-base's 7.3. The results by
  type are description, not tests.
- The spread of the per-question differences is 0.435, so the smallest difference this
  sample detects at power 0.8 is 0.084.
- gte-modernbert is behind BM25 at every cutoff, on every type and on every metric.
- Next to bge-base, as description: about level at recall@10 (0.612 against 0.618) and
  slightly ahead at the top (recall@5 0.567 against 0.552, MRR 0.555 against 0.541), but
  behind further down (recall@50 0.775 against 0.821).
- Table questions lost most, −0.101, and lookup questions least, −0.066.
- **Latency per question:** median 0.102 s and 95th percentile 0.201 s for
  gte-modernbert, embedding the question on the GPU included, against 0.050 s and
  0.112 s for BM25. Other commands slowed parts of this run, so its 95th percentile
  overstates it; section 6 gives the details, and why E1's 0.278 s is not compared.

## 5. Flips

21 questions improved and 47 regressed; the comparison record lists them. The last three
columns use report 0001's rule: each question is sorted by its first match, a section
number of Parts 171 to 180 (`\b1(?:7[1-9]|80)\.\d+`), then a UN or NA identification
number (`\b(?:UN|NA)\s?\d{4}\b`), else neither.

| Questions | All | lookup | multi_passage | table | A section number in the question | A UN or NA number | Neither |
|---|---:|---:|---:|---:|---:|---:|---:|
| Improved | 21 | 12 | 9 | 0 | 14 | 2 | 5 |
| Regressed | 47 | 20 | 17 | 10 | 23 | 4 | 20 |
| All answerable | 214 | 122 | 49 | 43 | 130 | 16 | 68 |

- **Multi-passage questions regress most often,** as in E1: 23% of the answerable
  questions but 36% of the regressions.
- **Table questions regress in proportion,** 20% of the questions and 21% of the
  regressions, but none of the 21 improvements is a table question. Four of the ten
  table regressions are questions from one letter, 23-0066: all four lost §172.313 from
  the top 10, and 23-0066-Q2 lost §172.504 as well.
- **Questions without an explicit number regress more often:** 43% of the regressions
  against 32% of all questions (E1: 45%).
- **The definitions section is lost.** 25 answerable questions cite §171.8, the
  regulation's definitions. BM25 ranks it in the top 10 for 10 of them, bge-base for 6
  and gte-modernbert for 3. It is cited by 12 of the 47 regressions, and in 7 of them
  BM25 had it in its top 50 and gte-modernbert did not.
- **In 15 regressions no cited section is in the top 50** (E1: 4). That is why
  recall@50 falls to 0.775: a later stage that reorders the top 50 cannot bring them
  back.

Six of the sharpest regressions, read in full, show four failure patterns, three of them
seen in E1:

- **A definition loses to the rules that use it (new).** Asked whether a shipment of
  PCB waste is subject to the regulations (18-0081-Q3), gte-modernbert ranked the
  hazardous waste rules §§171.3 and 172.205 and §171.23, on shipments under the
  international standards, first. Asked whether a vehicle that is not a "motor vehicle"
  as the regulations define it is (22-0038-Q4), it ranked four passages of the
  applicability section §171.1 first. The cited §171.8 was in neither top 50; BM25 had
  it at ranks 7 and 3.
- **An exact identifier is ignored.** A question naming § 173.219(c)(5), the exception
  for life-saving appliances (22-0001-Q2), sent BM25 to §173.219 at rank 1.
  gte-modernbert ranked the air transport exceptions of §175.10 and the compressed gas
  sections §§173.302a, 173.306, 173.302 and 173.304 first, and §173.219 outside its top
  50.
- **A neighbouring section, or another packaging's rules, wins.** For a shipping paper
  that lists a material not subject to the regulations (23-0012-Q2), gte-modernbert
  ranked §172.202 first, and the cited §172.201 fell from rank 1 out of its top 50. For
  the retest date of an MC 338 cargo tank motor vehicle (26-0094-Q1), it ranked the
  requalification rules for cylinders and UN pressure receptacles, §§180.209, 180.205
  and 180.207, first, and the cargo tank rule the regulator cited, §180.407, 32nd. BM25
  ranked §180.407 first.
- **The requester's context outweighs the question.** A question about smokeless
  powder sold at retail (18-0001-Q3) opens with four entries of the Hazardous Materials
  Table. All 50 of gte-modernbert's top 50 passages were from §172.101, so the cited
  §173.171, on smokeless powder for small arms, was not among them. BM25 ranked it
  first.

The other 41 regressions were classified by the table above, not read one by one.

## 6. Threats to validity

- **One model, one setting.** The result concerns gte-modernbert-base without a prompt,
  not dense retrieval in general. E3 tests a larger model that follows an instruction.
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
  p = 0.0079 for gte-modernbert and p = 0.0097 for E1's bge-base: both results hold.
  This check is reported beside ADR-0024's decision, not as part of it.
- **Latency depends on the machine's load.** A run times each question as it is
  computed, so other programs on the laptop slow it. This run's machine was not idle:
  other commands ran during it, and 42 of its 250 questions took over 0.15 s, in
  bursts, against 1 in E3's run, so its 95th percentile overstates its latency more
  than its median does. E1's times are uniformly higher than this run's, its fastest
  question 0.178 s against 0.064 s here, although a question takes the same two steps
  in both: one encoding and one exact search over 768-dimension vectors. So E1's times
  are not compared with this run's.
- **Machine-dependent numerics.** The vectors were computed once on one GPU; another
  machine may round differently and swap near-tied passages, which is why the vectors'
  SHA-256 is recorded and published runs come from one machine.
- **Dev split only.** Nothing was tuned, so the dev score is not inflated by a choice
  among settings, but the held-out split has not been run.

## 7. Verdict

**Rejected.** gte-modernbert-base lowers section recall@10 by 0.079 (95% interval −0.138
to −0.021, p = 0.0083), so BM25 remains the baseline. The hypothesis held: the
difference is negative and close to E1's. Configurations tried in phase 3 so far: 2.

## 8. Reproduction

From the repository root, with the database running and `DATABASE_URL` set as in
`.env.example`, and the corpus fetched and parsed as the README's quickstart shows. The
first command builds the passage index, and does nothing when the index already holds
the corpus; `--download` fetches the model's weights, about 300 MB, when they are not
cached.

```
uv run --env-file .env python -m regulator_graded_rag.index
uv sync --group models
uv run --group models --env-file .env python -m regulator_graded_rag.embed --config eval/configs/dense-gte-modernbert.toml --download
uv run --group models --env-file .env python -m regulator_graded_rag.run --split dev --config eval/configs/dense-gte-modernbert.toml
uv run python -m regulator_graded_rag.compare 2026-11-24-bm25-dev-1 2026-11-25-dense-gte-modernbert-dev-1
```

A rerun writes a new run folder. The comparison record recomputes byte for byte from the
two committed runs, which a unit test checks.

## References

The studies section 2 refers to, summarised in report 0001:

- Kyubyung Chae, Jewon Yeom, Jeongjae Park, Seunghyun Bae, Ijun Jang, Hyunbin Jin, Jinkwan Jang and Taesup Kim, [Beyond Case Law: Evaluating Structure-Aware Retrieval and Safety in Statute-Centric Legal QA](https://arxiv.org/abs/2604.06173) (arXiv, 2026).
- Yeong-Joon Ju and Seong-Whan Lee, [Citation-Closure Retrieval and Per-Rule Attribution for Real-World Regulatory Compliance Question Answering](https://arxiv.org/abs/2605.29742) (arXiv, 2026).
- Tuba Gokhan, Kexin Wang, Iryna Gurevych and Ted Briscoe, [RIRAG: Regulatory Information Retrieval and Answer Generation](https://arxiv.org/abs/2409.05677) (arXiv, 2024).
