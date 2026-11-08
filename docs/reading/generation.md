<!-- Author: Nicola Antonello -->

# Generation

Writing answers from retrieved passages, running open-weight models on a laptop, and
making answers checkable. Part of the [reading list](README.md).

## Retrieval-augmented generation

- ★ Chip Huyen, [AI Engineering](https://github.com/chiphuyen/aie-book) (O'Reilly, 2025). A practitioner's textbook and the closest match to this project: chapters 3 and 4 cover evaluation, and chapter 6 covers RAG.
- ★ Dan Jurafsky and James H. Martin, [Speech and Language Processing, 3rd edition draft](https://web.stanford.edu/~jurafsky/slp3/) (online manuscript, 2026). Free online. Chapter 11, "Information Retrieval and RAG", is the textbook route through the core of this project; chapter numbers can move between drafts.
- Nelson F. Liu et al., [Lost in the Middle: How Language Models Use Long Contexts](https://doi.org/10.1162/tacl_a_00638) (TACL, 2024). Models often miss information in the middle of a long context, so passage order matters. It studied the models of its time, so test the effect on yours.
- Gautier Izacard et al., [Atlas: Few-shot Learning with Retrieval Augmented Language Models](https://jmlr.org/papers/v24/23-0037.html) (JMLR, 2023). From 64 examples, a retrieval-augmented model reaches over 42% on Natural Questions, beating a 540B-parameter model while having 50 times fewer parameters. Why a small local model with good retrieval is a fair default.
- Yunfan Gao et al., [Retrieval-Augmented Generation for Large Language Models: A Survey](https://arxiv.org/abs/2312.10997) (arXiv, 2023). A map of the field: naive, advanced and modular RAG, and how each is evaluated.
- Patrick Lewis et al., [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html) (NeurIPS, 2020). The paper that named RAG.

## Running models locally

- ★ Tim Dettmers and Luke Zettlemoyer, [The case for 4-bit precision: k-bit Inference Scaling Laws](https://proceedings.mlr.press/v202/dettmers23a.html) (ICML, 2023). At a fixed memory budget, a bigger model at 4 bits almost always beats a smaller one at higher precision. Why the local models run as 4-bit files.
- [llama.cpp](https://github.com/ggml-org/llama.cpp) (GitHub). Inference in C and C++ for running models locally, with grammars that constrain the output format.
- [Ollama](https://github.com/ollama/ollama) (GitHub). A local model server that can force answers into a JSON schema.
- [Colibri](https://github.com/JustVugg/colibri) (GitHub). An engine for mixture-of-experts models that keeps the busiest experts on the graphics card and the rest in RAM or on disk.
- William Fedus, Barret Zoph and Noam Shazeer, [Switch Transformers: Scaling to Trillion Parameter Models with Simple and Efficient Sparsity](https://jmlr.org/papers/v23/21-0998.html) (JMLR, 2022). A mixture-of-experts model picks different parameters for each input, so it can hold far more parameters at a constant compute cost. Why a 35B model with about 3B active parameters can run on a laptop.

## Checkable answers and declining

- ★ Nelson F. Liu, Tianyi Zhang and Percy Liang, [Evaluating Verifiability in Generative Search Engines](https://doi.org/10.18653/v1/2023.findings-emnlp.467) (Findings of EMNLP, 2023). Defines citation recall and citation precision, and audits four real generative search engines with them.
- Claude documentation, [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) (Claude Docs). How the API forces an answer into a JSON schema, as the paid comparison uses it.
- Claude documentation, [Citations](https://platform.claude.com/docs/en/build-with-claude/citations) (Claude Docs). Built-in citations that point into the documents sent: the first design, now an experiment.
- Claude documentation, [Search results](https://platform.claude.com/docs/en/build-with-claude/search-results) (Claude Docs). The format for passing retrieved passages so that citations point into them.
- Adam Tauman Kalai, Ofir Nachum, Santosh S. Vempala and Edwin Zhang, [Why Language Models Hallucinate](https://arxiv.org/abs/2509.04664) (arXiv, 2025). Training and evaluation reward guessing over admitting uncertainty, and the fix includes changing how benchmarks score. Why the false-answer rate sits next to accuracy.
- Bingbing Wen et al., [Know Your Limits: A Survey of Abstention in Large Language Models](https://doi.org/10.1162/tacl_a_00754) (TACL, 2025). Methods, benchmarks and metrics for a model declining to answer.
- Tianyu Gao, Howard Yen, Jiatong Yu and Danqi Chen, [Enabling Large Language Models to Generate Text with Citations](https://doi.org/10.18653/v1/2023.emnlp-main.398) (EMNLP, 2023). ALCE, a benchmark with automatic metrics for citation quality.
