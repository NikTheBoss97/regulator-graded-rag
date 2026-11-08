<!-- Author: Nicola Antonello -->

# ADR-0013: The repository, CI and security

- Status: accepted
- Date: 2026-11-08

## Context

The repository is public and read by strangers, so its name has to say what the project
is at a glance, and its history and checks have to be trustworthy without anyone taking
the owner's word for them. CI has to prove the gates without model API keys or paid
calls. The project also handles material with its own risks: model weights from the
internet, an API key, and letters that name real people.

## Options

For the repository's name, with the repository's topics, such as "hazmat", carrying the
keywords:

| Option | Why not |
|---|---|
| **`regulator-graded-rag`** | Chosen. It says what makes the project different: it is graded against the regulator's own answers. |
| `hazmat-rag-eval` | Plainer and easier to search for, and it names the domain and the method, but not what sets the evaluation apart. |
| `cited-hazmat-answers` | It says what a user gets, but not that this is an evaluation project. |

## Decision

**Repository.** `regulator-graded-rag`, public, under Apache-2.0, which includes an
explicit patent grant. Once the repository exists, a ruleset protects `main`: changes
land only through pull requests, required checks must pass, history stays linear, merges
are rebase-only and merged branches are deleted. The first commit is the one change that
goes straight to `main`, before the ruleset exists.

**Code.** One Python package with one command per step: fetch, build passages, index,
split the letters, extract questions, run, score and report. Each long step shows a
counter, the elapsed time and what is left, and resumes after an interruption.

**Tests.**

- Unit tests need no database or network. Integration tests run against a real Postgres
  in Docker rather than mocks.
- They cover the passage builder, BM25 in SQL against bm25s, the quote check, the decline
  rule, JSON parsing, the metrics, the statistical test, the split, and prompt injection
  with planted passages.
- Every new test is seen failing first. Deliberate breakages prove each check, and every
  check that finds nothing has a control that finds something.

**CI.** GitHub Actions run on every pull request and every push to `main`, with no path
filters, so a docs-only change cannot skip a check.

- A checks job runs gitleaks, actionlint, zizmor, ruff and the type checker, plus a check
  that rejects commit-message trailers outside a short allowlist, so no tool can add its
  own lines to the history.
- A tests job runs with the pgvector image pinned by digest.
- No models run in CI: it holds no keys, calls no paid API and downloads no models, and it
  replays recorded outputs instead.
- Every action is pinned to a full commit SHA, the workflow token is read-only, and
  dependency updates arrive weekly after a 7-day cooldown that security updates skip.

**Security.**

- The Anthropic API key lives only in a git-ignored file on the Windows laptop.
- Model weights load only from safetensors or GGUF files that match their pinned
  checksum: never pickle-based files, which can run code when loaded, and never models
  that need code from their own repository.
- Local model servers listen only on localhost.
- The corpus is pinned by checksums (ADR-0006), so a changed or planted file fails the
  fetch.
- Raw letters are never committed. Questions are cleaned, and the owner checks each one.
- uv's lock file pins every dependency by hash.

## Consequences

- A reviewer can trust a green check on any commit, because the checks never skip.
- CI proves the code, not model quality: model outputs come from recordings, and quality
  is measured in run records made on the owner's machine.
- Integration tests need Docker, locally and in CI.
- Excluding pickle files and repository code rules out any model distributed only in
  those forms.
- Unverified: whether the name is free on GitHub, which is checked when the repository is
  created. The type checker and the trailer allowlist are chosen in phase 1.

## Amendments

- 2026-11-08: ADR-0015 chose mypy as the type checker, decided how the gate tools are
  installed, and allowed only the `Refs:` trailer.

## References

- Apache Software Foundation, [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).
- GitHub documentation, [About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets).
- GitHub documentation, [Dependabot options reference](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference).
- Git documentation, [git-interpret-trailers](https://git-scm.com/docs/git-interpret-trailers).
- Hugging Face documentation, [Pickle Scanning](https://huggingface.co/docs/hub/security-pickle) and [Safetensors](https://huggingface.co/docs/safetensors/index).
- Davide Spadini, Maurício Aniche, Magiel Bruntink and Alberto Bacchelli, [To Mock or Not To Mock? An Empirical Study on Mocking Practices](https://doi.org/10.1109/MSR.2017.61) (MSR, 2017).
- Wei Zou, Runpeng Geng, Binghui Wang and Jinyuan Jia, [PoisonedRAG: Knowledge Corruption Attacks to Retrieval-Augmented Generation of Large Language Models](https://www.usenix.org/conference/usenixsecurity25/presentation/zou-poisonedrag) (USENIX Security, 2025).
