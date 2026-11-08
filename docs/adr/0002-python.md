<!-- Author: Nicola Antonello -->

# ADR-0002: Python for the project

- Status: accepted
- Date: 2026-11-04

## Context

The work is parsing XML, running embedding, reranking and generation models, calling
model servers and APIs, computing retrieval metrics and running statistical tests. Most
of a run's time goes to model inference, and quality comes from retrieval and
evaluation choices rather than from the speed of the code around them. Rust was the
other language considered.

## Options

| Option | Why not |
|---|---|
| **Python** | Chosen. The libraries this project needs are Python-first: PyTorch and sentence-transformers for the local models, bm25s as the reference for the BM25 test, the clients for model servers and Anthropic's API, and the statistics stack. It is also the language most AI engineering roles ask for, which is a judgment rather than hiring data. |
| Rust | Faster and memory-safe, but the model and evaluation libraries would need bindings or reimplementation, and speed is not this project's bottleneck: a faster harness would move no measured result. |

## Decision

The project is written in Python and managed with uv, with ruff, a type checker and
pytest as its gates. The Python version and the type checker are chosen in phase 1.

## Consequences

- The local models, the BM25 reference and the statistics live in one language, so a
  test can compare them directly.
- A type checker in CI offsets dynamic typing.
- If a measurement ever shows a real bottleneck, that one component can move to a faster
  language under its own ADR.

## Amendments

- 2026-11-08: ADR-0015 chose Python 3.14 and mypy.
