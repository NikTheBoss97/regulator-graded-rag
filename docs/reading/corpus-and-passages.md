<!-- Author: Nicola Antonello -->

# The corpus and passages

Where the regulations and the regulator's letters come from, and how the regulations
become passages. Part of the [reading list](README.md).

## The regulations and the letters as data

- ★ eCFR, [API documentation](https://www.ecfr.gov/developers/documentation/api/v1) (eCFR). Its APIs serve each section as it read on any date since 2017, with paragraph IDs: what the drift check compares.
- GovInfo, [Code of Federal Regulations](https://www.govinfo.gov/app/collection/cfr) (GovInfo). The annual editions of the CFR, in PDF and XML. Parts 171–180 of the 2025 edition of Title 49 are this project's corpus.
- GovInfo, [Policies](https://www.govinfo.gov/about/policies) (GovInfo). Its statement that US government works are generally public domain.
- PHMSA, [Hazardous Materials Safety Interpretations](https://catalog.data.gov/dataset/hazardous-materials-safety-interpretations) (data.gov). The dataset entry for the regulator's interpretation letters.
- Internet Archive, [Wayback Machine](https://web.archive.org/) (Internet Archive). Where the letters are read from, because the regulator's own site refuses scripts.
- GPO, [Code of Federal Regulations XML Rendition: User Guide Document](https://www.govinfo.gov/bulkdata/CFR/resources/CFR-XML_User-Guide_v1.pdf) (GPO, 2009). The elements of the CFR's XML, and the warning that its tables may not display as the official PDF does, which is why passages are compared with the printed pages.

## Parsing and chunking

- ★ Renyi Qu, Ruixuan Tu and Forrest Sheng Bao, [Is Semantic Chunking Worth the Computational Cost?](https://aclanthology.org/2025.findings-naacl.114/) (Findings of NAACL, 2025). Semantic chunking against fixed-size chunking on three retrieval tasks: its extra cost is not repaid by consistent gains. Why this project doesn't pay for it.
- Tong Chen et al., [Dense X Retrieval: What Retrieval Granularity Should We Use?](https://doi.org/10.18653/v1/2024.emnlp-main.845) (EMNLP, 2024). The retrieval unit changes results, and propositions are proposed as an alternative to passages. One reason to test finer passages in phase 5.
- Nicholas Pipitone and Ghita Houir Alami, [LegalBench-RAG: A Benchmark for Retrieval-Augmented Generation in the Legal Domain](https://arxiv.org/abs/2408.10343) (arXiv, 2024). A legal retrieval benchmark that rewards minimal, precise snippets, because they use less context and are easier to cite.
- Christoph Auer et al., [Docling Technical Report](https://arxiv.org/abs/2408.09869) (arXiv, 2024). PDF conversion with separate models for layout analysis and table structure: what this project avoids by reading the publisher's XML.
- Yuan Sui, Mengyu Zhou, Mingjie Zhou, Shi Han and Dongmei Zhang, [Table Meets LLM: Can Large Language Models Understand Structured Table Data? A Benchmark and Empirical Study](https://arxiv.org/abs/2305.13062) (WSDM, 2024). How well a language model reads a table depends on how the table is written out as text, so the row format is a recorded choice and a phase 5 experiment.
- Antonio Jimeno Yepes, Yao You, Jan Milczek, Sebastian Laverde and Renyu Li, [Financial Report Chunking for Effective Retrieval Augmented Generation](https://arxiv.org/abs/2402.05131) (arXiv, 2024). Chunks built from a document's structural elements instead of paragraphs alone largely improved RAG results on financial reports. The theory behind passages that follow the regulation's sections and tables.
