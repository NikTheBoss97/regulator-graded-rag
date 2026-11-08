<!-- Author: Nicola Antonello -->

# Retrieval

Keyword search, dense and hybrid retrieval, reranking and vector search. Part of the
[reading list](README.md).

## Keyword search

- ★ Stephen Robertson and Hugo Zaragoza, [The Probabilistic Relevance Framework: BM25 and Beyond](https://doi.org/10.1561/1500000019) (Foundations and Trends in Information Retrieval, 2009). Where BM25 comes from: why each repeat of a word adds less, and why passage length is normalised. The origin of the idea, paired with Kamphuis et al.
- PostgreSQL, [Controlling Text Search](https://www.postgresql.org/docs/current/textsearch-controls.html) (PostgreSQL documentation). How Postgres turns text into searchable terms, and why its built-in ranking functions, which "do not use any global information", are not BM25.
- [bm25s](https://github.com/xhluca/bm25s) (GitHub). A fast BM25 library in Python whose default is Lucene's BM25: the independent reference that this project's SQL version is tested against.
- Chris Kamphuis, Arjen P. de Vries, Leonid Boytsov and Jimmy Lin, [Which BM25 Do You Mean? A Large-Scale Reproducibility Study of Scoring Variants](https://doi.org/10.1007/978-3-030-45442-5_4) (ECIR, 2020). Eight BM25 variants on three newswire collections, with no significant differences. Record which variant you use, but don't expect it to matter much on collections like those.
- Wei Yang, Kuang Lu, Peilin Yang and Jimmy Lin, [Critically Examining the "Neural Hype": Weak Baselines and the Additivity of Effectiveness Gains from Neural Ranking Models](https://doi.org/10.1145/3331184.3331340) (SIGIR, 2019). Only one of five recent neural models significantly improved a strong baseline when reranking it. Why the BM25 baseline has to be the real thing; the recent treatment of Armstrong et al.
- Timothy G. Armstrong, Alistair Moffat, William Webber and Justin Zobel, [Improvements That Don't Add Up: Ad-Hoc Retrieval Results Since 1998](https://doi.org/10.1145/1645953.1646031) (CIKM, 2009). A decade of claimed improvements, mostly over weak baselines, with little evidence that retrieval got better. The origin of the weak-baseline critique.

## Dense and hybrid retrieval, and reranking

- ★ Sebastian Bruch, Siyu Gai and Amir Ingber, [An Analysis of Fusion Functions for Hybrid Retrieval](https://doi.org/10.1145/3596512) (ACM Transactions on Information Systems, 2023). Reciprocal rank fusion proves sensitive to its parameters, while a convex combination of scores beats it and needs only a few examples to tune. Why the fusion method is settled by experiment.
- Jimmy Lin, Rodrigo Nogueira and Andrew Yates, [Pretrained Transformers for Text Ranking: BERT and Beyond](https://doi.org/10.1007/978-3-031-02181-7) (Springer, 2022). Multi-stage reranking and dense retrieval, from the people who built much of it. A free copy is on [arXiv](https://arxiv.org/abs/2010.06467).
- Vladimir Karpukhin et al., [Dense Passage Retrieval for Open-Domain Question Answering](https://doi.org/10.18653/v1/2020.emnlp-main.550) (EMNLP, 2020). Separate question and passage encoders, trained so that matching pairs score high: the paper that showed dense retrieval beating BM25 on question answering benchmarks.
- Rodrigo Nogueira and Kyunghyun Cho, [Passage Re-ranking with BERT](https://arxiv.org/abs/1901.04085) (arXiv, 2019). A cross-encoder that scores each question and passage pair: the simple design behind the reranking stage.
- Gordon V. Cormack, Charles L. A. Clarke and Stefan Buettcher, [Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods](https://doi.org/10.1145/1571941.1572114) (SIGIR, 2009). The origin of reciprocal rank fusion: combining rankings by rank alone, so scores need no calibration. Paired with Bruch et al.

## Vector search

- [pgvector](https://github.com/pgvector/pgvector) (GitHub). Vector similarity search inside Postgres, exact or through approximate indexes such as HNSW.
- Yu A. Malkov and D. A. Yashunin, [Efficient and Robust Approximate Nearest Neighbor Search Using Hierarchical Navigable Small World Graphs](https://doi.org/10.1109/TPAMI.2018.2889473) (IEEE Transactions on Pattern Analysis and Machine Intelligence, 2020). HNSW, the graph index many vector stores offer. It is approximate, so a miss can come from the index rather than the embedding, which is why this project searches exactly.
