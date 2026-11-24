# Author: Nicola Antonello
"""The sample size as a sensitivity table (ADR-0020).

Usage: python -m regulator_graded_rag.power eval/runs/<name>, from the repository root.

From a dev run's per-question recall@10, with s its sample standard deviation and n its
answerable questions, the table gives the minimum detectable difference (MDD): the
smallest true mean difference between two setups that a two-sided paired t-test on these
n questions detects at alpha 0.05 with power 0.8,
MDD = (z_0.975 + z_0.80) * sd / sqrt(n - z_0.975**2 / 2), Sakai's paired design with the
normal-quantile correction for the t test. The spread sd of the paired differences is
unknown until a second setup runs, so it is assumed: sqrt(2 * s**2 * (1 - rho)) for a
correlation rho between the two setups' scores, and sqrt(d) for a yes-or-no score whose
outcome changes on a share d of the questions. The answerable count is also checked
against the 120 the design expected (ADR-0008).
Exit code 0 when the table is printed, 1 when the run is missing or not a dev run.
"""

import argparse
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist, stdev

Z_975 = NormalDist().inv_cdf(0.975)
Z_80 = NormalDist().inv_cdf(0.80)
EXPECTED = 120  # answerable dev questions the design expected (ADR-0008)


@dataclass(frozen=True)
class Row:
    assumption: str
    sd: float
    mdd: float


def mdd(sd: float, n: int) -> float:
    """The smallest true mean difference a two-sided paired t-test on n questions detects
    at alpha 0.05 with power 0.8, when the paired differences spread by sd."""
    return (Z_975 + Z_80) * sd / math.sqrt(n - Z_975**2 / 2)


def table(
    scores: Sequence[float],
    rhos: Sequence[float] = (0.0, 0.3, 0.5, 0.7),
    discordant: Sequence[float] = (0.1, 0.2, 0.3),
) -> list[Row]:
    """A row per assumed correlation, then per assumed discordant share, each with the
    paired differences' spread and the MDD on len(scores) questions."""
    s = stdev(scores)
    spreads = [(f"rho={rho}", math.sqrt(2 * s**2 * (1 - rho))) for rho in rhos]
    spreads += [(f"discordant={d}", math.sqrt(d)) for d in discordant]
    return [Row(label, sd, mdd(sd, len(scores))) for label, sd in spreads]


def _shortfall(n: int) -> str:
    if n < EXPECTED:
        return (
            f"answerable dev questions: {n}, {EXPECTED - n} short of the {EXPECTED}"
            " the design expected"
        )
    return f"answerable dev questions: {n}, no shortfall against the {EXPECTED}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.power",
        description="Print the sample-size table from a dev run's recall@10.",
    )
    parser.add_argument("run", type=Path, help="the run's folder, eval/runs/<name>")
    folder: Path = parser.parse_args(argv).run
    try:
        run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        if run.get("split") != "dev":
            print(f"{folder.as_posix()} is not a dev run: the table is made on dev")
            return 1
        scores = json.loads((folder / "scores.json").read_text(encoding="utf-8"))
    except FileNotFoundError as err:
        print(f"{Path(err.filename).as_posix()} is missing")
        return 1
    recall = [question["recall"]["10"] for question in scores["per_question"]]
    print(
        f"{folder.name}: recall@10 of {len(recall)} answerable questions,"
        f" s = {stdev(recall):.3f}; MDD at alpha 0.05, power 0.8"
    )
    print(f"{'assumption':<16}{'sd':>8}{'MDD':>8}")
    for row in table(recall):
        print(f"{row.assumption:<16}{row.sd:>8.3f}{row.mdd:>8.3f}")
    print(_shortfall(len(recall)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
