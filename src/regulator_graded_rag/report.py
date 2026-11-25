# Author: Nicola Antonello
"""The README's results table, written from the committed run records (ADR-0012).

Usage: python -m regulator_graded_rag.report [--check], from the repository root.

The table sits in README.md between two markers. Results are compared only on the same
corpus and gold set, so each split, corpus version and gold-set version gets a block of
its own, with a row per complete, scored run; a held-out block also gives the number of
held-out runs (ADR-0014). Without --check it rewrites the block; with --check it changes
nothing and exits 1 when the README differs from what the records give.
"""

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from regulator_graded_rag.runs import RUNS, run_files

START = "<!-- results:start -->"
END = "<!-- results:end -->"
EMPTY = (
    "No committed run yet: BM25's first dev run comes with the approved dev questions."
)
README = Path("README.md")

_COLUMNS = (
    "| Run | Retriever | Settings | Recall@10 | Recall@5 | Recall@20 | Recall@50 | MRR"
    " | nDCG@10 | Median seconds |"
)
_ALIGN = "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"


def load_runs(root: Path) -> list[dict[str, Any]]:
    """Each complete run under root that has its scores, sorted by name: its run file,
    with its folder's name and its summary rows."""
    runs: list[dict[str, Any]] = []
    for run_file in sorted(root.glob("*/run.json")):
        folder = run_file.parent
        run = json.loads(run_file.read_text(encoding="utf-8"))
        scores = folder / "scores.json"
        if run.get("status") == "complete" and scores.exists():
            summary = json.loads(scores.read_text(encoding="utf-8"))["summary"]
            runs.append(run | {"name": folder.name, "summary": summary})
    return runs


def _row(run: Mapping[str, Any]) -> str:
    """A run's row; a run that scored nothing, having no answerable item, keeps its row
    with dashes, so no run drops out of the table."""
    overall = next((row for row in run["summary"] if row["type"] == "all"), None)
    if overall is None:
        scores = ["—"] * 6
    else:
        recall = overall["recall"]
        numbers = [recall["10"], recall["5"], recall["20"], recall["50"]]
        numbers += [overall["mrr"], overall["ndcg10"]]
        scores = [f"{x:.3f}" for x in numbers]
    if "config" in run:
        # A config run's settings are its file's path and checksums; the committed
        # file holds every setting (ADR-0023).
        path = run["config"]["path"]
        settings = f"[{Path(path).name}]({path})"
    else:
        settings = ", ".join(f"{key}={value}" for key, value in run["settings"].items())
    link = f"[{run['name']}]({RUNS.as_posix()}/{run['name']}/)"
    median = f"{run['seconds']['median']:.3f}"
    return "| " + " | ".join([link, run["retriever"], settings, *scores, median]) + " |"


def table(runs: Sequence[Mapping[str, Any]], heldout_runs: int = 0) -> str:
    """One block per split, corpus version and gold-set version, dev first, each run a
    row; EMPTY when there is no run. A held-out block gives heldout_runs, the number of
    held-out runs ever started."""
    if not runs:
        return EMPTY
    blocks: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for run in runs:
        key = (run["split"], run["corpus_version"], run["gold"]["version"])
        blocks.setdefault(key, []).append(run)
    parts = []
    for (split, corpus, gold), members in sorted(
        blocks.items(), key=lambda block: block[0][0] != "dev"
    ):
        answerable = members[0]["gold"]["answerable"]
        title = (
            f"{'Dev' if split == 'dev' else 'Held-out'}, corpus {corpus[:8]}…,"
            f" gold set {gold[:8]}…, {answerable} answerable questions"
        )
        if split == "heldout":
            title += f", held-out runs: {heldout_runs}"
        rows = [_row(run) for run in members]
        parts.append("\n".join([f"**{title}**", "", _COLUMNS, _ALIGN, *rows]))
    return "\n\n".join(parts)


def results(root: Path) -> str:
    """The README's results block for the runs under root. Every held-out run counts,
    stopped ones included, since each one looked at the held-out split (ADR-0014)."""
    looks = sum(run.get("split") == "heldout" for run in run_files(root))
    return table(load_runs(root), heldout_runs=looks)


def render(readme: str, block: str) -> str:
    """The README with block between the markers, which stay."""
    start, end = readme.find(START), readme.find(END)
    if start < 0 or end < start:
        raise ValueError(f"README.md needs the markers {START} and then {END}")
    return f"{readme[: start + len(START)]}\n{block}\n{readme[end:]}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.report",
        description="Write the README's results table from the committed run records.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="change nothing, and exit 1 when the README differs from the records",
    )
    args = parser.parse_args(argv)
    readme = README.read_text(encoding="utf-8")
    written = render(readme, results(RUNS))
    if written == readme:
        print("README.md's results match the run records")
        return 0
    if args.check:
        print(
            "README.md's results differ from the run records:"
            ' run "uv run python -m regulator_graded_rag.report"'
        )
        return 1
    README.write_text(written, encoding="utf-8", newline="\n")
    print("README.md's results table is rewritten from the run records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
