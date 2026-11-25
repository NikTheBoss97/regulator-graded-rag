# Author: Nicola Antonello
"""Retrieval runs over a gold split, kept as run records (ADR-0012, ADR-0014).

Usage: python -m regulator_graded_rag.run --split {dev,heldout} [--config PATH]
[--gold PATH] [--k1 F] [--b F] [--resume NAME] [--runs DIR] [--heldout-by-owner], from
the repository root, with DATABASE_URL set as in .env.example.

--config runs an experiment config through the pipeline, which caches stage outputs in
.cache/pipeline/<split>, and the run is named after the config. Without it the command
runs BM25 with k1 and b, which a config sets itself. A config's name stays bound to the
contents of its first run, so a config changed since a run under its name is refused
(ADR-0023).

A run is one folder, eval/runs/<YYYY-MM-DD>-<retriever>-<split>-<n>/:
- run.json, the run file: the commit, its tree and whether tracked files had uncommitted
  changes, the corpus version, the gold set's path, version and counts, the split, the
  retriever and its settings, the config's path, SHA-256 and text when there is one,
  the machine, the cost and the running total, and for a held-out run how many held-out
  runs there have been;
- questions.jsonl, one line per question, written as it finishes: its ID and type, its
  top 50 passage IDs with their scores, and its time, never its text. A config run's
  time is what its stages took to compute the answer, even when the cache gave it;
- scores.json, recomputed from the stored hits, naming the gold set's version.
Every item is searched, unanswerable ones included, and only answerable items are
scored. A run stopped midway, by closing the laptop, resumes with the settings it started
with. Held-out runs are started by the owner only, and read only the frozen items, whose
SHA-256 eval/heldout-items.sha256 records (ADR-0014).
Exit code 0 when the run is complete and scored, 1 when it cannot run, and 2 for a
held-out run without the owner's flag.
"""

import argparse
import json
import os
import platform
import statistics
import subprocess
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from regulator_graded_rag.bm25 import BM25, K1, B, Retriever, StaleIndex
from regulator_graded_rag.cache import CACHE_ROOT, StageCache
from regulator_graded_rag.configs import Config, ConfigError, DenseStage, load_config
from regulator_graded_rag.db import connect, database_url
from regulator_graded_rag.embeddings import model_key
from regulator_graded_rag.gold import Item, gold_version, load_items
from regulator_graded_rag.manifest import DEFAULT_MANIFEST, load_manifest
from regulator_graded_rag.metrics import (
    CUTOFFS,
    DEPTH,
    Summary,
    score_question,
    summarize,
)
from regulator_graded_rag.models import SentenceTransformerEncoder, WeightsMismatch
from regulator_graded_rag.pipeline import build

RUNS = Path("eval/runs")
GOLD = {
    "dev": Path("eval/dev/items.jsonl"),
    "heldout": Path("eval/heldout/items.jsonl"),
}
FROZEN = Path("eval/heldout-items.sha256")

# A stopped run resumes only when these are what it started with.
_SAME = (
    "corpus_version",
    "gold.version",
    "split",
    "retriever",
    "settings",
    # The code and the machine too: every question then ran under the commit the
    # record names, and the run's times are comparable.
    "git.commit",
    "git.dirty",
    "machine",
)


@runtime_checkable
class Timed(Protocol):
    """A retriever whose answers may come from a cache, in microseconds, reports the
    seconds its stages took to compute the last one, and the run records those."""

    def compute_seconds(self) -> float: ...


def cache_root(split: str) -> Path:
    """Each split's own stage cache, so held-out hit lists stay apart from dev's, under
    a heldout/ path."""
    return CACHE_ROOT / split


class RunExists(Exception):
    """The run is complete, so it never runs again: a new run gets a new name."""


class ResumeMismatch(Exception):
    """A stopped run resumes only with what it started with."""


def freeze(items: Path, frozen: Path, count: int) -> None:
    """Record the items file's SHA-256 and its count of items: the held-out freeze."""
    frozen.parent.mkdir(parents=True, exist_ok=True)
    frozen.write_text(
        f"{gold_version(items)}  {items.as_posix()}\nitems: {count}\n",
        encoding="utf-8",
        newline="\n",
    )


def frozen_matches(items: Path, frozen: Path) -> bool:
    """Whether the items file is the frozen one: its SHA-256 opens the frozen file.
    When nothing is frozen, nothing matches."""
    try:
        words = frozen.read_text(encoding="utf-8").split()
    except FileNotFoundError:
        return False
    return bool(words) and words[0] == gold_version(items)


def git_state(repo: Path) -> tuple[str, str, bool]:
    """The commit checked out, its tree, and whether tracked files have uncommitted
    changes. A rebase merge gives the commit a new ID but keeps its tree (ADR-0012)."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, encoding="utf-8", check=True
        ).stdout

    dirty = git("status", "--porcelain", "--untracked-files=no").strip()
    commit, tree = git("rev-parse", "HEAD", "HEAD^{tree}").split()
    return commit, tree, bool(dirty)


def machine() -> dict[str, str]:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor() or platform.machine(),
    }


def run_name(day: date, retriever: str, split: str, existing: Iterable[str]) -> str:
    """The day's next free name for this retriever and split, counting from 1."""
    taken = set(existing)
    n = 1
    while (name := f"{day.isoformat()}-{retriever}-{split}-{n}") in taken:
        n += 1
    return name


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _recorded(path: Path, repo: Path) -> str:
    """A path as a committed record may show it: relative to the repository, or only
    its name when it lies outside, so the user's home folder never reaches git."""
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.name


def run_files(root: Path) -> list[dict[str, Any]]:
    """Every run file under root, whatever its status, in name order."""
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(root.glob("*/run.json"))
    ]


def run_config(path: Path, root: Path, repo: Path) -> Config:
    """The config in the file, with its path as a committed record may show it; refused
    with ConfigError when a run under root ran a config of the same name with other
    contents, since a config that produced a run is never edited (ADR-0023)."""
    config = replace(load_config(path), path=_recorded(path, repo))
    for run_file in sorted(root.glob("*/run.json")):
        run = json.loads(run_file.read_text(encoding="utf-8"))
        ran = _field(run, "config.sha256")
        if run.get("retriever") == config.name and ran not in (None, config.sha256):
            raise ConfigError(
                f"{run_file.parent.as_posix()} ran {config.name} from a config with"
                f" SHA-256 {ran}, and {config.path} now has {config.sha256}: a changed"
                " config needs a new name"
            )
    return config


def header(
    retriever: Retriever,
    items_path: Path,
    items: Sequence[Item],
    split: str,
    corpus_version: str,
    root: Path,
    repo: Path,
    *,
    config: Config | None = None,
) -> dict[str, object]:
    """The run file's fields that are known before the run starts, with the whole config
    when the retriever runs one."""
    commit, tree, dirty = git_state(repo)
    earlier = run_files(root)
    heldout_runs = sum(run.get("split") == "heldout" for run in earlier)
    head: dict[str, object] = {
        "stage": "retrieval",
        "retriever": retriever.name,
        "settings": retriever.settings(),
        "split": split,
        "gold": {
            "path": _recorded(items_path, repo),
            "version": gold_version(items_path),
            "items": len(items),
            "answerable": sum(item.answerable for item in items),
        },
        "corpus_version": corpus_version,
        "git": {"commit": commit, "tree": tree, "dirty": dirty},
        "machine": machine(),
        "started": _now(),
        "cost_usd": 0.0,
        "spent_usd": sum(
            (
                run.get("cost_usd", 0.0)
                for run in earlier
                if run.get("status") == "complete"
            ),
            0.0,
        ),
        "heldout_runs": heldout_runs + 1 if split == "heldout" else 0,
    }
    if config is not None:
        head["config"] = {
            "path": config.path,
            "sha256": config.sha256,
            "text": config.text,
        }
    return head


def _field(run: dict[str, Any], key: str) -> Any:
    """A field by its dotted name, as JSON gives it back, so a tuple equals its list."""
    value: Any = run
    for part in key.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return json.loads(json.dumps(value))


def _write_json(path: Path, data: object) -> None:
    """Sorted, indented JSON with LF, written whole: a run cut off mid-write leaves the
    previous file in place, never half a file."""
    part = path.with_name(path.name + ".part")
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    part.write_text(text, encoding="utf-8", newline="\n")
    os.replace(part, path)


def _saved(path: Path) -> list[dict[str, Any]]:
    """The questions saved so far. A line is whole once its newline is written, so a
    last line without one was cut off mid-write, even when it parses: it is dropped from
    the file, that question runs again, and the next line starts clean."""
    if not path.exists():
        return []
    whole, newline, cut = path.read_bytes().rpartition(b"\n")
    if cut:
        with path.open("r+b") as file:
            file.truncate(len(whole) + len(newline))
    return [json.loads(line) for line in whole.split(b"\n") if line]


def _p95(seconds: Sequence[float]) -> float:
    return statistics.quantiles(seconds, n=20, method="inclusive")[-1]


def run_retrieval(
    retriever: Retriever,
    items: Sequence[Item],
    folder: Path,
    head: dict[str, object],
    *,
    clock: Callable[[], float] = time.perf_counter,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, object]:
    """Search every item not yet saved in the folder, saving each as it finishes, and
    return the complete run file. progress hears each question's number, the number of
    items and its ID before it is searched."""
    run_file = folder / "run.json"
    run: dict[str, Any]
    if run_file.exists():
        run = json.loads(run_file.read_text(encoding="utf-8"))
        if run.get("status") == "complete":
            raise RunExists(
                f"{folder.as_posix()} is complete: a new run gets a new name"
            )
        for key in _SAME:
            started, now = _field(run, key), _field(head, key)
            if started != now:
                raise ResumeMismatch(
                    f"{folder.as_posix()} started with {key} {started!r}, not {now!r}"
                )
    else:
        folder.mkdir(parents=True, exist_ok=True)
        run = {**head, "status": "running"}
    _write_json(run_file, run)
    questions = folder / "questions.jsonl"
    saved = _saved(questions)
    done = {line["id"] for line in saved}
    seconds = [float(line["seconds"]) for line in saved]
    with questions.open("a", encoding="utf-8", newline="\n") as out:
        for number, item in enumerate(items, start=1):
            if item.id in done:
                continue
            if progress is not None:
                progress(number, len(items), item.id)
            start = clock()
            hits = retriever.search(item.question, DEPTH)
            took = clock() - start
            if isinstance(retriever, Timed):
                took = retriever.compute_seconds()
            line = {
                "id": item.id,
                "type": item.type,
                "hits": [[hit.passage_id, hit.score] for hit in hits],
                "seconds": took,
            }
            out.write(json.dumps(line) + "\n")
            out.flush()
            seconds.append(took)
    run |= {
        "status": "complete",
        "finished": _now(),
        "questions": len(seconds),
        "seconds": {
            "total": sum(seconds),
            "median": statistics.median(seconds),
            "p95": _p95(seconds),
        },
    }
    _write_json(run_file, run)
    return run


def score_run(folder: Path, items: Sequence[Item], version: str) -> list[Summary]:
    """Score the answerable items from the run's stored hits, write scores.json with
    the gold set's version, and return the summary rows; refused unless the run ran on
    that version of the gold set and holds exactly these items."""
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    ran_on = _field(run, "gold.version")
    if ran_on != version:
        raise ValueError(
            f"{folder.as_posix()} ran on gold set {ran_on}, not {version}: score it"
            " with the items it ran on"
        )
    text = (folder / "questions.jsonl").read_text(encoding="utf-8")
    saved = [json.loads(line) for line in text.splitlines()]
    ids = sorted(line["id"] for line in saved)
    if ids != sorted(item.id for item in items):
        raise ValueError(
            f"{folder.as_posix()} holds {len(ids)} questions that differ from the"
            f" {len(items)} items: score a complete run of these items"
        )
    ranked = {line["id"]: [passage for passage, _ in line["hits"]] for line in saved}
    scores = [
        score_question(item, ranked[item.id]) for item in items if item.answerable
    ]
    summary = summarize(scores)
    _write_json(
        folder / "scores.json",
        {
            "gold_version": version,
            "per_question": [asdict(score) for score in scores],
            "summary": [asdict(row) for row in summary],
        },
    )
    return summary


def _table(rows: Sequence[Summary]) -> str:
    title = f"{'type':<14}{'n':>5}" + "".join(f"{f'R@{k}':>8}" for k in CUTOFFS)
    lines = [title + f"{'MRR':>8}{'nDCG@10':>9}"]
    for row in rows:
        recall = "".join(f"{row.recall[k]:>8.3f}" for k in CUTOFFS)
        lines.append(
            f"{row.type:<14}{row.n:>5}{recall}{row.mrr:>8.3f}{row.ndcg10:>9.3f}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.run",
        description="Run BM25, or an experiment config, over a gold split into a run"
        " record, then score it.",
    )
    parser.add_argument("--split", required=True, choices=sorted(GOLD))
    parser.add_argument(
        "--config", type=Path, help="run this experiment config (ADR-0023)"
    )
    parser.add_argument(
        "--gold", type=Path, help="the gold items (default: the split's)"
    )
    parser.add_argument("--k1", type=float, help=f"without a config (default {K1})")
    parser.add_argument("--b", type=float, help=f"without a config (default {B})")
    parser.add_argument("--resume", metavar="NAME", help="resume the stopped run NAME")
    parser.add_argument("--runs", type=Path, default=RUNS)
    parser.add_argument(
        "--heldout-by-owner",
        action="store_true",
        help="the owner starts a held-out run (ADR-0014)",
    )
    args = parser.parse_args(argv)
    if args.split == "heldout" and not args.heldout_by_owner:
        print("held-out runs are started by the owner only (ADR-0014)")
        return 2
    given = (("--k1", args.k1), ("--b", args.b))
    flags = [flag for flag, value in given if value is not None]
    if args.config is not None and flags:
        print(
            f"--config sets every setting itself, so {' and '.join(flags)} cannot go"
            " with it"
        )
        return 1
    gold: Path = args.gold or GOLD[args.split]
    try:
        items = load_items(gold)
    except FileNotFoundError:
        print(f"{gold.as_posix()} is missing: write the {args.split} gold items first")
        return 1
    except ValueError as err:
        print(err)
        return 1
    if not items:
        print(f"{gold.as_posix()} holds no items")
        return 1
    # The items' own split, not only the flag, decides which split a run looks at.
    other = next((item for item in items if item.split != args.split), None)
    if other is not None:
        print(
            f"{gold.as_posix()} holds {other.id} of the {other.split} split,"
            f" not {args.split}: a run reads only its own split's items"
        )
        return 1
    if args.split == "heldout" and not frozen_matches(gold, FROZEN):
        print(
            f"{gold.as_posix()} does not match {FROZEN.as_posix()}: a held-out run"
            " reads only the frozen items (ADR-0014)"
        )
        return 1
    runs: Path = args.runs
    if args.resume and not (runs / args.resume / "run.json").exists():
        print(f"there is no run {args.resume} in {runs.as_posix()} to resume")
        return 1
    config = None
    if args.config is not None:
        try:
            config = run_config(args.config, runs, Path("."))
        except (OSError, ValueError) as err:
            print(err)
            return 1
    try:
        manifest = load_manifest(DEFAULT_MANIFEST)
        url = database_url()
    except (RuntimeError, ValueError) as err:
        print(err)
        return 1
    corpus_version = str(manifest.version)
    with connect(url) as conn:
        retriever: Retriever
        try:
            if config is None:
                k1 = K1 if args.k1 is None else args.k1
                b = B if args.b is None else args.b
                retriever = BM25(conn, corpus_version=corpus_version, k1=k1, b=b)
            else:
                cache = StageCache(cache_root(args.split))
                encoders = {
                    model_key(stage.model, stage.revision): SentenceTransformerEncoder(
                        stage
                    )
                    for stage in config.first
                    if isinstance(stage, DenseStage)
                }
                retriever = build(
                    config,
                    conn,
                    corpus_version=corpus_version,
                    cache=cache,
                    encoders=encoders,
                )
        except ImportError:
            print('the models group is not installed: run "uv sync --group models"')
            return 1
        except (StaleIndex, ConfigError, WeightsMismatch) as err:
            print(err)
            return 1
        existing = [path.name for path in runs.iterdir()] if runs.is_dir() else []
        name = args.resume or run_name(
            date.today(), retriever.name, args.split, existing
        )
        folder = runs / name
        head = header(
            retriever,
            gold,
            items,
            args.split,
            corpus_version,
            runs,
            Path("."),
            config=config,
        )
        start = time.monotonic()

        def show(number: int, total: int, item_id: str) -> None:
            elapsed = int(time.monotonic() - start)
            clock = f"{elapsed // 3600:02}:{elapsed // 60 % 60:02}:{elapsed % 60:02}"
            print(f"[{number}/{total} {clock}] {item_id}", flush=True)

        print(f"run {folder.as_posix()}")
        try:
            run_retrieval(retriever, items, folder, head, progress=show)
        except (RunExists, ResumeMismatch) as err:
            print(err)
            return 1
    print(_table(score_run(folder, items, gold_version(gold))))
    return 0
