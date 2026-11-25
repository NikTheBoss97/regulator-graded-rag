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
            '[fusion]\nmethod = "rrf"\nk = [10, 60]\n[cv]\nfolds = 5\nseed = "s"\n',
            "tunes k",
        ),
        # Fusion comes with its own experiments.
        ("fused", '[fusion]\nmethod = "rrf"\nk = 60\n', "single first stage"),
        # A dense stage cannot search without its model.
        ("dense", "", "no encoder"),
    ],
)
def test_build_refuses_a_grid_or_a_stage_it_cannot_run(
    tmp_path: Path, name: str, body: str, match: str
) -> None:
    dense = (
        '[[first_stage]]\nkind = "dense"\nmodel = "m"\nrevision = "r"\n'
        f'weights_sha256 = "{"a" * 64}"\nquery_prompt = ""\nmax_length = 512\n'
    )
    bm25 = '[[first_stage]]\nkind = "bm25"\nk1 = 1.2\nb = 0.75\n'
    first = bm25 + dense if body else dense
    path = tmp_path / f"{name}.toml"
    path.write_text(f'name = "{name}"\n{first}{body}', encoding="utf-8")
    with pytest.raises(ConfigError, match=match):
        build(
            load_config(path),
            cast(Conn, None),
            corpus_version=CORPUS,
            cache=StageCache(tmp_path),
        )


def test_a_search_deeper_than_the_stages_is_refused(tmp_path: Path) -> None:
    # Every stage keeps its top DEPTH, so a deeper search would quietly come up short.
    with pytest.raises(ValueError, match=str(DEPTH)):
        pipeline(tmp_path, FakeBm25()).search("Is it?", DEPTH + 1)
