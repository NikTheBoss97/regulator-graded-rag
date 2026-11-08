<!-- Author: Nicola Antonello -->

# ADR-0009: Local retrieval models and exact vector search

- Status: accepted
- Date: 2026-11-06

## Context

Phase 3 compares three methods with BM25 on dev: dense retrieval, hybrid retrieval with
the fusion method settled by experiment, and a reranker over the top 50 passages of the
best first stage.

- An **embedding model** turns a passage into a vector, so that passages with similar
  meaning end up close together. Passages are embedded once, and at question time only
  the question is embedded and compared with every passage. It finds matches worded
  differently from the question.
- A **reranker**, a cross-encoder, reads the question and one passage together and scores
  how well that passage answers it. It is more accurate, but runs once per pair, so it
  only rescores the top candidates.

The open question was where these models run. The machine has an RTX 4070 laptop GPU with
8 GB, 32 GB of RAM and 160 GB of free disk.

## Options

| Option | Why not |
|---|---|
| **Open-weight models running on the owner's laptop, pinned by revision** | Chosen. Free for any number of runs, so the budget stays for generation, and pinned weights mean any run can be redone exactly, years later. Every candidate fits the 8 GB GPU, and running them locally exposes details such as input-length limits and how a model's output becomes one vector. |
| Hosted services, such as Voyage AI, OpenAI or Cohere | Nothing to install, and some hosted models may score higher. But every embedding or reranking run would be paid and need an API key and the owner's go-ahead, each call adds network delay, and a provider can retire a model, after which old run records cannot be reproduced. Their prices were not checked. |

## Decision

The models are open-weight, under MIT or Apache-2.0, with no terms to accept before
download. Each is pinned to an exact Hugging Face revision, recorded in every run record,
and used with the query format its documentation recommends. Phase 3 tries them on dev,
smallest first, and a bigger model has to earn its place with a measured gain. The
candidates:

| Role | Model | Licence | Parameters | Max input (tokens) |
|---|---|---|---|---|
| Embedding | BAAI/bge-base-en-v1.5 | MIT | 109M | 512 |
| Embedding | Alibaba-NLP/gte-modernbert-base | Apache-2.0 | 149M | 8,192 |
| Embedding | Qwen/Qwen3-Embedding-0.6B | Apache-2.0 | 596M | 32,768 |
| Reranker | cross-encoder/ms-marco-MiniLM-L6-v2 | Apache-2.0 | 23M | 512 |
| Reranker | BAAI/bge-reranker-v2-m3 | Apache-2.0 | 568M | 8,192 |
| Reranker | Qwen/Qwen3-Reranker-0.6B | Apache-2.0 | 596M | 40,960 |

- **Exact vector search.** Postgres compares the question with every passage, with no
  approximate index, so a miss cannot come from the index. An approximate index such as
  HNSW comes back only if speed ever demands it, as its own experiment.
- **One machine for published runs.** Graphics cards, Apple chips and plain processors
  round numbers slightly differently, which is enough to swap two near-tied passages.
  Passage embeddings are computed once on the Windows laptop and saved with a checksum.
  The owner's Mac loads that file instead of recomputing, and every run record names the
  machine it ran on.

## Consequences

- Retrieval costs nothing per run. A hosted model can still be tried later as an
  experiment, with the owner's go-ahead.
- PyTorch publishes GPU builds for Python 3.14 on Windows, the newest being 2.14.1 for
  CUDA 12.6 and 13.0, and sentence-transformers 6.2 supports Python 3.10 and later
  (checked on 2026-11-06). PyTorch takes a few GB, and each model 0.1-1.2 GB.
- The demo runs the question-time models on a CPU, where the larger rerankers may be too
  slow, so speed is reported next to quality and the demo uses whichever is worth it.
- Exact search over about 13,500 passages is estimated at tens of milliseconds per
  question; it is unmeasured.
- The Mac's 8 GB, shared with Docker and Postgres, is tight for the 0.6B-parameter
  models, which is one more reason published runs come from the Windows laptop.
- Unverified: how well any of these models retrieves on this project's questions, and
  how fast they run on a CPU.

## References

- Hugging Face model cards: [bge-base-en-v1.5](https://huggingface.co/BAAI/bge-base-en-v1.5), [gte-modernbert-base](https://huggingface.co/Alibaba-NLP/gte-modernbert-base), [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B), [ms-marco-MiniLM-L6-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2), [bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) and [Qwen3-Reranker-0.6B](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B).
- uv documentation, [Using uv with PyTorch](https://docs.astral.sh/uv/guides/integration/pytorch/).
- Vladimir Karpukhin et al., [Dense Passage Retrieval for Open-Domain Question Answering](https://doi.org/10.18653/v1/2020.emnlp-main.550) (EMNLP, 2020).
- Rodrigo Nogueira and Kyunghyun Cho, [Passage Re-ranking with BERT](https://arxiv.org/abs/1901.04085) (arXiv, 2019).
- Jimmy Lin, Rodrigo Nogueira and Andrew Yates, [Pretrained Transformers for Text Ranking: BERT and Beyond](https://doi.org/10.1007/978-3-031-02181-7) (Springer, 2022).
- Sebastian Bruch, Siyu Gai and Amir Ingber, [An Analysis of Fusion Functions for Hybrid Retrieval](https://doi.org/10.1145/3596512) (ACM Transactions on Information Systems, 2023).
- Yu A. Malkov and D. A. Yashunin, [Efficient and Robust Approximate Nearest Neighbor Search Using Hierarchical Navigable Small World Graphs](https://doi.org/10.1109/TPAMI.2018.2889473) (IEEE Transactions on Pattern Analysis and Machine Intelligence, 2020).
