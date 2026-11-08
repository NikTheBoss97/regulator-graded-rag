<!-- Author: Nicola Antonello -->

# Engineering practice

Recording decisions, tests, CI and dependencies. Part of the [reading list](README.md).

## Recording decisions

- ★ Michael Nygard, [Documenting Architecture Decisions](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions) (Cognitect, 2011). The original ADR format: a title, context, decision, status and consequences, with a reversed decision kept and marked superseded.
- Georg Buchgeher et al., [Using Architecture Decision Records in Open Source Projects—An MSR Study on GitHub](https://doi.org/10.1109/ACCESS.2023.3287654) (IEEE Access, 2023). ADR adoption on GitHub is low but rising, about half of the repositories with ADRs hold only one to five, and most follow Nygard's template.

## Tests, CI and dependencies

- GitHub, [About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets) (GitHub Docs). What rulesets are and how they protect branches.
- GitHub, [Dependabot options reference](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference) (GitHub Docs). Every Dependabot setting, including the cooldown that holds back newly released versions.
- Git, [git-interpret-trailers](https://git-scm.com/docs/git-interpret-trailers) (Git documentation). How the trailers at the end of a commit message are added and parsed, which the trailer check relies on.
- uv, [Using uv with PyTorch](https://docs.astral.sh/uv/guides/integration/pytorch/) (uv documentation). How to pin PyTorch builds for a given CUDA version in a uv project.
- uv, [Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/) (uv documentation). How uv resolves dependencies into `uv.lock`, which records a hash for every file, and keeps the environment in step with it.
- mypy, [documentation](https://mypy.readthedocs.io/en/stable/) (mypy documentation). The type checker the gates run, and its strict mode.
- Ruff, [Rules](https://docs.astral.sh/ruff/rules/) (Ruff documentation). Every lint rule, which ones are on by default, and the security rules among them.
- zizmor, [Usage](https://docs.zizmor.sh/usage/) (zizmor documentation). How it audits GitHub Actions workflows, offline or online, and what each mode leaves out.
- [gitleaks](https://github.com/gitleaks/gitleaks) (GitHub). Scans a git repository for secrets.
- [actionlint](https://github.com/rhysd/actionlint) (GitHub). A static checker for GitHub Actions workflow files.
- Davide Spadini, Maurício Aniche, Magiel Bruntink and Alberto Bacchelli, [To Mock or Not To Mock? An Empirical Study on Mocking Practices](https://doi.org/10.1109/MSR.2017.61) (MSR, 2017). An empirical study of which dependencies developers mock in their tests, and why.
