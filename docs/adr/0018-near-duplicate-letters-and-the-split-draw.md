<!-- Author: Nicola Antonello -->

# ADR-0018: Near-duplicate letters and the split draw

- Status: accepted
- Date: 2026-11-14

## Context

ADR-0008 splits the regulator's letters into dev and held-out by code, before anyone
reads them: near-duplicate letters and letters that cite each other are grouped, because
a question with a near-copy on the other side of a split leaks its answer (Lewis et al.),
and a committed seed sends 40% of each year's groups to held-out. It left the grouping
method and the draw's details to phase 2. What bears on them:

- **The method must work blind.** Nobody reads a letter before the split, so the
  grouping can be checked only through counts: how many letters link, how close the
  rest come, and how large the groups are.
- **The pool,** measured on 2026-11-14 and 2026-11-15 from the archive's index and the
  pages' structure, without reading a letter. The Internet Archive's index (its CDX API)
  holds 903 letters with reference numbers from 2017 on: 118, 132, 107, 75, 95, 97, 75,
  92, 81 and 31 for the years 2017 to 2026. Numbers from 96- to 99- are letters of the
  1990s, outside the pool. Each letter is read from its newest capture that reads as a
  letter page, and 887 letters have a capture from 2026. 898 letters read as letter
  pages; the other 5 exist only as PDFs, so their pages hold no text, and 2 of the 898
  hold a single paragraph of under 100 characters.
- **The frame.** The letters read during the design open and close the same way: a
  salutation, a standard opening, a closing and a signature. Compared whole, two
  unrelated letters share those words.
- **The draw's reproducibility.** Python's `random` module guarantees across versions
  only that `random()` gives the same sequence for the same seed; `sample` and `shuffle`
  may change. A split drawn with them could change with the Python that reruns it.

## Options

Finding near-duplicate letters:

| Option | Why not |
|---|---|
| **Exact shingle overlap: the Jaccard similarity of 5-word shingles, after the frame is removed** | Chosen. About 400,000 pairs compare exactly in seconds, with no dependency and no randomness. Lee et al. found near-duplicates in training corpora with the same 5-word shingles. |
| MinHash with locality-sensitive hashing | An approximation of the same measure (Broder; Leskovec et al.), built for millions of documents. At 903 letters the exact measure is cheap, and MinHash would add a dependency and seeded randomness. |
| TF-IDF or embedding similarity | It would catch reworded letters, but its threshold cannot be set without reading letters, and it needs scikit-learn or the embedding model phase 3 chooses. |

Drawing the groups:

| Option | Why not |
|---|---|
| **A SHA-256 key per group, drawn by year** | Chosen. The same on any machine and Python version, and a test pins a key. |
| `random.sample` with a seed | Python does not promise that `sample` draws the same groups in a later version. |
| By date, holding out the newest letters | Rejected by ADR-0008: dev and held-out would come from different years. |

## Decision

1. **Shingles.** A letter's response text is lowercased and split into words (`\w+`).
   Its shingles are every run of 5 consecutive words; a text of 1 to 4 words gives one
   shingle of all its words.
2. **The frame is removed.** A shingle found in more than a fifth of the letters with
   text is part of the frame, and is dropped from every letter before comparing.
3. **Links.** Two letters link when the Jaccard similarity of their remaining shingles
   is at least 0.5, or when one cites the other's reference number. A citation is a
   number of the form `NN-NNNN` that is not part of a longer token, such as a docket
   number or a ZIP+4 code, is in the pool and is not the letter's own. A letter without
   text links only by citations.
4. **Groups** are the connected components of the links. A group of more than 20
   letters stops the split and goes to the owner; changing a threshold then is an
   amendment to this record before any split is drawn.
5. **The draw.** A group's year is the reference year of its lowest-numbered letter. In
   each year, 40% of the groups, rounded half up (`(4n + 5) // 10`), go to held-out:
   those with the lowest keys, where a group's key is the SHA-256 of the seed, a colon
   and its lowest letter number. The groups holding the three letters already read
   (20-0003, 20-0018 and 20-0034) go to dev, and held-out is drawn from the year's other
   groups, so 2020 still sends 40% of all its groups to held-out.
6. **The seed** is the corpus version,
   `ecaac596422344e6b548dcd8a1816261a27d398d0d707077def27a5976db34ef`, fixed before any
   letter was listed, so nobody can have chosen it to shape the split.
7. **The owner's choices of 2026-11-14:**
   - the pool includes 2026's letters, as letters written after the edition qualify
     like the others (ADR-0007);
   - each letter is read from its newest readable capture;
   - until the split, every letter file lives under `eval/heldout/unsplit/`, which the
     held-out rules guard; the split moves dev letters to `eval/letters/dev/` and
     held-out letters to `eval/heldout/letters/`.
8. **Once.** The split is drawn once: the command refuses to run when `eval/split.jsonl`
   exists, and the letter listing then refuses too, so the pool is frozen. The script
   prints counts only.

## Consequences

- **Reworded duplicates are missed.** Shingle overlap catches copies, not paraphrases:
  Yang et al. show that n-gram overlap misses rephrased test items. An embedding audit,
  printing counts only, can follow once phase 3 has chosen a model.
- **Both thresholds were set blind.** The report's histogram of each letter's best
  similarity shows how close letters come to 0.5.
- **Letters without text** are grouped only by citations.
- **The pool is what the archive captured,** frozen by the committed manifest
  (`eval/letters.jsonl`) and the assignment (`eval/split.jsonl`), which hold letter
  numbers, captures and checksums, never text.
- **Unverified** until the split runs: how many letters link.

## Amendments

- 2026-11-15: The split was drawn as decided, on Python 3.14.7, and the assignment's
  SHA-256 is the reviewed dry run's digest, `a2215b4c…`. The near-duplicate report:
  - 903 letters, 5 of them without text; 3 links by text and 41 by citation.
  - Each letter's highest similarity to another, by tenths from 0.0–0.1 to 0.9–1.0:
    820, 57, 6, 7, 2, 0, 0, 6, 0 and 0 letters. No letter falls between 0.5 and 0.7,
    though 2 fall just below the threshold, between 0.4 and 0.5.
  - 862 groups: 825 single letters, 33 pairs and 4 groups of three.
  - Seven reference-shaped strings use a Unicode dash, not the hyphen the citation
    pattern reads. None cites another letter in the pool, so no link was missed
    (counted without reading the letters).

  | Year | Groups | Letters | Dev groups | Held-out groups |
  |---|---|---|---|---|
  | 2017 | 117 | 126 | 70 | 47 |
  | 2018 | 132 | 138 | 79 | 53 |
  | 2019 | 103 | 108 | 62 | 41 |
  | 2020 | 67 | 71 | 40 | 27 |
  | 2021 | 92 | 99 | 55 | 37 |
  | 2022 | 92 | 97 | 55 | 37 |
  | 2023 | 68 | 70 | 41 | 27 |
  | 2024 | 86 | 89 | 52 | 34 |
  | 2025 | 77 | 77 | 46 | 31 |
  | 2026 | 28 | 28 | 17 | 11 |
  | **Total** | **862** | **903** | **517 (543 letters)** | **345 (360 letters)** |

  A group counts in the year of its lowest-numbered letter, so 2017's groups hold 126
  letters: its own 118 and 8 later letters joined to them. The three letters already
  read are in dev.

## References

- Andrei Z. Broder, [On the Resemblance and Containment of Documents](https://doi.org/10.1109/SEQUEN.1997.666900) (Compression and Complexity of Sequences, 1997).
- Jure Leskovec, Anand Rajaraman and Jeffrey D. Ullman, [Mining of Massive Datasets](https://doi.org/10.1017/9781108684163) (Cambridge University Press, 3rd ed., 2020), chapter 3.
- Katherine Lee et al., [Deduplicating Training Data Makes Language Models Better](https://doi.org/10.18653/v1/2022.acl-long.577) (ACL, 2022).
- Shuo Yang, Wei-Lin Chiang, Lianmin Zheng, Joseph E. Gonzalez and Ion Stoica, [Rethinking Benchmark and Contamination for Language Models with Rephrased Samples](https://arxiv.org/abs/2311.04850) (arXiv, 2023).
- Patrick Lewis, Pontus Stenetorp and Sebastian Riedel, [Question and Answer Test-Train Overlap in Open-Domain Question Answering Datasets](https://doi.org/10.18653/v1/2021.eacl-main.86) (EACL, 2021).
- Python, [random: Notes on Reproducibility](https://docs.python.org/3.14/library/random.html#notes-on-reproducibility).
- Internet Archive, [Wayback CDX Server API](https://github.com/internetarchive/wayback/blob/master/wayback-cdx-server/README.md).
