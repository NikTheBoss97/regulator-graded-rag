<!-- Author: Nicola Antonello -->

# ADR-0014: When the held-out split runs

- Status: accepted
- Date: 2026-11-08

## Context

ADR-0008 freezes the held-out split before tuning and lets only the owner run it. The
draft plan put a single held-out run in the last phase, yet called phases 1 to 4 a
complete project on their own, which they would not be without a held-out number. A
held-out number also needs a committed run record, and that record holds the model's
answers to the held-out questions, which reveal them.

## Options

| Option | Why not |
|---|---|
| **Once, when the answers stop changing; at the end of phase 4 the owner decides, with dev results in hand, whether that is then or after phase 5** | Chosen. One look, a held-out number however the project ends, and the choice is made with evidence. |
| Once, fixed in phase 7 | Also one look, but if the project stopped after phase 4 it would have no held-out number. |
| Twice: after phase 4 and at the end | The earliest held-out number. But the first run's record has to be committed to back that number, which exposes the held-out questions and answers to all later tuning, so the second run would no longer measure unseen questions. |

## Decision

The held-out split runs once, when nothing that can change an answer is still changing.
At the end of phase 4, the owner decides whether that is then or after phase 5. Anything
that can change an answer, including phase 6's guardrails, is a dev experiment that lands
before the held-out run. The owner starts the run, the number of held-out runs is printed
next to its results, and the held-out file is published with its run record in the final
report.

## Consequences

- Until the held-out run, every published number is a dev number and says so.
- If phase 5 comes after the held-out run, its gains are reported on dev only and
  labelled as such.
- Deciding at the end of phase 4 uses the dev results and the time left, which are
  unknown today.
- Dwork et al. show that choosing analyses after seeing results breaks a holdout's
  guarantees. Hardt and Recht note that replication studies find the damage milder than
  the worst case, but a single look needs no such argument.

## References

- Cynthia Dwork, Vitaly Feldman, Moritz Hardt, Toniann Pitassi, Omer Reingold and Aaron Roth, [The Reusable Holdout: Preserving Validity in Adaptive Data Analysis](https://doi.org/10.1126/science.aaa9375) (Science, 2015).
- Moritz Hardt and Benjamin Recht, [Patterns, Predictions, and Actions](https://mlstory.org/) (Princeton University Press, 2022), chapter 8, "Datasets".
- Brian A. Nosek, Charles R. Ebersole, Alexander C. DeHaven and David T. Mellor, [The Preregistration Revolution](https://doi.org/10.1073/pnas.1708274114) (PNAS, 2018).
