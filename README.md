<!-- Author: Nicola Antonello -->

# regulator-graded-rag

`regulator-graded-rag` answers questions about the US hazardous materials regulations,
49 CFR Parts 171–180, with quotes that code verifies word for word, and declines when
its sources do not support an answer. It is graded against answers it did not write: in
its public interpretation letters, the regulator, PHMSA, answers real people's questions
yes or no and cites the sections behind each answer.

```mermaid
flowchart LR
  manifest[Corpus manifest] --> build[Fetch, verify, parse into passages]
  build --> index[(Postgres 18 with pgvector)]
  question[Question] --> retrieve[Retrieve and rerank]
  index --> retrieve
  retrieve --> generate[Generator: one JSON answer]
  generate --> verify[Verify quotes, apply the decline rule]
  verify --> answer[Answer or decline]
  gold[Gold questions] --> harness[Evaluation harness]
  harness --> question
  verify --> harness
  harness --> records[Run records in git]
  records --> table[README results table]
```

Status: phase 1 (foundations) complete. The 2025 edition is fetched by checksum and
split into 13,539 passages, which pass their parse checks. The owner compared 25 sampled
passages with [the printed pages](corpus/parse-review.md): 20 match, and 5 differ only
in that the page sets A₁ and A₂ as subscripts, which
[ADR-0017](docs/adr/0017-passage-text-from-the-xml.md#amendments) keeps as plain text.
Phase 2 (evaluation) is in progress: 903 regulator letters are split into dev and
held-out by a committed seed. This is not compliance or legal advice.

## Results

<!-- results:start -->
No committed run yet: BM25's first dev run comes with the approved dev questions.
<!-- results:end -->

`uv run python -m regulator_graded_rag.report` writes this table from the committed run
records in `eval/runs/`, and a test fails if it is ever edited by hand.

## How it is evaluated

- **Questions** are numbered yes-or-no questions from the regulator's letters from 2017
  on, kept only when every paragraph they cite reads the same in the 2025 edition.
  Code splits them into dev and held-out before anyone reads the letters, and the
  held-out split runs once.
- **Retrieval** is scored by section recall@10: the share of the sections the regulator
  cited that reach the top 10 passages.
- **Generation** is scored by the supported verdict: the regulator's yes or no, backed by
  at least one quote, verified by code, from a section the regulator cited. Verdict
  accuracy and the false-answer rate sit next to it. It runs closed-book, with the cited
  sections, and end-to-end, so a failure can be traced to a stage.
- **Models:** a local open-weight model answers by default, and Claude Haiku, Sonnet and
  Opus answer the dev questions once as a comparison.

## Quickstart

Needs Python 3.14 with uv; the index and the integration tests also need Docker.

```bash
uv sync --locked
uv run python -m regulator_graded_rag.fetch
uv run python -m regulator_graded_rag.passages
cp .env.example .env
docker compose up -d --wait
uv run --env-file .env python -m regulator_graded_rag.index
uv run pytest tests/unit
```

The build writes the passages to `corpus/parsed/passages.jsonl` and checks that they give
the passage count and corpus version the manifest records. Before starting Postgres,
choose a password in `.env`, the same in both of its lines: Compose reads it, and the
index reads `DATABASE_URL` from it. The index is rebuilt only when the corpus version
changes.

## Read more

- [Design](docs/DESIGN.md): goals, invariants, architecture, evaluation and phases.
- [Decision records](docs/adr/): each decision, with the options it rejected.
- [Further reading](docs/reading/README.md): the sources behind the decisions. Five first
  reads:
  - Chip Huyen, [AI Engineering](https://github.com/chiphuyen/aie-book) (O'Reilly, 2025).
  - Dan Jurafsky and James H. Martin, [Speech and Language Processing, 3rd edition draft](https://web.stanford.edu/~jurafsky/slp3/) (online manuscript, 2026), chapter 11, "Information Retrieval and RAG".
  - Mark Sanderson, [Test Collection Based Evaluation of Information Retrieval Systems](https://doi.org/10.1561/1500000009) (Foundations and Trends in Information Retrieval, 2010).
  - Nelson F. Liu, Tianyi Zhang and Percy Liang, [Evaluating Verifiability in Generative Search Engines](https://doi.org/10.18653/v1/2023.findings-emnlp.467) (Findings of EMNLP, 2023).
  - Cynthia Dwork et al., [The Reusable Holdout: Preserving Validity in Adaptive Data Analysis](https://doi.org/10.1126/science.aaa9375) (Science, 2015).

## License

[Apache License 2.0](LICENSE).
