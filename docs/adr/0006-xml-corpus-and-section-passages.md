<!-- Author: Nicola Antonello -->

# ADR-0006: The 2025 XML edition, split into section passages

- Status: accepted
- Date: 2026-11-06

## Context

The corpus is Parts 171–180 of 49 CFR (ADR-0003). GovInfo publishes it in dated annual
editions, as PDF and as XML. Counted on the 2025 edition:

- ten XML files, 10.3 MB and 712,618 words;
- §172.101, the Hazardous Materials Table, holds 82,316 words in 6,386 rows, and the ten
  parts hold 215 tables with 10,350 rows;
- §172.102, the special provisions, holds 25,576 words, including one nested block of
  14,341 words;
- 416 of the 1,069 non-empty sections and appendices are over 400 words;
- there are 125 images, including hazard labels and package markings.

The XML already marks sections, headings, paragraphs and table cells, so there is no page
layout to reconstruct and no table to misread; a PDF parser such as Docling would have to
recover all of that. The open question was the passage: the unit the system retrieves,
shows the generator and cites. Whole sections cannot be that unit, because of their size.

## Options

| Option | Why not |
|---|---|
| **Sections split at paragraph boundaries, at most about 250 words each, with one passage per table row** | Chosen. Every passage belongs to exactly one section, and the letters cite sections, so retrieval is scored exactly. It is simple to build and to check. 250 words is roughly 330 tokens, within the 512-token input limit of many embedding models. Jimeno Yepes et al. found that chunks following a document's structure beat paragraph chunks on financial reports. |
| Fixed-size windows over the running text, such as 250 words with overlap | The usual default in RAG tutorials, but a window would cut across sections, so one passage could mix two rules and a citation would be ambiguous. It would also separate table rows from their column headers. |
| One passage per regulation paragraph, with IDs such as `173.306(a)(3)` | The most precise citations, but about 25,000 passages, half of them 27 words or fewer. A short list item means little without its parent paragraph, so each would need that text attached, and the paragraph numbers must be worked out from markers where "(i)" can be the letter i or the Roman numeral one. |

## Decision

- **The edition.** Parts 171–180 of the 2025 annual edition on GovInfo, revised as of
  1 October 2025, the newest available. It stays fixed for the whole project.
- **A manifest, not copies.** A manifest lists each file's URL, size and SHA-256
  checksum, and one command downloads and checks them. The files are public domain, but
  the checksums already pin them exactly, so committing 10 MB would add nothing. GovInfo
  answers a missing edition with an HTML page and status 200, so the fetch checks the
  file type and the checksum, never only the status.
- **Passages.** Paragraphs are merged in reading order until the next one would pass
  about 250 words, and a passage never crosses a section. A single paragraph over the
  limit is split at sentence ends. Every table row is its own passage, with its column
  headers attached. Every passage starts with its section number and heading, copied
  verbatim.
- **IDs and the corpus version.** A passage's ID is its section number plus its position
  in that section, such as `173.306:4`, and a rebuild gives the same IDs. The corpus
  version is a checksum over every passage's ID and text, so it changes exactly when a
  passage changes.
- **Parse checks, the gate for phase 1.** Apart from the heading and column headers that
  each passage repeats, every word of each section lands in exactly one passage. Every
  table row becomes exactly one passage. The owner compares a sample of the hardest
  passages with the official PDF pages: rows of §172.101, §172.102, §173.62 and
  §173.435.

## Consequences

- A simulation on the edition gives about 13,500 passages: about 10,300 table rows and
  3,200 text passages. A limit of 150 or 400 words would give about 5,100 or 2,300 text
  passages instead. The real builder makes these counts exact.
- §172.102's 14,341-word block has to be split at its nested paragraphs.
- A text-only system cannot read the images, so it should decline questions that need
  one. The 15 images in §173.62 have not been inspected.
- One passage per regulation paragraph becomes the chunking experiment in phase 5.
  Smaller units can retrieve better (Chen et al.), and precise snippets make citations
  easier (Pipitone and Houir Alami), but that has to be shown on this project's own
  questions, not assumed. Fixed-size windows can still be tested as an experiment.
- There is no semantic chunking: Qu et al. found its cost is not repaid by consistent
  gains.
- The token estimate uses a rule of thumb of 1.3 tokens per word.
- The 2026 edition was not available on 2026-11-06. A newer edition would be a new
  corpus version, with every run redone.

## Amendments

- 2026-11-09: ADR-0017 defines how the XML becomes passage text. For the conservation
  check, a section's words are its rule text: the amendment citations and editorial
  notes the publisher appends are left out. Every table row with text becomes one
  passage; the three rows of column numbers label the columns instead.

## References

- GovInfo, [Code of Federal Regulations](https://www.govinfo.gov/app/collection/cfr).
- Antonio Jimeno Yepes, Yao You, Jan Milczek, Sebastian Laverde and Renyu Li, [Financial Report Chunking for Effective Retrieval Augmented Generation](https://arxiv.org/abs/2402.05131) (arXiv, 2024).
- Tong Chen et al., [Dense X Retrieval: What Retrieval Granularity Should We Use?](https://doi.org/10.18653/v1/2024.emnlp-main.845) (EMNLP, 2024).
- Nicholas Pipitone and Ghita Houir Alami, [LegalBench-RAG: A Benchmark for Retrieval-Augmented Generation in the Legal Domain](https://arxiv.org/abs/2408.10343) (arXiv, 2024).
- Renyi Qu, Ruixuan Tu and Forrest Sheng Bao, [Is Semantic Chunking Worth the Computational Cost?](https://aclanthology.org/2025.findings-naacl.114/) (Findings of NAACL, 2025).
- Christoph Auer et al., [Docling Technical Report](https://arxiv.org/abs/2408.09869) (arXiv, 2024).
