# Author: Nicola Antonello
"""Experiment configs: one TOML file per configuration, in eval/configs/ (ADR-0023).

A config names one or two first stages (bm25 or dense), a fusion when there are two
(rrf or weighted), an optional reranker, and, when a setting is a grid, the
cross-validation that tunes it (ADR-0024). A scalar setting is fixed; a list of more
than one value is a grid, and at most one setting may be a grid. A model is pinned by
its Hugging Face revision and by its weights file's SHA-256. The file's name is the
config's name, and a config that produced a committed run is never edited: a change is a
new config with a new name.

A config runs exactly as written or not at all. Each table may hold only the keys its
kind uses, so a misspelt key is refused rather than left out; a dense stage states its
query prompt, "" for a model without one; and a value out of its range is refused
rather than rounded or capped. A dense stage's dtype, the precision its model runs in,
is float32 unless the config states float16 or bfloat16 (ADR-0009).
"""

import hashlib
import re
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TypeIs

from regulator_graded_rag.metrics import DEPTH

LOADERS = ("cross-encoder", "transformers")
DTYPES = ("float32", "float16", "bfloat16")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_KEYS = {
    "config": {"name", "first_stage", "fusion", "rerank", "cv"},
    "bm25": {"kind", "k1", "b"},
    "dense": {
        "kind",
        "model",
        "revision",
        "weights_sha256",
        "query_prompt",
        "max_length",
        "dtype",
    },
    "rrf": {"method", "k"},
    "weighted": {"method", "alpha"},
    "rerank": {"model", "revision", "weights_sha256", "depth", "max_length", "loader"},
    "cv": {"folds", "seed"},
}


class ConfigError(ValueError):
    """A config that cannot run as written."""


@dataclass(frozen=True)
class Bm25Stage:
    k1: float
    b: float


@dataclass(frozen=True)
class DenseStage:
    model: str
    revision: str
    weights_sha256: str
    query_prompt: str
    max_length: int
    dtype: str = "float32"


@dataclass(frozen=True)
class Fusion:
    method: str
    values: tuple[float, ...]


@dataclass(frozen=True)
class RerankStage:
    model: str
    revision: str
    weights_sha256: str
    depths: tuple[int, ...]
    max_length: int
    loader: str


@dataclass(frozen=True)
class Cv:
    folds: int
    seed: str


@dataclass(frozen=True)
class Config:
    name: str
    path: str
    sha256: str
    text: str
    first: tuple[Bm25Stage | DenseStage, ...]
    fusion: Fusion | None
    rerank: RerankStage | None
    cv: Cv | None

    @property
    def tuned(self) -> str | None:
        """The one setting with more than one value: "k", "alpha" or "depth"."""
        if self.fusion is not None and len(self.fusion.values) > 1:
            return "k" if self.fusion.method == "rrf" else "alpha"
        if self.rerank is not None and len(self.rerank.depths) > 1:
            return "depth"
        return None


def _table(value: object, kind: str, where: str) -> dict[str, Any]:
    """The value as a table holding only the keys its kind uses."""
    if not isinstance(value, dict):
        raise ConfigError(f"{where} is not a table")
    unknown = sorted(set(value) - _KEYS[kind])
    if unknown:
        raise ConfigError(f"{where}: unknown keys {', '.join(unknown)}")
    return value


def _is_number(value: object) -> TypeIs[int | float]:
    """A TOML integer or float; true and false are not numbers here."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def _values(table: dict[str, Any], key: str, where: str) -> tuple[Any, ...]:
    """The setting's values: one, or a list of more than one, which is a grid."""
    if key not in table:
        raise ConfigError(f"{where} needs {key}")
    value = table[key]
    values = tuple(value) if isinstance(value, list) else (value,)
    if not values:
        raise ConfigError(f"{where}: {key} needs a value")
    return values


def _number(table: dict[str, Any], key: str, where: str, least: int = 1) -> int:
    value = table.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < least:
        raise ConfigError(f"{where} needs {key} as a whole number of {least} or more")
    return value


def _model(table: dict[str, Any], where: str) -> tuple[str, str, str]:
    """The model's name, revision and weights checksum, each required."""
    for key in ("model", "revision", "weights_sha256"):
        if not isinstance(table.get(key), str) or not table[key]:
            raise ConfigError(f"{where} needs {key}")
    if not _SHA256.fullmatch(table["weights_sha256"]):
        raise ConfigError(f"{where}'s weights_sha256 is not a SHA-256 in lowercase hex")
    return table["model"], table["revision"], table["weights_sha256"]


def _stage(value: object, where: str) -> Bm25Stage | DenseStage:
    if not isinstance(value, dict):
        raise ConfigError(f"{where} is not a table")
    kind = value.get("kind")
    if kind == "bm25":
        table = _table(value, "bm25", where)
        k1, b = table.get("k1"), table.get("b")
        if not _is_number(k1) or not _is_number(b):
            raise ConfigError(f"{where}: bm25 needs fixed numbers k1 and b")
        if k1 < 0 or not 0 <= b <= 1:
            raise ConfigError(f"{where}: bm25 needs k1 of 0 or more and b from 0 to 1")
        return Bm25Stage(float(k1), float(b))
    if kind == "dense":
        table = _table(value, "dense", where)
        model, revision, sha256 = _model(table, where)
        prompt = table.get("query_prompt")
        if not isinstance(prompt, str):
            raise ConfigError(f'{where} needs query_prompt, "" for a model without one')
        dtype = table.get("dtype", "float32")
        if dtype not in DTYPES:
            raise ConfigError(f"{where}: dtype must be one of {', '.join(DTYPES)}")
        return DenseStage(
            model,
            revision,
            sha256,
            prompt,
            _number(table, "max_length", where),
            dtype,
        )
    raise ConfigError(f"{where}: unknown first-stage kind {kind!r}")


def load_config(path: Path) -> Config:
    """The config in the file, refused with ConfigError unless it can run as written."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    where = path.as_posix()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(f"{where}: {err}") from err
    data = _table(data, "config", where)
    if data.get("name") != path.stem:
        raise ConfigError(
            f"{where}: its name {data.get('name')!r} must be the file's name,"
            f" {path.stem!r}"
        )
    stages = data.get("first_stage", [])
    if not isinstance(stages, list) or len(stages) not in (1, 2):
        raise ConfigError(f"{where} needs one or two first stages")
    first = tuple(
        _stage(table, f"{where} first stage {i}") for i, table in enumerate(stages, 1)
    )
    fusion = None
    if "fusion" in data:
        if len(first) != 2:
            raise ConfigError(f"{where}: a fusion needs two first stages")
        if not isinstance(data["fusion"], dict):
            raise ConfigError(f"{where} fusion is not a table")
        method = data["fusion"].get("method")
        if not isinstance(method, str) or method not in ("rrf", "weighted"):
            raise ConfigError(f"{where}: unknown fusion method {method!r}")
        key = "k" if method == "rrf" else "alpha"
        table = _table(data["fusion"], method, f"{where} fusion")
        values = _values(table, key, f"{where} fusion")
        if not all(_is_number(v) for v in values):
            raise ConfigError(f"{where} fusion: {key} needs numbers")
        if method == "weighted" and not all(0 <= v <= 1 for v in values):
            raise ConfigError(f"{where} fusion: alpha must be from 0 to 1")
        if method == "rrf" and not all(v >= 0 for v in values):
            raise ConfigError(f"{where} fusion: k must be 0 or more")
        fusion = Fusion(method, tuple(float(v) for v in values))
        if len(set(fusion.values)) != len(fusion.values):
            raise ConfigError(f"{where} fusion: {key} repeats a value")
    elif len(first) == 2:
        raise ConfigError(f"{where}: two first stages need a fusion")
    rerank = None
    if "rerank" in data:
        table = _table(data["rerank"], "rerank", f"{where} rerank")
        model, revision, sha256 = _model(table, f"{where} rerank")
        loader = table.get("loader", "cross-encoder")
        if loader not in LOADERS:
            raise ConfigError(f"{where}: the rerank loader must be one of {LOADERS}")
        depths = _values(table, "depth", f"{where} rerank")
        if not all(
            isinstance(d, int) and not isinstance(d, bool) and 1 <= d <= DEPTH
            for d in depths
        ):
            raise ConfigError(
                f"{where} rerank: depth must be whole numbers from 1 to {DEPTH}"
            )
        if len(set(depths)) != len(depths):
            raise ConfigError(f"{where} rerank: depth repeats a value")
        rerank = RerankStage(
            model,
            revision,
            sha256,
            depths,
            _number(table, "max_length", f"{where} rerank"),
            loader,
        )
    cv = None
    if "cv" in data:
        table = _table(data["cv"], "cv", f"{where} [cv]")
        seed = table.get("seed")
        if not isinstance(seed, str) or not seed:
            raise ConfigError(f"{where}: [cv] needs a seed")
        cv = Cv(_number(table, "folds", f"{where} [cv]", least=2), seed)
    config = Config(
        name=path.stem,
        path=where,
        sha256=hashlib.sha256(raw).hexdigest(),
        text=text,
        first=first,
        fusion=fusion,
        rerank=rerank,
        cv=cv,
    )
    grids = (fusion is not None and len(fusion.values) > 1) + (
        rerank is not None and len(rerank.depths) > 1
    )
    if grids > 1:
        raise ConfigError(f"{where}: only one setting may be tuned at a time")
    if config.tuned is not None and cv is None:
        raise ConfigError(f"{where}: the grid for {config.tuned} needs a [cv] table")
    if config.tuned is None and cv is not None:
        raise ConfigError(f"{where}: [cv] has no grid to tune")
    return config


def fixed(config: Config, value: float | None) -> Config:
    """The config with its grid replaced by one of the grid's own values; an untuned
    config is returned as it is."""
    if config.tuned is None:
        if value is not None:
            raise ConfigError(f"{config.name} has no grid to fix")
        return config
    if value is None:
        raise ConfigError(f"{config.name} tunes {config.tuned}: give one of its values")
    if config.rerank is not None and config.tuned == "depth":
        if value not in config.rerank.depths:
            raise ConfigError(f"{value} is not in {config.name}'s grid for depth")
        return replace(config, rerank=replace(config.rerank, depths=(int(value),)))
    assert config.fusion is not None
    if float(value) not in config.fusion.values:
        raise ConfigError(f"{value} is not in {config.name}'s grid for {config.tuned}")
    return replace(config, fusion=replace(config.fusion, values=(float(value),)))
