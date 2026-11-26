# Author: Nicola Antonello
import shutil
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from regulator_graded_rag import pipeline as pipeline_module
from regulator_graded_rag.bm25 import Conn, Hit
from regulator_graded_rag.cache import StageCache
from regulator_graded_rag.configs import Bm25Stage, Config, ConfigError, load_config
from regulator_graded_rag.embeddings import Encoder, model_key
from regulator_graded_rag.fusion import rrf, weighted
from regulator_graded_rag.metrics import DEPTH
from regulator_graded_rag.pipeline import Pipeline, build, code_digest

BASELINE = Path("eval/configs/bm25.toml")
CORPUS = "c" * 64
CODE = "s" * 64
# Scores with long decimal forms, so a lossy trip through the cache file would show.
HITS = [Hit("171.1:1", 1 / 3), Hit("172.101:9", 0.1 + 0.2), Hit("173.185:3", 2.5e-17)]


class FakeBm25:
    """Stands in for BM25's SQL and counts the searches it is asked for."""

    def __init__(self, built: str = "1") -> None:
        self.calls: list[tuple[str, int]] = []
        self.built = built

    def identity(self) -> dict[str, object]:
        return {"index_built": self.built}

    def search(self, question: str, k: int) -> list[Hit]:
        self.calls.append((question, k))
        return HITS[:k]


DENSE_HITS = [Hit("173.185:3", 0.9), Hit("175.10:1", 0.5), Hit("171.1:1", 0.4)]
BM25_TOML = '[[first_stage]]\nkind = "bm25"\nk1 = 1.2\nb = 0.75\n'
DENSE_TOML = (
    '[[first_stage]]\nkind = "dense"\nmodel = "m"\nrevision = "r"\n'
    f'weights_sha256 = "{"a" * 64}"\nquery_prompt = ""\nmax_length = 512\n'
)
RRF = '[fusion]\nmethod = "rrf"\nk = 60\n'


class FakeDense:
    """Stands in for the dense stage and counts the searches it is asked for."""

    def __init__(self, vectors: str = "v1") -> None:
        self.calls: list[tuple[str, int]] = []
        self.vectors = vectors

    def identity(self) -> dict[str, object]:
        return {"vectors_sha256": self.vectors}

    def search(self, question: str, k: int) -> list[Hit]:
        self.calls.append((question, k))
        return DENSE_HITS[:k]


def config_file(tmp_path: Path, name: str, body: str) -> Config:
    path = tmp_path / f"{name}.toml"
    path.write_text(f'name = "{name}"\n{body}', encoding="utf-8", newline="\n")
    return load_config(path)


def ticks(*times: float) -> Callable[[], float]:
    """A clock that reads the given times in turn."""
    return iter(times).__next__


def pipeline(
    cache: Path,
    stage: FakeBm25,
    *,
    config: Config | None = None,
    corpus: str = CORPUS,
    code: str = CODE,
    clock: Callable[[], float] | None = None,
) -> Pipeline:
    return Pipeline(
        config or load_config(BASELINE),
        [stage],
        corpus_version=corpus,
        cache=StageCache(cache),
        code=code,
        clock=clock or time.perf_counter,
    )


def test_a_bm25_config_searches_like_bm25(tmp_path: Path) -> None:
    config = load_config(BASELINE)
    stage = FakeBm25()
    found = pipeline(tmp_path, stage, config=config)
    assert found.name == "bm25"
    assert found.settings() == {
        "config_file": "eval/configs/bm25.toml",
        "config_sha256": config.sha256,
    }
    assert found.search("Is it?", 2) == HITS[:2]
    # The stage always gives the pipeline its full depth, whatever k is asked for.
    assert stage.calls == [("Is it?", DEPTH)]


def test_a_cached_search_does_not_call_the_stage_again(tmp_path: Path) -> None:
    stage = FakeBm25()
    first = pipeline(tmp_path, stage)
    assert first.search("Is it?", DEPTH) == HITS
    assert first.search("Is it?", DEPTH) == HITS
    # The next run's pipeline reads the same folder, through the file.
    assert pipeline(tmp_path, stage).search("Is it?", DEPTH) == HITS
    assert stage.calls == [("Is it?", DEPTH)]


def test_an_answer_from_the_cache_reports_the_seconds_its_stage_took(
    tmp_path: Path,
) -> None:
    # Read from the cache, an answer takes microseconds; a run records what it cost.
    first = pipeline(tmp_path, FakeBm25(), clock=ticks(10.0, 10.25))
    first.search("Is it?", DEPTH)
    again = pipeline(tmp_path, FakeBm25(), clock=ticks())
    again.search("Is it?", DEPTH)
    assert (first.compute_seconds(), again.compute_seconds()) == (0.25, 0.25)


def test_deleting_the_cache_gives_the_same_hits(tmp_path: Path) -> None:
    stage = FakeBm25()
    before = pipeline(tmp_path / "cache", stage).search("Is it?", DEPTH)
    shutil.rmtree(tmp_path / "cache")
    after = pipeline(tmp_path / "cache", stage).search("Is it?", DEPTH)
    assert before == after == HITS and len(stage.calls) == 2


def test_other_settings_data_corpus_or_code_are_not_served_from_the_cache(
    tmp_path: Path,
) -> None:
    stage = FakeBm25()
    # The same settings over a rebuilt index search other data.
    rebuilt = FakeBm25(built="2")
    other_k1 = replace(load_config(BASELINE), first=(Bm25Stage(1.5, 0.75),))
    pipeline(tmp_path, stage).search("Is it?", DEPTH)
    pipeline(tmp_path, stage, config=other_k1).search("Is it?", DEPTH)
    pipeline(tmp_path, stage, corpus="d" * 64).search("Is it?", DEPTH)
    pipeline(tmp_path, stage, code="t" * 64).search("Is it?", DEPTH)
    pipeline(tmp_path, rebuilt).search("Is it?", DEPTH)
    assert (len(stage.calls), len(rebuilt.calls)) == (4, 1)


def test_the_code_digest_changes_with_the_package_or_the_locked_libraries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A new torch can change a model's outputs while the package's files stay the same.
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "a.py").write_text("x = 1\n", encoding="utf-8")
    lock = tmp_path / "uv.lock"
    lock.write_text('name = "torch"\nversion = "2.14.1"\n', encoding="utf-8")
    monkeypatch.setattr(pipeline_module, "PACKAGE", package)
    monkeypatch.setattr(pipeline_module, "LOCK", lock)
    first = code_digest()
    lock.write_text('name = "torch"\nversion = "2.15.0"\n', encoding="utf-8")
    second = code_digest()
    (package / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert len({first, second, code_digest()}) == 3


def test_build_keys_its_stage_by_the_code_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Code that changed never reads what older code wrote, through build as well.
    made: list[FakeBm25] = []

    def fake_bm25(
        conn: Conn, *, corpus_version: str, k1: float, b: float, schema: str
    ) -> FakeBm25:
        made.append(FakeBm25())
        return made[-1]

    digest = ["a" * 64]
    monkeypatch.setattr(pipeline_module, "BM25", fake_bm25)
    monkeypatch.setattr(pipeline_module, "code_digest", lambda: digest[0])
    for code in ("a" * 64, "a" * 64, "b" * 64):
        digest[0] = code
        built = build(
            load_config(BASELINE),
            cast(Conn, None),
            corpus_version=CORPUS,
            cache=StageCache(tmp_path),
        )
        built.search("Is it?", DEPTH)
    assert [len(stage.calls) for stage in made] == [1, 0, 1]


@pytest.mark.parametrize(
    ("name", "body", "match"),
    [
        (
            "grid",
            BM25_TOML
            + DENSE_TOML
            + '[fusion]\nmethod = "rrf"\nk = [10, 60]\n[cv]\nfolds = 5\nseed = "s"\n',
            "tunes k",
        ),
        # Reranking comes with its own experiments.
        (
            "reranked",
            BM25_TOML
            + '[rerank]\nmodel = "m2"\nrevision = "r2"\n'
            + f'weights_sha256 = "{"b" * 64}"\ndepth = 20\nmax_length = 512\n',
            "reranking comes with its own experiments",
        ),
        # A dense stage cannot search without its model.
        ("dense", DENSE_TOML, "no encoder"),
    ],
)
def test_build_refuses_a_grid_or_a_stage_it_cannot_run(
    tmp_path: Path, name: str, body: str, match: str
) -> None:
    with pytest.raises(ConfigError, match=match):
        build(
            config_file(tmp_path, name, body),
            cast(Conn, None),
            corpus_version=CORPUS,
            cache=StageCache(tmp_path),
        )


def fused(
    tmp_path: Path,
    config: Config,
    stages: list[FakeBm25 | FakeDense],
    clock: Callable[[], float] = time.perf_counter,
) -> Pipeline:
    return Pipeline(
        config,
        stages,
        corpus_version=CORPUS,
        cache=StageCache(tmp_path / "cache"),
        code=CODE,
        clock=clock,
    )


def test_a_fused_config_fuses_its_two_stages(tmp_path: Path) -> None:
    config = config_file(tmp_path, "hybrid", BM25_TOML + DENSE_TOML + RRF)
    bm25, dense = FakeBm25(), FakeDense()
    found = fused(tmp_path, config, [bm25, dense])
    assert found.search("Is it?", 3) == rrf([HITS, DENSE_HITS], 60.0)[:3]
    assert bm25.calls == dense.calls == [("Is it?", DEPTH)]
    assert found.settings()["vectors_sha256"] == "v1"


def test_a_weighted_fusion_tells_bm25_from_dense_by_kind(tmp_path: Path) -> None:
    # The dense stage comes first here, yet alpha still weighs the dense list.
    body = DENSE_TOML + BM25_TOML + '[fusion]\nmethod = "weighted"\nalpha = 1.0\n'
    found = fused(
        tmp_path, config_file(tmp_path, "hybrid", body), [FakeDense(), FakeBm25()]
    )
    assert found.search("Is it?", DEPTH) == weighted(HITS, DENSE_HITS, 1.0)


def test_a_weighted_fusion_needs_one_bm25_and_one_dense_stage(tmp_path: Path) -> None:
    body = BM25_TOML + BM25_TOML + '[fusion]\nmethod = "weighted"\nalpha = 0.5\n'
    with pytest.raises(ConfigError, match="one bm25 and one dense"):
        fused(tmp_path, config_file(tmp_path, "twice", body), [FakeBm25(), FakeBm25()])


def test_the_fusion_is_cached_under_its_stages_keys(tmp_path: Path) -> None:
    config = config_file(tmp_path, "hybrid", BM25_TOML + DENSE_TOML + RRF)
    cache = tmp_path / "cache"

    def search(bm25: FakeBm25) -> FakeDense:
        dense = FakeDense()
        fused(tmp_path, config, [bm25, dense]).search("Is it?", 3)
        return dense

    search(FakeBm25())
    assert len(list(cache.glob("*.jsonl"))) == 3
    again = FakeBm25()
    assert search(again).calls == [] and again.calls == []
    # A rebuilt index gives BM25 a new key, and so the fusion that reads it; the dense
    # stage's entry still serves.
    rebuilt = FakeBm25(built="2")
    assert search(rebuilt).calls == [] and len(rebuilt.calls) == 1
    assert len(list(cache.glob("*.jsonl"))) == 5


def test_a_fused_answer_reports_the_seconds_of_all_its_stages(tmp_path: Path) -> None:
    config = config_file(tmp_path, "hybrid", BM25_TOML + DENSE_TOML + RRF)
    # BM25 takes 1 s, the dense stage 2 s and the fusion 0.5 s.
    first = fused(
        tmp_path, config, [FakeBm25(), FakeDense()], ticks(0, 1, 1, 3, 3, 3.5)
    )
    first.search("Is it?", 3)
    assert first.compute_seconds() == 3.5
    # From the cache, no clock is read and the same seconds are reported.
    cached = fused(tmp_path, config, [FakeBm25(), FakeDense()], ticks())
    cached.search("Is it?", 3)
    assert cached.compute_seconds() == 3.5


def test_build_runs_both_stages_of_a_fused_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    given: list[object] = []

    def fake_bm25(
        conn: Conn, *, corpus_version: str, k1: float, b: float, schema: str
    ) -> FakeBm25:
        return FakeBm25()

    def fake_dense(
        conn: Conn,
        *,
        stage: object,
        corpus_version: str,
        encoder: Encoder,
        index_schema: str,
    ) -> FakeDense:
        given.append(encoder)
        return FakeDense()

    monkeypatch.setattr(pipeline_module, "BM25", fake_bm25)
    monkeypatch.setattr(pipeline_module, "Dense", fake_dense)
    encoder = cast(Encoder, object())
    built = build(
        config_file(tmp_path, "hybrid", BM25_TOML + DENSE_TOML + RRF),
        cast(Conn, None),
        corpus_version=CORPUS,
        cache=StageCache(tmp_path / "cache"),
        encoders={model_key("m", "r"): encoder},
    )
    assert built.search("Is it?", 3) == rrf([HITS, DENSE_HITS], 60.0)[:3]
    assert given == [encoder]


def test_a_search_deeper_than_the_stages_is_refused(tmp_path: Path) -> None:
    # Every stage keeps its top DEPTH, so a deeper search would quietly come up short.
    with pytest.raises(ValueError, match=str(DEPTH)):
        pipeline(tmp_path, FakeBm25()).search("Is it?", DEPTH + 1)
