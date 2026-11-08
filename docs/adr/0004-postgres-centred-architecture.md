<!-- Author: Nicola Antonello -->

# ADR-0004: A Postgres-centred architecture

- Status: accepted
- Date: 2026-11-05

## Context

The system stores passages, keyword statistics and embeddings, and searches them. The
budget for model calls and hosting is under $25 in total, every published number must be
reproducible from what is committed, and the local machine has an 8 GB graphics card and
32 GB of RAM. The architecture decides where storage and search live, what a stranger
needs to reproduce a run, and what the project shows about building systems.

## Options

| Option | Why not |
|---|---|
| **Postgres-centred: Postgres with pgvector holds passages, keyword statistics and embeddings, and runs search as SQL; Python computes** | Chosen by the owner. It shows production storage and search in one database, runs locally in Docker, and works on managed hosts that offer pgvector. It costs setup time, a database to host for the demo, and Docker for anyone reproducing a run. |
| Local-first: keyword and vector search in Python, with local models | The initial recommendation: free apart from generation, and one command to reproduce. It leaves little infrastructure to show until the demo. |
| Hosted services: a hosted embedding API and vector database | Per-call fees would eat the budget, reproducing a run would need accounts and API keys, and wiring services together teaches less. |

## Decision

- **Files are the source of truth.** Git holds the corpus manifest, the gold questions
  and the run records, and the corpus files are downloaded from the manifest and checked
  against its checksums. Nobody can review a database snapshot in a pull request.
- **Postgres is an index you can rebuild.** It holds only what is derived from those
  files: passages, keyword statistics and embeddings. It is labelled with the corpus
  version and rebuilt from scratch for each one, so there are no migrations.
- **Postgres searches; Python computes.** Postgres 18 with pgvector runs in Docker from
  the pgvector project's image, pinned by digest, and runs keyword and vector search as
  SQL. Python parses, embeds, reranks, calls the models, checks quotes and scores.
- **Boundaries.** Every retrieval method takes a question and returns ranked passage IDs
  with scores. Every model call goes through one client that saves the request and the
  response in the run record, so tests replay them and rescoring costs nothing. The
  generator gets no tools, and the system prompt lives in code.

## Consequences

- Reproducing a run needs Docker as well as Python.
- The demo needs hosted Postgres with pgvector. Neon and Supabase both listed pgvector
  on 2026-11-05; their free-tier storage limits are unchecked.
- Postgres 18.6 was the newest release on 2026-11-05, with 19 in beta. The pgvector image
  also has a build for Apple chips (checked on 2026-11-06), so the owner's Mac can run it.
- How keyword search works inside Postgres is decided in ADR-0005.

## References

- PostgreSQL, [Versioning Policy](https://www.postgresql.org/support/versioning/).
- [pgvector](https://github.com/pgvector/pgvector) on GitHub.
- Neon documentation, [Supported Postgres extensions](https://neon.com/docs/extensions/pg-extensions).
- Supabase documentation, [Postgres Extensions Overview](https://supabase.com/docs/guides/database/extensions).
