<!-- Author: Nicola Antonello -->

# Engineering practice

Recording decisions, experiment configs, tests, CI, dependencies and personal data in the history. Part of the [reading list](README.md).

## Recording decisions

- ★ Michael Nygard, [Documenting Architecture Decisions](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions) (Cognitect, 2011). The original ADR format: a title, context, decision, status and consequences, with a reversed decision kept and marked superseded.
- Georg Buchgeher et al., [Using Architecture Decision Records in Open Source Projects—An MSR Study on GitHub](https://doi.org/10.1109/ACCESS.2023.3287654) (IEEE Access, 2023). ADR adoption on GitHub is low but rising, about half of the repositories with ADRs hold only one to five, and most follow Nygard's template.

## Experiment configs

- Jimmy Lin, Xueguang Ma, Sheng-Chieh Lin, Jheng-Hong Yang, Ronak Pradeep and Rodrigo Nogueira, [Pyserini: An Easy-to-Use Python Toolkit to Support Replicable IR Research with Sparse and Dense Representations](https://arxiv.org/abs/2102.10073) (arXiv, 2021). Sparse, dense and hybrid retrieval baselines, kept replicable by shared norms and automated testing. The model for the test that checks the BM25 config reproduces the committed baseline.
- D. Sculley, Gary Holt, Daniel Golovin, Eugene Davydov, Todd Phillips, Dietmar Ebner, Vinay Chaudhary, Michael Young, Jean-François Crespo and Dan Dennison, [Hidden Technical Debt in Machine Learning Systems](https://proceedings.neurips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html) (NIPS, 2015). The ML-specific risk factors behind ongoing maintenance costs, configuration issues among them. The older classic on configuration as technical debt, listed next to Lin et al.

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

## Personal data in the history

- GitHub, [Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) (GitHub Docs). Why a rewrite and a force-push are not enough: pull request refs and cached views keep the old commits until GitHub Support removes them.
- GitHub, [Blocking command line pushes that expose your personal email address](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/blocking-command-line-pushes-that-expose-your-personal-email-address) (GitHub Docs). The account setting that rejects a push whose newest commit names a private email.
