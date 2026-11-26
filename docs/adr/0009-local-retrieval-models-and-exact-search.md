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

## Amendments

- 2026-11-25: The versions and pins phase 3 runs with.
  - The models run from a `models` dependency group that CI never installs: torch
    2.14.1 (PyTorch's CUDA 12.6 build on Windows, PyPI's elsewhere), sentence-transformers
    6.3.0 and transformers 5.23.0, the newest 5.x release past the 7-day cooldown. The
    group's other new dependencies were locked under the same cooldown, and no module
    imports these packages when it loads.
  - Each model is pinned by its revision and by its `model.safetensors` SHA-256, both read
    from the Hugging Face API at that revision, in the table below. The loader checks the
    file's SHA-256 before loading it, and never loads a pickle file or code from the
    model's repository; three of the six repositories also hold a `pytorch_model.bin`.
  - The query formats, verified in each model's files at its revision: bge-base-en-v1.5
    puts `Represent this sentence for searching relevant passages: ` before a question,
    Qwen3-Embedding-0.6B puts `Instruct: Given a web search query, retrieve relevant
    passages that answer the query`, a newline and `Query:`, and gte-modernbert-base puts
    nothing. Passages never get a prefix.
  - bge-reranker-v2-m3's weights take 2.27 GB, more than the 0.1-1.2 GB estimated above;
    the others take 0.09-1.19 GB.

| Model | Revision | `model.safetensors` SHA-256 | Bytes |
|---|---|---|---|
| BAAI/bge-base-en-v1.5 | a5beb1e3e68b9ab74eb54cfd186867f64f240e1a | c7c1988aae201f80cf91a5dbbd5866409503b89dcaba877ca6dba7dd0a5167d7 | 437,955,512 |
| Alibaba-NLP/gte-modernbert-base | e7f32e3c00f91d699e8c43b53106206bcc72bb22 | 3e85899d5728cb7de79781c0c3acfb91ccef9f875f1f7e0b3c9f3dd4b6a724ba | 298,041,568 |
| Qwen/Qwen3-Embedding-0.6B | 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3 | 0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd | 1,191,586,416 |
| cross-encoder/ms-marco-MiniLM-L6-v2 | 233902d25c440f23af6f7d6e94d2946bac0bee0a | 821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae | 90,870,598 |
| BAAI/bge-reranker-v2-m3 | 953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e | d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286 | 2,271,071,852 |
| Qwen/Qwen3-Reranker-0.6B | e61197ed45024b0ed8a2d74b80b4d909f1255473 | 27cd75a405b9c1b46b59abfd88aaa209e6fed2a1972cde9b70e7659537c5e65b | 1,191,588,280 |

- 2026-11-25: A model's precision is a setting of its dense stage (the owner's choice).
  Transformers otherwise picks it from the model's files: bge-base loaded in float32,
  but Qwen3-Embedding and gte-modernbert ship 16-bit weights, so they would have run in
  16 bits, a second change that no record showed.
  - A dense config may state `dtype` as float32, float16 or bfloat16. A config that
    states none runs in float32, as E1 did, so E1's committed config, which is never
    edited, still reads as it ran.
  - The dtype joins the cache key, the vectors file's header and the meta table. A
    dense stage refuses vectors made with another dtype or max_length, and vectors
    loaded before these were recorded.
  - The run record names, besides the vectors' SHA-256, their dtype, the count of
    passages cut to the input length, the GPU, and torch's and CUDA's versions.
- 2026-11-26: The encoder compares the precision the model loaded in with its config's
  and refuses a mismatch, so the record's dtype is the one the model ran in, not only
  the one asked for. The record names the device by its name for a CUDA GPU and by its
  type otherwise, such as "mps" for Apple's GPU.

## References

- Hugging Face model cards: [bge-base-en-v1.5](https://huggingface.co/BAAI/bge-base-en-v1.5), [gte-modernbert-base](https://huggingface.co/Alibaba-NLP/gte-modernbert-base), [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B), [ms-marco-MiniLM-L6-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2), [bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) and [Qwen3-Reranker-0.6B](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B).
- uv documentation, [Using uv with PyTorch](https://docs.astral.sh/uv/guides/integration/pytorch/).
- Vladimir Karpukhin et al., [Dense Passage Retrieval for Open-Domain Question Answering](https://doi.org/10.18653/v1/2020.emnlp-main.550) (EMNLP, 2020).
- Rodrigo Nogueira and Kyunghyun Cho, [Passage Re-ranking with BERT](https://arxiv.org/abs/1901.04085) (arXiv, 2019).
- Jimmy Lin, Rodrigo Nogueira and Andrew Yates, [Pretrained Transformers for Text Ranking: BERT and Beyond](https://doi.org/10.1007/978-3-031-02181-7) (Springer, 2022).
- Sebastian Bruch, Siyu Gai and Amir Ingber, [An Analysis of Fusion Functions for Hybrid Retrieval](https://doi.org/10.1145/3596512) (ACM Transactions on Information Systems, 2023).
- Yu A. Malkov and D. A. Yashunin, [Efficient and Robust Approximate Nearest Neighbor Search Using Hierarchical Navigable Small World Graphs](https://doi.org/10.1109/TPAMI.2018.2889473) (IEEE Transactions on Pattern Analysis and Machine Intelligence, 2020).
