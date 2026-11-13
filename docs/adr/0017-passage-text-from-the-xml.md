<!-- Author: Nicola Antonello -->

# ADR-0017: Passage text from the XML

- Status: accepted
- Date: 2026-11-09

## Context

ADR-0006 chose the 2025 XML edition and passages bounded by sections, and left open how
the XML's markup becomes passage text. Measured on 2026-11-09 from the ten Part files:

- **Pretty-printing.** The publisher indents the XML. Every line break inside text was
  added with 4 spaces per level of nesting, and an original space shows as one extra
  space; this held for all 155,225 line breaks. Undoing it exactly gives "5101 et seq.)
  directs", where collapsing the whitespace gives "et seq. ) directs".
- **Superscripts.** 1,437 `E` elements with `T="51"` and 2,857 `SU` elements are raised
  text: footnote markers, units such as `ft<SU>3</SU>`, and the exponents of the A₁ and
  A₂ values in §173.435 and §173.436. Page 788 prints `8.0 × 10<E T="51">−1</E>` as
  8.0 × 10 to the power −1, but joined as plain text it reads `8.0 × 10−1`, another
  number. The 334 `E` elements with `T="52"` are subscripts in formulas, such as H₃AsO₄,
  and the other `E` codes appear to mark emphasis.
- **The publisher's apparatus.** Each section ends with its amendment citations (`CITA`:
  886 of them, 25,204 words, such as "[Amdt. 173-260, 62 FR 24720, May 6, 1997]"), the
  appendices hold 19 more (356 words), and 68 sections carry an editorial note
  (`EDNOTE`: 2,040 words). Neither is rule text, but ADR-0006 says every word of a
  section lands in a passage.
- **Tables.** 215 tables hold 10,350 rows. Column headers come in levels, and 2,218
  rows hold fewer cells than their table has columns. The first rows of three
  tables (§172.101's Hazardous Materials Table, §173.224 and §173.225) are column
  numbers such as "(7)", by which the rules cite columns, and 11 rows are empty. One
  table in §173.319 has six columns but five column labels.
- **Units without body text.** 27 sections and 2 appendices are only "[Reserved]". 29
  other sections are only a heading, such as "§ 179.100-1 Tanks built under these
  specifications shall comply with the requirements of §§ 179.100 and 179.101.", and 2
  appendices are only an image.
- **Images.** 125 images and 32 formulas drawn as images sit in 89 units. §173.62's 15
  images are its table of packing methods, so the packing methods for explosives exist
  only as images.
- **The official format.** GPO's user guide says the XML files are not part of the
  official format of the CFR, and that complex tables in them may not display as the
  tables of the PDF do. This is why the owner compares a sample of passages with the
  printed pages (ADR-0006).
- **Copyright.** The text is a work of the US Government, which GovInfo's policies place
  in the public domain (17 U.S.C. 105), so passages can hold it verbatim.

## Options

What counts as a section's words:

| Option | Why not |
|---|---|
| **The rule text: amendment citations and editorial notes are left out** | Chosen. Passages hold only what the rules say, and the build reports the left-out words, so nothing disappears unnoticed. |
| Every word, the apparatus included | What ADR-0006 said. It adds 143 passages, and about 940 of the 3,300 text passages would end in a citation or a note, which puts Federal Register numbers and dates into keyword search and gives the generator text to quote that is not a rule. |
| The apparatus in passages of its own | Every word is kept apart from the rules, but these passages can still be retrieved and quoted, and no question asks about them. |

Superscripts:

| Option | Why not |
|---|---|
| **A `^` before the raised text, as in `8.0 × 10^−1`** | Chosen. The value stays readable and searchable, and the source never contains `^`, so the marker cannot be mistaken for text. |
| Unicode superscript characters | They look right, but exist for digits and only some letters, so some raised text would need a fallback, and tokenizers split them unevenly. |
| Plain text | Every A₁ and A₂ value would read as another number. |

Table rows:

| Option | Why not |
|---|---|
| **The table's title and description, then one `label: value` line per non-empty cell** | Chosen. Each value carries its column's name, so a row of the 14-column Hazardous Materials Table reads `(7) Special provisions (§ 172.102): IB2, T4, TP1`. |
| A header line, then the values separated by `\|` | Shorter, but matching a value with its header means counting columns, which is hard on a 14-column row. |
| The values alone | Shortest, but loses which column each value is in, while the rules cite columns by number. |

The parser:

| Option | Why not |
|---|---|
| **`xml.etree.ElementTree` from the standard library, on Expat 2.7.2 or newer** | Chosen. No new dependency. Python's documentation says Expat before 2.7.2 may be open to entity-expansion and large-token attacks; the Windows laptop's Python 3.14.7 bundles Expat 2.8.2, and a test pins the minimum everywhere. A file is parsed only after its size and SHA-256 match the manifest. |
| lxml | Faster, with XPath, but a C library and a new dependency, whose entity handling has to be configured. |
| A hardened wrapper such as defusedxml | A dependency for protections Expat 2.7.2 already has. |

## Decision

- **A section's words are its rule text.** The amendment citations (`CITA`) and
  editorial notes (`EDNOTE`) are left out, and the build counts the words it leaves
  out. The parse checks compare passages with the rule text alone.
- **Exact spacing.** The pretty-printing is undone exactly: a line break followed by the
  expected indentation is removed, and one more space is an original space. Any other
  indentation, or a line break that remains, stops the build. Soft hyphens are dropped,
  and each run of whitespace, typographic spaces included, becomes one space.
- **Inline markup.** Superscripts (`SU`, and `E` with `T="51"`) become `^` and their
  text. Other `E` codes and footnote references give their text. A fraction (`FR`) gets
  a space when it follows a letter or a digit, so `1<FR>1/2</FR>` reads `1 1/2`. A line
  break inside a cell or a header (`LI`) and the parts of a label–value line (`FL-2`,
  `LDRFIG`) become a space. Page markers (`PRTPAGE`) add no text and set the printed
  page.
- **Blocks.** `P`, `FP`, `HD`, `APPRO`, `SECAUTH`, `LDRWK`, `TCAP` and `RESERVED` are
  paragraphs. `NOTE`, `EXTRACT`, `EXAMPLE`, `FTNT` and the images and formulas (`GPH`,
  `MATH`) are read child by child: an image's file name adds nothing, and its caption is
  a paragraph.
- **Text passages.** Paragraphs merge in reading order while they total at most 250
  words. A longer paragraph splits at sentence ends, and a sentence over the limit stays
  whole. A passage never crosses a unit, and starts with the unit's heading.
- **Table rows.** Each row with text is one passage: the heading, the table's title and
  description, then one `label: value` line per non-empty cell. A label joins the header
  levels above its column, and a value past the last label has none. The three rows of
  column numbers prefix the labels, as in `(8A) (8) Packaging (§ 173.***) Exceptions`,
  instead of becoming passages, and empty rows are dropped and counted. A table's notes
  become text passages after its rows.
- **Units.** Sections and appendices are the units; reserved ones get no passage. A unit
  with no body text gets one passage holding its heading, so a question citing it can
  still retrieve it. A section's key is its number, such as `173.304a` or `178.337-10`,
  and an appendix's comes from its `EAR`, such as `172.appA` or `178.subptC.appA`.
- **IDs and the corpus version.** A passage's ID is its unit's key and its position in
  the unit, counted from 1, such as `173.306:4`. The corpus version is the SHA-256 of one
  JSON line `[id, text]` per passage, in build order, in UTF-8 with non-ASCII characters
  kept as they are.
- **Unknown markup stops the build.** An element the builder does not know raises an
  error naming the element and the unit, so no text is dropped silently.

## Consequences

- Text cannot carry the 125 images and 32 formulas, §173.62's packing methods among
  them, so questions that need one should be declined.
- A prototype of these rules gave 13,539 passages: 3,203 text passages, 31 of them a
  heading alone, and 10,336 rows. The builder makes the counts exact.
- Passages leave out the 27,600 words of the citations and notes, and the build reports
  that count.
- A row is never split, so 15 rows of §176.708 hold more than 250 words, at most 358.
- In one row of §173.435 (Rb(nat)) the source tags a minus apart from its superscript,
  so two cells read `6.7 × 10 −^10` and `1.8 × 10 −^8`.
- Six tables have column labels that rows can misplace. §173.319's header lacks a level,
  §173.301's labels are empty, and §176.708, §178.275 and the two tables of §178.348-2
  repeat labels, because the source puts sub-headers in body rows or two tables side by
  side; one cell of §176.708 also carries an `A` attribute, apparently a span, which the
  builder does not read. In §178.348-2 a row of thicknesses no longer says which lading
  density each value is for. The build reports each of these tables, and the owner's
  comparison with the printed pages includes §176.708 and §178.348-2.
- How a table is written out as text changes how well a language model reads it (Sui et
  al.), so this row format is the baseline for phase 5's table-handling experiment.
- Unverified: the meaning of the `E` codes other than 51 and 52, which was inferred from
  the data and checked against the printed page only for §173.435, and how reliably
  GovInfo answers CI's downloads.

## Amendments

- 2026-11-13: The owner compared 25 sampled passages with the printed pages
  (`corpus/parse-review.md`). Where five rows of §173.435 read A1 and A2, the pages set
  A₁ and A₂ as subscripts, which confirms that `E` with `T="52"` marks a subscript; the
  section's heading tags the same two digits with `T="9145"` instead. Each of the 334
  subscripts follows a letter, a bracket, a slash or another subscript, never a digit,
  so none merges with a number before it. Joined to the letter before it, a subscript
  reads like a number only in one formula of §173.24b, printed twice: `(12.74e0)` and
  `(144.2e0)` mean 12.74 and 144.2 times e₀, which the lines below the formula define.
  The source itself writes A1 and A2 untagged in §173.427 and §173.433, and LC50
  untagged 30 times, and a marker such as `_` would be ambiguous, because the source
  holds 853 underscores. The owner kept subscripts as plain text, with that formula as
  the known exception. Plain A1 and A2 also spell special provisions A1 and A2, in 112
  places of §172.101 and §172.102, and only the column label or the sentence tells them
  apart.
- 2026-11-13: Two of the owner's notes are answered by the source. The source tags all
  16 cent signs of Part 172, such as the one after "Beryllium powder", with `T="51"`, so
  passages write `^¢`; the owner was not sure the page prints that ¢ raised, so whether
  `T="51"` always prints raised stays unverified. The three Ethylene cells of
  §173.319's 17 psig row are empty in the source, so that passage has no line for them,
  as decided.
- 2026-11-13: The owner's note on the first row of §172.102's IB8 table ("These are
  table headers") led to two tables whose sub-headers sit in a body row: the IB3 and IB8
  tables, whose first row reads "Inner packagings:" and "Large outer packagings:". The
  build does not report them, so eight tables, not the six above, have column labels
  that can mislead.
- 2026-11-13: The owner's notes show two consequences of these rules. A special
  provision's code is the first word of its paragraph: the source separates it from the
  text with an em space (U+2003) in 366 of the 375 paragraphs of §172.102 that start
  with a code, and with a plain space in 9, and the whitespace rule turns both into a
  space, so a passage reads "40 Polyester resin kits …" where the page sets the code
  apart. A paragraph over 250 words splits at a sentence end, so its later passages
  lose the code, as in special provision 340 (258 words).

## References

- GPO, [Code of Federal Regulations XML Rendition: User Guide Document](https://www.govinfo.gov/bulkdata/CFR/resources/CFR-XML_User-Guide_v1.pdf) (2009).
- Python, [XML Processing Modules](https://docs.python.org/3.14/library/xml.html), section "XML security".
- GovInfo, [Policies](https://www.govinfo.gov/about/policies), section "Public Domain & Copyright Notice".
- Yuan Sui, Mengyu Zhou, Mingjie Zhou, Shi Han and Dongmei Zhang, [Table Meets LLM: Can Large Language Models Understand Structured Table Data? A Benchmark and Empirical Study](https://arxiv.org/abs/2305.13062) (WSDM, 2024).
