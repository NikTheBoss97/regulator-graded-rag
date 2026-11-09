<!-- Author: Nicola Antonello -->

# Security

Keeping retrieved text from acting as instructions, and keeping the corpus and model files
trustworthy. Part of the [reading list](README.md).

## Prompt injection

- ★ Kai Greshake, Sahar Abdelnabi, Shailesh Mishra, Christoph Endres, Thorsten Holz and Mario Fritz, [Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection](https://doi.org/10.1145/3605764.3623985) (AISec, 2023). Instructions hidden in the data an application retrieves. The reason retrieved text is treated as data, never instructions.
- Edoardo Debenedetti et al., [Defeating Prompt Injections by Design](https://arxiv.org/abs/2503.18813) (arXiv, 2025). Control flow comes from the trusted query, so untrusted retrieved data cannot change it.
- Yupei Liu, Yuqi Jia, Runpeng Geng, Jinyuan Jia and Neil Zhenqiang Gong, [Formalizing and Benchmarking Prompt Injection Attacks and Defenses](https://www.usenix.org/conference/usenixsecurity24/presentation/liu-yupei) (USENIX Security, 2024). A framework for prompt injection attacks and a benchmark of defenses, useful when writing the planted-passage tests.

## The corpus and model files

- Hugging Face, [Pickle Scanning](https://huggingface.co/docs/hub/security-pickle) (Hugging Face documentation). Why loading a pickle file can run arbitrary code, and how the Hub scans for it.
- Hugging Face, [Safetensors](https://huggingface.co/docs/safetensors/index) (Hugging Face documentation). A simple format for storing tensors safely, unlike pickle, so loading weights runs no code.
- Python, [XML Processing Modules](https://docs.python.org/3.14/library/xml.html) (Python documentation), section "XML security". Expat before 2.7.2 may be open to entity-expansion and large-token attacks, so a test pins the minimum version the passage builder parses with.
- Wei Zou, Runpeng Geng, Binghui Wang and Jinyuan Jia, [PoisonedRAG: Knowledge Corruption Attacks to Retrieval-Augmented Generation of Large Language Models](https://www.usenix.org/conference/usenixsecurity25/presentation/zou-poisonedrag) (USENIX Security, 2025). Attacks that plant malicious texts in the knowledge database. Why the corpus is pinned by checksums.
