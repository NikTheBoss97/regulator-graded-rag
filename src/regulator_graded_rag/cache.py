# Author: Nicola Antonello
"""A cache of pipeline stage outputs (ADR-0023).

A stage's outputs for a question (passage IDs and scores) are kept in one JSON-lines
file per stage key, one line per question, keyed by the question's SHA-256. The pipeline
builds each stage key from everything that decides the stage's output, its code
included, so an entry never outlives the code that wrote it. Each entry also keeps the
seconds its stage took, so an answer read from the cache still reports what it cost to
compute. The cache only remembers: deleting it and running again computes every entry
again, with the same passages and scores wherever the stage computes deterministically,
as BM25 does. A line is whole once its newline is written, so a last line cut off
mid-write is dropped and its question computed again.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from regulator_graded_rag.bm25 import Hit

CACHE_ROOT = Path(".cache/pipeline")


@dataclass(frozen=True)
class Entry:
    """A stage's answer to a question: its passages, best first, and the seconds the
    stage took to compute them."""

    hits: list[Hit]
    seconds: float


def source_digest(package: Path) -> str:
    """The SHA-256 over each Python file's path, relative to the package, and bytes."""
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def stage_key(parts: Mapping[str, object]) -> str:
    """The SHA-256 of the parts as canonical JSON: sorted keys and no spaces."""
    text = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _question_key(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


class StageCache:
    """Stage outputs per key and question, in one JSON-lines file per key."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._loaded: dict[str, dict[str, Entry]] = {}

    def _file(self, key: str) -> Path:
        return self._root / f"{key}.jsonl"

    def _entries(self, key: str) -> dict[str, Entry]:
        """The key's entries, read once; a cut-off last line is removed from the file."""
        if key not in self._loaded:
            entries: dict[str, Entry] = {}
            path = self._file(key)
            if path.exists():
                whole, newline, cut = path.read_bytes().rpartition(b"\n")
                if cut:
                    with path.open("r+b") as file:
                        file.truncate(len(whole) + len(newline))
                for line in whole.split(b"\n"):
                    if line:
                        record = json.loads(line)
                        hits = [
                            Hit(passage, float(score))
                            for passage, score in record["hits"]
                        ]
                        entries[record["question"]] = Entry(
                            hits, float(record["seconds"])
                        )
            self._loaded[key] = entries
        return self._loaded[key]

    def get(self, key: str, question: str) -> Entry | None:
        entry = self._entries(key).get(_question_key(question))
        return None if entry is None else Entry(list(entry.hits), entry.seconds)

    def put(self, key: str, question: str, hits: Sequence[Hit], seconds: float) -> None:
        entries = self._entries(key)
        self._root.mkdir(parents=True, exist_ok=True)
        record = {
            "hits": [[hit.passage_id, hit.score] for hit in hits],
            "question": _question_key(question),
            "seconds": seconds,
        }
        with self._file(key).open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(record, sort_keys=True) + "\n")
        entries[_question_key(question)] = Entry(list(hits), seconds)
