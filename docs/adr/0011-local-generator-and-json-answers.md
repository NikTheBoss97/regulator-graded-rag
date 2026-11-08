<!-- Author: Nicola Antonello -->

# ADR-0011: A local open-weight generator with one JSON answer format

- Status: accepted
- Date: 2026-11-07
- Supersedes: [ADR-0010](0010-claude-built-in-citations.md)

## Context

After ADR-0010, a models-and-budget plan proposed Claude Haiku 5.5 for day-to-day runs,
with Sonnet 5.5 and Opus 5.5 run once each on dev. Before it was decided, the owner asked
whether open-weight models could replace the paid ones. Most "open source" language
models are open-weight: their weights can be downloaded and run, but their training data
is not published, and their licences range from permissive to restrictive.

The Windows laptop has an 8 GB graphics card, 32 GB of RAM and 160 GB of free disk.
Checked on Hugging Face and GitHub on 2026-11-07:

- Qwen3.5 4B and 9B and Gemma 4 E4B, all Apache-2.0 and from 2026, run entirely on the
  graphics card as 4-bit files. For scale, Qwen3-8B's 4-bit file is 5.0 GB.
- Qwen3.6-35B-A3B, also Apache-2.0, is a mixture-of-experts model: only a few of its many
  sub-networks work on each token. Colibri, an Apache-2.0 engine (v2.1.0, 31 October
  2026), keeps the busiest experts on the graphics card and the others in RAM or on the
  SSD. Its README gives this model as a 23 GB download needing about 20 GB of RAM, at
  about 11 tokens per second on 8 GB cards.
- The frontier models Colibri is known for do not fit: GLM-5.2 and DeepSeek V4 Flash are
  429 GB and 167 GB downloads that run at 0.05-1.6 tokens per second on comparable
  machines, so a 150-question dev run would take a day or more.
- llama.cpp and Ollama, both MIT, can force a JSON format, and llama.cpp takes a fixed
  seed.

## Options

| Option | Why not |
|---|---|
| **Open-weight by default, with Claude answering the dev questions once as a paid comparison** | Chosen. Tuning runs are free and unlimited, runs are more repeatable, and local inference is hands-on. About $4 of Claude runs shows how close a free local model gets to the best models available. |
| Open-weight only, with no paid model calls | Nothing is spent on models, and the comparison is between open models of different sizes. But readers cannot see how far the system is from the best models. |
| Claude by default, with one open-weight model as an experiment | The best answer quality, and built-in citations stay. But every tuning run costs money, and that one comparison would change two things at once: the model and the citation format. |

## Decision

- **The default generator** is a local open-weight model under Apache-2.0 or MIT, from a
  known publisher, run as a 4-bit file pinned by its checksum. Phase 4 tries the small
  models first, then Qwen3.6-35B-A3B through Colibri, and chooses the server: llama.cpp,
  Ollama or Colibri. The local model always picks the most likely next token, with a
  fixed seed.
- **The comparison.** Haiku 5.5, Sonnet 5.5 and Opus 5.5 each answer the dev questions
  once, through the same interface and in the same format, by the Batch API, with the
  owner's go-ahead and a hard cap. Every run pins the full model ID.
- **One answer format for every model:** one JSON object with a `verdict` (`yes`, `no` or
  `not_covered`), an `explanation`, and `quotes`, a list of passage IDs each with the
  text the model copied from that passage. The server's JSON schema or grammar enforces
  the format, and Claude's structured outputs do the same.
- **Code verifies every quote** word for word against its passage in this corpus version.
  A yes or no with no verified quote becomes `not_covered`, and the run record keeps
  both. An answer outside the format is a format failure, and a safety refusal is its
  own outcome.
- **Claude's built-in citations become an experiment**, replacing ADR-0010's decision.

## Consequences

- Answer quality is likely lower than Claude's, by an amount the comparison measures.
- The model will sometimes paraphrase a quote. The check turns that answer into a
  decline, and the oracle run measures how often it happens: the JSON format fixes the
  answer's shape, not the wording of a quote.
- Local runs are slower: by estimate, under an hour per dev run with a 9B model and a few
  hours with the 35B one, run in the background with progress counters.
- A local run should repeat exactly on the same machine, and a repeat run checks that.
  The Claude API version in use rejects sampling settings such as temperature, so
  Claude's answers can vary between runs, and every output is stored.
- On 2026-11-06 the Claude documentation said structured outputs work on Haiku 5.5,
  Sonnet 5.5 and Opus 5.5 and with the Batch API, but cannot be combined with citations
  in one call, and that thinking is billed as output even when its text is hidden.
- Hosting the demo is harder: it needs a server with a graphics card or a paid service,
  and free options are rare. Phase 6 decides it, with measured results.
- Unverified: how well any open model answers these questions, speeds on this laptop, and
  whether Colibri's grammar support can enforce this format.

## References

- Gautier Izacard et al., [Atlas: Few-shot Learning with Retrieval Augmented Language Models](https://jmlr.org/papers/v24/23-0037.html) (JMLR, 2023).
- Tim Dettmers and Luke Zettlemoyer, [The case for 4-bit precision: k-bit Inference Scaling Laws](https://proceedings.mlr.press/v202/dettmers23a.html) (ICML, 2023).
- William Fedus, Barret Zoph and Noam Shazeer, [Switch Transformers: Scaling to Trillion Parameter Models with Simple and Efficient Sparsity](https://jmlr.org/papers/v23/21-0998.html) (JMLR, 2022).
- [Colibri](https://github.com/JustVugg/colibri), [llama.cpp](https://github.com/ggml-org/llama.cpp) and [Ollama](https://github.com/ollama/ollama) on GitHub.
- Claude documentation, [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) and [Pricing](https://platform.claude.com/docs/en/about-claude/pricing).
- Adam Tauman Kalai, Ofir Nachum, Santosh S. Vempala and Edwin Zhang, [Why Language Models Hallucinate](https://arxiv.org/abs/2509.04664) (arXiv, 2025).
