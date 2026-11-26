# Author: Nicola Antonello
"""One pipeline that runs every experiment config (ADR-0023).

build() turns a fixed config into a retriever with the harness's interface (name,
settings() and search(question, k)), so the run command and phase 4 call it like BM25.
Each stage keeps its top DEPTH passages per question, and its output goes through the
stage cache under a key made of:
- the stage's kind and settings;
- the identity of the data it reads, such as when BM25's index was built or which
  vectors a dense stage loaded;
- the corpus version;
- the code: the package's Python files, which also hold the depth, and the locked
  library versions in uv.lock.
A key never outlives the code or the data that filled it. The gold set is not part of a
key, since a stage sees only the question's text, which keys each entry. Each entry keeps
the seconds its stage took, and compute_seconds() reports them for the last search, so a
run answered from the cache still records what each answer cost. This version runs a
single first stage, BM25 or dense, and settings() names what a dense stage's answers
depend on beyond its config (RECORDED): its vectors' SHA-256, dtype and count of cut
passages, and the device, torch and CUDA it ran on. Fusion and reranking come with
their experiments.
"""

import hashlib
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from regulator_graded_rag.bm25 import BM25, Conn, Hit
from regulator_graded_rag.cache import Entry, StageCache, source_digest, stage_key
from regulator_graded_rag.configs import Bm25Stage, Config, ConfigError
from regulator_graded_rag.dense import Dense
from regulator_graded_rag.embeddings import Encoder, model_key
from regulator_graded_rag.index import SCHEMA
from regulator_graded_rag.metrics import DEPTH

PACKAGE = Path(__file__).resolve().parent
LOCK = PACKAGE.parents[1] / "uv.lock"
# The parts of a stage's identity that a run record names.
RECORDED = ("vectors_sha256", "dtype", "truncated", "gpu", "torch", "cuda")


def code_digest() -> str:
    """The SHA-256 over the package's Python files and the locked library versions: a
    new torch can change a model's outputs while the package stays the same."""
    lock = hashlib.sha256(LOCK.read_bytes()).hexdigest()
    return stage_key({"package": source_digest(PACKAGE), "lock": lock})


class Stage(Protocol):
    """A first stage: a question's best passages, best first, and the identity of the
    data it searches, which joins its cache key."""

    def identity(self) -> Mapping[str, object]: ...

    def search(self, question: str, k: int) -> list[Hit]: ...


class Pipeline:
    """A fixed config's stages behind the harness's retriever interface."""

    def __init__(
        self,
        config: Config,
        first: Sequence[Stage],
        *,
        corpus_version: str,
        cache: StageCache,
        code: str,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.name = config.name
        self._config = config
        self._cache = cache
        self._clock = clock
        self._seconds = 0.0
        identities = [dict(stage.identity()) for stage in first]
        self._first = [
            (
                stage_key(
                    {
                        "stage": type(settings).__name__,
                        "settings": asdict(settings),
                        "data": identity,
                        "corpus_version": corpus_version,
                        "code": code,
                    }
                ),
                stage,
            )
            for settings, stage, identity in zip(
                config.first, first, identities, strict=True
            )
        ]
        self._identities = identities

    def settings(self) -> dict[str, str | float]:
        """The config by path and SHA-256, and for a dense stage the parts of its
        identity a run record names (RECORDED): the exact embeddings it searched, their
        precision, how many passages were cut, and the GPU and libraries that embedded
        the questions."""
        found: dict[str, str | float] = {
            "config_file": self._config.path,
            "config_sha256": self._config.sha256,
        }
        for key in RECORDED:
            values = [identity[key] for identity in self._identities if key in identity]
            if len(values) == 1 and isinstance(values[0], int | float):
                found[key] = values[0]
            elif values:
                found[key] = ",".join(str(value) for value in values)
        return found

    def _cached(self, key: str, stage: Stage, question: str) -> Entry:
        entry = self._cache.get(key, question)
        if entry is None:
            start = self._clock()
            hits = stage.search(question, DEPTH)
            entry = Entry(hits, self._clock() - start)
            self._cache.put(key, question, entry.hits, entry.seconds)
        return entry

    def search(self, question: str, k: int) -> list[Hit]:
        """The k best passages, k at most DEPTH, which every stage keeps."""
        if k > DEPTH:
            raise ValueError(f"each stage keeps its top {DEPTH} passages, not {k}")
        key, stage = self._first[0]
        entry = self._cached(key, stage, question)
        self._seconds = entry.seconds
        return entry.hits[:k]

    def compute_seconds(self) -> float:
        """The seconds the last search's stages took to compute its answer, whether it
        came from them or from the cache."""
        return self._seconds


def build(
    config: Config,
    conn: Conn,
    *,
    corpus_version: str,
    cache: StageCache,
    schema: str = SCHEMA,
    encoders: Mapping[str, Encoder] | None = None,
) -> Pipeline:
    """The pipeline for a fixed config, with each dense stage's encoder found by
    model_key(model, revision); refused with ConfigError for a grid, a missing encoder,
    or stages this version cannot run."""
    if config.tuned is not None:
        raise ConfigError(
            f"{config.path} tunes {config.tuned}: build a pipeline for one of its values"
        )
    if config.fusion or config.rerank:
        raise ConfigError(f"{config.path}: this pipeline runs a single first stage")
    stage = config.first[0]
    first: Stage
    if isinstance(stage, Bm25Stage):
        first = BM25(
            conn, corpus_version=corpus_version, k1=stage.k1, b=stage.b, schema=schema
        )
    else:
        encoder = (encoders or {}).get(model_key(stage.model, stage.revision))
        if encoder is None:
            raise ConfigError(
                f"{config.path}: no encoder for {stage.model} at {stage.revision}"
            )
        first = Dense(
            conn,
            stage=stage,
            corpus_version=corpus_version,
            encoder=encoder,
            index_schema=schema,
        )
    return Pipeline(
        config,
        [first],
        corpus_version=corpus_version,
        cache=cache,
        code=code_digest(),
    )
