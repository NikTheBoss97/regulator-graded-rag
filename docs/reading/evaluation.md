<!-- Author: Nicola Antonello -->

# Evaluation

Gold questions, metrics and significance tests, keeping the held-out split honest, and
tracing failures to a stage. Part of the [reading list](README.md).

## Test collections and gold questions

- ★ Mark Sanderson, [Test Collection Based Evaluation of Information Retrieval Systems](https://doi.org/10.1561/1500000009) (Foundations and Trends in Information Retrieval, 2010). The method this project's evaluation rests on: its measures, significance testing and the limits of the approach.
- Pranab Islam et al., [FinanceBench: A New Benchmark for Financial Question Answering](https://arxiv.org/abs/2311.11944) (arXiv, 2023). A domain benchmark with answers and evidence strings, and a model for this project's gold format.
- Jonathan H. Clark et al., [TyDi QA: A Benchmark for Information-Seeking Question Answering in Typologically Diverse Languages](https://doi.org/10.1162/tacl_a_00317) (TACL, 2020). Questions written by people who want the answer and don't know it yet, to avoid priming. The theory behind starting from real requesters' questions.
- Tom Kwiatkowski et al., [Natural Questions: A Benchmark for Question Answering Research](https://doi.org/10.1162/tacl_a_00276) (TACL, 2019). Real search queries annotated against Wikipedia, with an analysis of how much human annotators vary: a reminder that gold labels are not perfect.
- Pranav Rajpurkar, Robin Jia and Percy Liang, [Know What You Don't Know: Unanswerable Questions for SQuAD](https://doi.org/10.18653/v1/P18-2124) (ACL, 2018). Unanswerable questions written to look like answerable ones, which is why this project's must be plausible.

## Metrics and significance tests

- ★ Julián Urbano, Harlley Lima and Alan Hanjalic, [Statistical Significance Testing in Information Retrieval: An Empirical Analysis of Type I, Type II and Type III Errors](https://doi.org/10.1145/3331184.3331259) (SIGIR, 2019). Over 500 million simulated p-values: the t-test and the permutation test hold their error rates, while the sign and Wilcoxon tests are unreliable for mean effectiveness. A free copy is on [arXiv](https://arxiv.org/abs/1905.11096).
- Tetsuya Sakai, [Laboratory Experiments in Information Retrieval: Sample Sizes, Effect Sizes, and Statistical Power](https://doi.org/10.1007/978-981-13-1199-4) (Springer, 2018). How to plan and report an IR experiment statistically, including how many questions it needs.
- Tetsuya Sakai, [Topic Set Size Design](https://doi.org/10.1007/s10791-015-9273-z) (Information Retrieval Journal, 2015). Working out the number of test questions from statistical requirements, and why different measures need different numbers.
- Benjamin A. Carterette, [Multiple Testing in Statistical Analysis of Systems-Based Information Retrieval Experiments](https://doi.org/10.1145/2094072.2094076) (ACM Transactions on Information Systems, 2012). Modelling the many hypotheses tested on one data set can raise p-values by orders of magnitude. Why the number of configurations tried is recorded.
- Mark D. Smucker, James Allan and Ben Carterette, [A Comparison of Statistical Significance Tests for Information Retrieval Evaluation](https://doi.org/10.1145/1321440.1321528) (CIKM, 2007). The t-test, bootstrap and randomization tests largely agree, and the authors recommend dropping the Wilcoxon and sign tests.
- Kalervo Järvelin and Jaana Kekäläinen, [Cumulated Gain-Based Evaluation of IR Techniques](https://doi.org/10.1145/582415.582418) (ACM Transactions on Information Systems, 2002). The origin of nDCG: graded relevance, discounted by rank.

## The held-out split and contamination

- ★ Cynthia Dwork, Vitaly Feldman, Moritz Hardt, Toniann Pitassi, Omer Reingold and Aaron Roth, [The Reusable Holdout: Preserving Validity in Adaptive Data Analysis](https://doi.org/10.1126/science.aaa9375) (Science, 2015). Why choosing analyses after seeing results breaks the usual guarantees: the theory behind running the held-out split once.
- Sayash Kapoor and Arvind Narayanan, [Leakage and the Reproducibility Crisis in Machine-Learning-Based Science](https://doi.org/10.1016/j.patter.2023.100804) (Patterns, 2023). Leakage found in 17 fields and 294 papers, with a taxonomy of eight types: a checklist for the gold set and the harness.
- Manley Roberts, Himanshu Thakur, Christine Herlihy, Colin White and Samuel Dooley, [Data Contamination Through the Lens of Time](https://arxiv.org/abs/2310.10628) (arXiv, 2023). Models' training cutoffs as a natural experiment for contamination. Why letters dated after a model's cutoff are reported separately.
- Moritz Hardt and Benjamin Recht, [Patterns, Predictions, and Actions](https://mlstory.org/) (Princeton University Press, 2022). Free online. Chapter 8, "Datasets", explains why reusing a test set undermines the holdout's guarantee, and why replication studies find the damage milder than the worst case.
- Patrick Lewis, Pontus Stenetorp and Sebastian Riedel, [Question and Answer Test-Train Overlap in Open-Domain Question Answering Datasets](https://doi.org/10.18653/v1/2021.eacl-main.86) (EACL, 2021). In three popular benchmarks, 30% of test questions have a near-duplicate in the training set. Why near-duplicate letters go to the same split.
- Joelle Pineau et al., [Improving Reproducibility in Machine Learning Research (A Report from the NeurIPS 2019 Reproducibility Program)](https://jmlr.org/papers/v22/20-303.html) (JMLR, 2021). What a code policy, a reproducibility challenge and a checklist taught a large ML conference: the basis for the run records.
- Brian A. Nosek, Charles R. Ebersole, Alexander C. DeHaven and David T. Mellor, [The Preregistration Revolution](https://doi.org/10.1073/pnas.1708274114) (PNAS, 2018). Fixing the plan before seeing outcomes separates prediction from postdiction. Why each hypothesis comes first and the held-out checksum is committed before tuning.

## Tracing failures and judging answers

- ★ Scott Barnett et al., [Seven Failure Points When Engineering a Retrieval Augmented Generation System](https://doi.org/10.1145/3644815.3644945) (CAIN, 2024). Seven ways a RAG system fails, from three case studies, and the argument that such a system can only be fully validated in operation.
- Shreya Shankar et al., [Who Validates the Validators? Aligning LLM-Assisted Evaluation of LLM Outputs with Human Preferences](https://doi.org/10.1145/3654777.3676450) (UIST, 2024). Model-generated evaluators inherit the problems of the models they judge, so they need human validation.
