<!-- Author: Nicola Antonello -->

# ADR-0023: Experiments as configs, run by one cached pipeline

- Status: accepted
- Date: 2026-11-25

## Context

Phase 3 runs eight retrieval experiments against the committed BM25 baseline: three
dense models, two fusions of BM25 with dense retrieval, and three rerankers
([ADR-0009](0009-local-retrieval-models-and-exact-search.md)). Five of them tune a
setting by cross-validation, which scores every value of a grid on every dev question
([ADR-0024](0024-paired-comparisons-cross-validated-tuning-and-adoption.md)), and
phase 4 calls the winning retriever once per question. Every published number must
reproduce from a committed run record
([ADR-0012](0012-main-numbers-and-run-records.md)), so each configuration has to be
written down whole, and each run has to stay tied to the configuration it ran.

## Options

| Option | For | Against |
|---|---|---|
| Everything live: each method runs end to end, and cross-validation reruns every value | Simple | Tuning means many live runs, configurations live in command lines, and later analyses search again |
| Live first stages, with fusion and reranking derived from stored runs | Cheap | Two code paths, derived for experiments and live for phase 4, that a test must keep in agreement |
| One pipeline driven by committed config files, with a cache (chosen by the owner, 2026-11-25) | Every configuration is a file in git, and experiments and phase 4 share one code path | A framework layer, which must stay limited to phase 3's four stages |

## Decision

**Configs.** Each configuration is a TOML file in `eval/configs/`, read with the
standard library's `tomllib`.

- It names one or two first stages (`bm25` or `dense`), a fusion (`rrf` or `weighted`)
  when there are two, and an optional reranker.
- A scalar setting is fixed, and so is a list of one value. A list of more than one
  value is a grid that cross-validation tunes: at most one setting is a grid, a grid
  needs a `[cv]` table with the folds and the seed, and a `[cv]` table needs a grid.
- A model is pinned by its Hugging Face revision and its weights file's SHA-256.
- A config runs exactly as written or not at all. A table may hold only the keys its
  kind uses, a dense stage states its query prompt (`""` for a model without one), and
  a value out of its range is refused, so a misspelt or mistyped setting stops the run
  instead of running another experiment than the file shows.
- The file's name is the config's name. A config that produced a run is never edited:
  a change is a new config with a new name, and the run command refuses a config whose
  name has a run made from other contents.
- `eval/configs/bm25.toml` stands for the baseline run, which predates configs. An
  integration test runs it through the pipeline on every dev question and checks that
  each question's passage IDs and scores equal the run's, so the baseline needs no
  rerun. Since that run records no config for the run command to compare, a unit test
  pins the file's settings and this test its results.

**One pipeline.** `build` turns a config without a grid into a retriever with the
harness's interface: a name, its settings, and the best k passages for a question. The
run command and phase 4 call it as they call BM25. `run --config PATH` names its run
`<date>-<config name>-<split>-<n>`, and the run file holds the config's path, SHA-256
and text. Every stage keeps its top 50 passages per question, the harness's depth.

**The cache.** Each stage's output for a question, its passage IDs and scores, is saved
in the git-ignored folder `.cache/pipeline/<split>/`, in one JSON-lines file per stage
key and one line per question. Each split has its own folder, so held-out hit lists
never sit beside dev's. The key is the SHA-256 of:

- the stage's kind and settings, a model's revision and weights checksum included;
- the identity of the data the stage reads: for BM25, when its index was built and the
  database server's version; for a dense stage, its vectors' checksum;
- for fusion and reranking, the key of the stage they read from;
- the corpus version;
- the code: the package's Python files and the locked library versions in `uv.lock`.

Code is in the key because a change to it, a fixed bug or a new tie-break, can change a
stage's output while an old entry still looks right, and a new torch can change a
model's outputs while the package stays the same. The data is in the key because a
rebuilt index, recomputed vectors or a new server can change the answers while the
settings and the code stay the same. The gold set is not in the key, because a stage
sees only the question's text, which already keys each line.

Each line also keeps the seconds its stage took, and a run records those seconds, so a
run answered from the cache reports what each answer cost to compute, not the
microseconds of reading it back. The cache only remembers: deleting it and running
again computes every entry again, with the same passages and scores wherever the stage
computes deterministically, as BM25 does; a GPU's kernels may differ in the last digits.

## Consequences

- A new configuration is a new file, and a tuned method scores every grid value from
  stage outputs it computed once.
- Phase 4 calls the code the experiments measured, so the retriever it uses is a
  configuration with a run record.
- Any change to the code or the lock file, a dependency update included, recomputes
  every stage, and a rebuilt index or a new database server recomputes BM25's.
  Reranking 50 passages for each question is the slowest stage, so it pays this the
  most.
- The `--k1` and `--b` flags stay, for the baseline's own command. Beside `--config`
  they are refused, because the config sets every setting.

## References

- D. Sculley, Gary Holt, Daniel Golovin, Eugene Davydov, Todd Phillips, Dietmar Ebner, Vinay Chaudhary, Michael Young, Jean-François Crespo and Dan Dennison, [Hidden Technical Debt in Machine Learning Systems](https://proceedings.neurips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html) (NIPS, 2015). Configuration issues are among the ML-specific risk factors behind ongoing maintenance costs.
- Jimmy Lin, Xueguang Ma, Sheng-Chieh Lin, Jheng-Hong Yang, Ronak Pradeep and Rodrigo Nogueira, [Pyserini: An Easy-to-Use Python Toolkit to Support Replicable IR Research with Sparse and Dense Representations](https://arxiv.org/abs/2102.10073) (arXiv, 2021). Sparse, dense and hybrid retrieval baselines, kept replicable by shared norms and automated testing.
