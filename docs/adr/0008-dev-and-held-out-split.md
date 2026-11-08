<!-- Author: Nicola Antonello -->

# ADR-0008: Dev and held-out, split by letter in code

- Status: accepted
- Date: 2026-11-06

## Context

The gold set needs a dev split for tuning and a held-out split for one final estimate. An
earlier rule had the owner write the held-out questions, but ADR-0007 makes the questions
the regulator's, so the split has to be drawn from the letters. Two leaks threaten an
honest estimate: near-duplicate questions on both sides, and anyone shaping the split, or
the system, after reading held-out letters. The letters are also public, so a model may
have seen them in training.

## Options

| Option | Why not |
|---|---|
| **Random by letter, grouped, drawn by code before anyone reads the letters** | Chosen. Dev and held-out come from the same pool, so the held-out score is an honest estimate for the kind of question dev was tuned on. Code fixes the split before anyone looks, so it can be audited, and grouping near-duplicates closes a known leak: Lewis et al. found that 30% of test questions in three popular question-answering benchmarks had a near-paraphrase in the training data. |
| By date, holding out the newest letters (2024 on, plus letters after the edition) | Closer to real use, and recent letters lose fewer questions to drift. But only about 70 questions, a ±12-point margin of error, and dev and held-out would come from different years, so a gap between their scores could reflect the years rather than over-tuning. These letters are probably still older than the models' training cutoffs, so it does not avoid contamination either. |
| The owner writes the held-out questions | New questions the model cannot have seen, but the owner would have to answer them correctly without being a specialist, questions written after reading a section tend to echo its wording (Clark et al.; Kwiatkowski et al.), and they would differ in kind from dev, so the held-out score would not measure what was tuned. |

## Decision

1. **The split comes first.** A script lists every letter from 2017 on and groups those
   that belong together: letters whose text is nearly identical, and letters that cite
   each other's reference numbers.
2. **A committed seed decides.** Separately for each year, the seed sends 40% of the
   groups to held-out and 60% to dev. The script prints counts only, and anyone can rerun
   it and get the same split. Git holds the assignment as letter numbers only.
3. **Letters already read go to dev.** The three letters opened while the domain was
   chosen, 20-0003, 20-0018 and 20-0034, are assigned to dev.
4. **The extractor is built on dev.** The question extractor is built and tested on dev
   letters only.
5. **The owner builds and checks held-out.** The owner runs the command that extracts the
   held-out questions into a git-ignored folder, then checks them alone with a small
   review tool, including each letter's date, on which the drift rule depends.
6. **Unanswerable questions.** The owner writes them in one private file, which the same
   seed splits 60/40. An unanswerable letter question follows its letter.
7. **Freeze before tuning.** Before any tuning starts, the held-out file's checksum is
   committed and a backup is made outside the repository. The file stays out of git until
   it is published with the final report, and changing it voids earlier held-out results.

Only the owner reads held-out questions or runs held-out commands. ADR-0014 fixes when
the held-out run happens.

## Consequences

- **Sizes, estimated.** About 200 letter questions and about 50 unanswerable ones make
  roughly 250: about 150 dev and 100 held-out. Retrieval and the supported verdict are
  scored on the answerable questions only, about 120 in dev and 80 held-out.
- **Held-out precision.** Accuracy over about 80 answerable questions has a 95% margin of
  error of about ±11 points. Held-out's only job is one final estimate.
- **Dev power.** On about 120 paired questions, a 10-point difference between two setups
  is detected roughly 60% of the time, assuming one question in five changes outcome
  between them. The estimate first presented, about 80%, counted all 150 dev questions,
  including the unanswerable ones that these measures skip. Phase 2 measures that share
  on dev and redoes the calculation with Sakai's method.
- **The owner's time.** Checking about 250 questions at one to two minutes each takes
  roughly 4-8 hours, about 100 of them alone, and writing the unanswerable questions 1-2
  hours more.
- **Contamination is measured, not avoided.** Most letters are older than any current
  model's training cutoff, so results are also reported for letters dated after the
  model's cutoff, next to the closed-book run (Roberts et al.).
- **Unverified.** How many letters are near-duplicates, the full number of usable
  questions, and the one-in-five assumption behind the power estimate.

## References

- Patrick Lewis, Pontus Stenetorp and Sebastian Riedel, [Question and Answer Test-Train Overlap in Open-Domain Question Answering Datasets](https://doi.org/10.18653/v1/2021.eacl-main.86) (EACL, 2021).
- Sayash Kapoor and Arvind Narayanan, [Leakage and the Reproducibility Crisis in Machine-Learning-Based Science](https://doi.org/10.1016/j.patter.2023.100804) (Patterns, 2023).
- Tetsuya Sakai, [Topic Set Size Design](https://doi.org/10.1007/s10791-015-9273-z) (Information Retrieval Journal, 2015).
- Tetsuya Sakai, [Laboratory Experiments in Information Retrieval: Sample Sizes, Effect Sizes, and Statistical Power](https://doi.org/10.1007/978-981-13-1199-4) (Springer, 2018).
- Manley Roberts, Himanshu Thakur, Christine Herlihy, Colin White and Samuel Dooley, [Data Contamination Through the Lens of Time](https://arxiv.org/abs/2310.10628) (arXiv, 2023).
- Jonathan H. Clark et al., [TyDi QA: A Benchmark for Information-Seeking Question Answering in Typologically Diverse Languages](https://doi.org/10.1162/tacl_a_00317) (TACL, 2020).
- Tom Kwiatkowski et al., [Natural Questions: A Benchmark for Question Answering Research](https://doi.org/10.1162/tacl_a_00276) (TACL, 2019).
- Brian A. Nosek, Charles R. Ebersole, Alexander C. DeHaven and David T. Mellor, [The Preregistration Revolution](https://doi.org/10.1073/pnas.1708274114) (PNAS, 2018).
