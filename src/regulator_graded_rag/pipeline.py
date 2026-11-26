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
run answered from the cache still records what each answer cost. A config runs one first
stage, BM25 or dense, or two fused by RRF or a weighted sum; the fusion's own entries
sit under a key made of its settings and both stages' keys, and a fused answer reports
the seconds of all three steps. settings() names what a dense stage's answers depend on
beyond its config (RECORDED): its vectors' SHA-256, dtype and count of cut passages, and
the device, torch and CUDA it ran on. Reranking comes with its own experiments.
"""

import hashlib
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from regulator_graded_rag.bm25 import BM25, Conn, Hit
from regulator_graded_rag.cache import Entry, StageCache, source_digest, stage_key
from regulator_graded_rag.configs import Bm25Stage, Config, ConfigError, DenseStage
from regulator_graded_rag.dense import Dense
from regulator_graded_rag.embeddings import Encoder, model_key
from regulator_graded_rag.fusion import rrf, weighted
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
        self._fusion_key: str | None = None
        if config.fusion is not None:
            if len(config.fusion.values) != 1:
                raise ConfigError(
                    f"{config.path} tunes {config.tuned}: use one of its values"
                )
            kinds = [type(settings) for settings in config.first]
            if config.fusion.method == "weighted" and sorted(
                kind.__name__ for kind in kinds
            ) != sorted((Bm25Stage.__name__, DenseStage.__name__)):
                raise ConfigError(
                    f"{config.path}: a weighted fusion needs one bm25 and one dense"
                    " stage"
                )
            # The weighted sum weighs the lists by kind, not by their order.
            self._bm25_at = kinds.index(Bm25Stage) if Bm25Stage in kinds else 0
            self._fusion_key = stage_key(
                {
                    "stage": "Fusion",
                    "settings": asdict(config.fusion),
                    "upstream": [key for key, _ in self._first],
                    "corpus_version": corpus_version,
                    "code": code,
                }
            )

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

    def _fuse(self, lists: Sequence[Sequence[Hit]]) -> list[Hit]:
        fusion = self._config.fusion
        assert fusion is not None
        if fusion.method == "rrf":
            return rrf(lists, fusion.values[0])
        bm25 = lists[self._bm25_at]
        dense = lists[1 - self._bm25_at]
        return weighted(bm25, dense, fusion.values[0])

    def search(self, question: str, k: int) -> list[Hit]:
        """The k best passages, k at most DEPTH, which every stage keeps."""
        if k > DEPTH:
            raise ValueError(f"each stage keeps its top {DEPTH} passages, not {k}")
        entries = [self._cached(key, stage, question) for key, stage in self._first]
        if self._fusion_key is None:
            self._seconds = entries[0].seconds
            return entries[0].hits[:k]
        fused = self._cache.get(self._fusion_key, question)
        if fused is None:
            start = self._clock()
            hits = self._fuse([entry.hits for entry in entries])
            fused = Entry(hits, self._clock() - start)
            self._cache.put(self._fusion_key, question, fused.hits, fused.seconds)
        self._seconds = math.fsum(
            [*(entry.seconds for entry in entries), fused.seconds]
        )
        return fused.hits[:k]

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
    or a reranker, which comes with its own experiments."""
    if config.tuned is not None:
        raise ConfigError(
            f"{config.path} tunes {config.tuned}: build a pipeline for one of its values"
        )
    if config.rerank is not None:
        raise ConfigError(f"{config.path}: reranking comes with its own experiments")
    first: list[Stage] = []
    for stage in config.first:
        if isinstance(stage, Bm25Stage):
            first.append(
                BM25(
                    conn,
                    corpus_version=corpus_version,
                    k1=stage.k1,
                    b=stage.b,
                    schema=schema,
                )
            )
            continue
        encoder = (encoders or {}).get(model_key(stage.model, stage.revision))
        if encoder is None:
            raise ConfigError(
                f"{config.path}: no encoder for {stage.model} at {stage.revision}"
            )
        first.append(
            Dense(
                conn,
                stage=stage,
                corpus_version=corpus_version,
                encoder=encoder,
                index_schema=schema,
            )
        )
    return Pipeline(
        config,
        first,
        corpus_version=corpus_version,
        cache=cache,
        code=code_digest(),
    )
