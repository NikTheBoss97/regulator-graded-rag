<!-- Author: Nicola Antonello -->

# ADR-0005: BM25 written in SQL

- Status: accepted
- Date: 2026-11-05

## Context

BM25 ranks passages by keywords. It scores a passage on how often each query word appears
in it, with each repeat adding less; on how rare that word is across the collection, its
inverse document frequency (IDF); and on the passage's length. `k1` sets how quickly
repeats stop adding score, and `b` how much long passages are penalised.

Every later retrieval method is measured against BM25, so it has to be the real thing.
Armstrong et al. and Yang et al. found that published gains measured against weak
baselines often vanish against strong ones. ADR-0004 puts search inside Postgres.

## Options

| Option | Why not |
|---|---|
| **BM25 written in SQL over Postgres's own tokenizer, checked against bm25s** | Chosen. Plain tables and one query, which run on the standard pgvector image and on any managed Postgres with pgvector. A test proves it is real BM25 by comparing its scores with bm25s, an independent library (MIT, v0.3.16) whose default is Lucene's BM25. It costs about a day of work and 50-80 lines of SQL to maintain, and it is slower than an extension at millions of passages; this corpus has about 13,500 (ADR-0006). |
| Postgres's built-in ranking, `ts_rank` | It is not BM25. The Postgres documentation says its ranking functions "do not use any global information", so there is no IDF: a rare word like *aerosol* counts no more than a common one like *shipment*. By default it also ignores passage length. As the baseline, it would flatter every later method. |
| The pg_textsearch extension, from Timescale | Real BM25 with adjustable `k1` and `b` on Postgres's own tokenizer, under the PostgreSQL licence; version 1.5.1 came out on 2 October 2026 for Postgres 17 and 18. But it needs its own Docker image and a preload setting, and no free managed host offered it: Neon did not list it, and Supabase's image did not include it. |
| ParadeDB's pg_search | Mature, but under AGPL-3.0, and Neon stopped offering it to new projects on 19 March 2026. |
| VectorChord-bm25 | Under AGPL-3.0 or the Elastic licence, and its last release was in December 2025. |

## Decision

Keyword search is BM25 written in SQL:

- Postgres splits and stems passages and questions with the same text search
  configuration.
- Plain tables hold each passage's term counts and length, and how many passages contain
  each term.
- One SQL query computes BM25 for a question, with `k1` and `b` as settings.
- A test gives bm25s the same tokens and compares the scores.

`ts_rank` is not used for ranking. If the SQL version ever becomes too slow, moving to an
extension is a contained change, with the same tokenizer and interface, run as its own
experiment.

## Consequences

- Once its test passes, it is as real a BM25 as an extension's, and every part of the
  formula can be explained.
- The database stays standard: simpler setup now, and cheaper hosting for the demo.
- The test checks scoring, not tokenizing. bm25s receives Postgres's tokens, so
  Postgres's English stemming is a separate choice that the test does not judge.
- Its speed is unmeasured until phase 2, and every run records it.
- Kamphuis et al. found no significant differences between eight BM25 variants on three
  newswire collections, so recording which variant is used matters more than the choice.

## Amendments

- 2026-11-15: What was built, as phase 2 measured it:
  - **The variant.** The one bm25s calls "lucene", its default. It has Lucene's IDF and
    no (k1 + 1) factor in the numerator, which Lucene itself dropped in version 8.0
    because it scales every score alike (LUCENE-8563). Unlike Lucene, which stores a
    passage's length in one byte, it uses exact lengths, so its scores match bm25s's,
    not Lucene's own. k1 is 1.2 and b 0.75, the defaults of Lucene and Elasticsearch,
    fixed before any dev run. Postgres's `english` configuration splits and stems both
    passages and questions, a repeated query word counts each time, and an index built
    with another configuration is refused. Every number is double precision, and ties
    break in corpus order.
  - **The check.** On all 13,539 passages, for five questions, the SQL scores equal
    those of bm25s 0.3.16 in float64 to a relative 1e-9. bm25s gets its tokens from the
    passages' text, not from the index's counts. A changed IDF constant, dropping the
    count of a repeated query word, or a term count of 1 fails it. A tie broken by ID
    or not at all fails the test of corpus order.
  - **The index.** It holds 16,318 lexemes and 869,605 tokens and builds in about 5
    seconds. The build analyzes its tables: autovacuum never analyzes the one-row
    statistics table, and without its statistics the planner chose a plan about five
    times slower.
  - **The speed.** On the Windows laptop, with Postgres in Docker on WSL2, 20 searches
    of the top 50 passages took a median of 20 to 30 ms and at most 68 to 116 ms, over
    three runs. Before the build analyzed its tables, they took a median of 208 to
    322 ms.
  - **Postgres's limits.** A tsvector holds at most 256 positions per lexeme, and a
    position is at most 16,383. A test shows the corpus reaches neither: no position
    exceeds 383 (the longest passage holds 358 words and 334 terms), and no lexeme
    occurs more than 27 times in one passage.

## References

- PostgreSQL documentation, [Controlling Text Search](https://www.postgresql.org/docs/current/textsearch-controls.html).
- PostgreSQL 18 documentation, [Full Text Search: Limitations](https://www.postgresql.org/docs/18/textsearch-limitations.html).
- Apache Lucene, [Remove k1+1 from the numerator of BM25Similarity (LUCENE-8563)](https://issues.apache.org/jira/browse/LUCENE-8563), fixed in Lucene 8.0, 2018.
- [pg_textsearch](https://github.com/timescale/pg_textsearch), [ParadeDB](https://github.com/paradedb/paradedb), [VectorChord-bm25](https://github.com/supervc-stack/VectorChord-bm25) and [bm25s](https://github.com/xhluca/bm25s) on GitHub.
- Neon documentation, [The pg_search extension](https://neon.com/docs/extensions/pg_search).
- Stephen Robertson and Hugo Zaragoza, [The Probabilistic Relevance Framework: BM25 and Beyond](https://doi.org/10.1561/1500000019) (Foundations and Trends in Information Retrieval, 2009).
- Chris Kamphuis, Arjen P. de Vries, Leonid Boytsov and Jimmy Lin, [Which BM25 Do You Mean? A Large-Scale Reproducibility Study of Scoring Variants](https://doi.org/10.1007/978-3-030-45442-5_4) (ECIR, 2020).
- Timothy G. Armstrong, Alistair Moffat, William Webber and Justin Zobel, [Improvements That Don't Add Up: Ad-Hoc Retrieval Results Since 1998](https://doi.org/10.1145/1645953.1646031) (CIKM, 2009).
- Wei Yang, Kuang Lu, Peilin Yang and Jimmy Lin, [Critically Examining the "Neural Hype": Weak Baselines and the Additivity of Effectiveness Gains from Neural Ranking Models](https://doi.org/10.1145/3331184.3331340) (SIGIR, 2019).
