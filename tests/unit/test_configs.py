# Author: Nicola Antonello
import hashlib
from pathlib import Path

import pytest

from regulator_graded_rag.configs import (
    Bm25Stage,
    ConfigError,
    DenseStage,
    fixed,
    load_config,
)

REPO = Path(__file__).resolve().parents[2]
SHA = "a" * 64
BM25 = """
[[first_stage]]
kind = "bm25"
k1 = 1.2
b = 0.75
"""
DENSE = f"""
[[first_stage]]
kind = "dense"
model = "BAAI/bge-base-en-v1.5"
revision = "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"
weights_sha256 = "{SHA}"
query_prompt = ""
max_length = 512
"""
RRF_GRID = '[fusion]\nmethod = "rrf"\nk = [10, 30, 60, 100]\n'
CV = '[cv]\nfolds = 5\nseed = "phase-3-folds-2026-11-25"\n'


def write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.toml"
    path.write_text(f'name = "{name}"\n{body}', encoding="utf-8", newline="\n")
    return path


def test_the_baseline_config_loads() -> None:
    path = REPO / "eval" / "configs" / "bm25.toml"
    c = load_config(path)
    assert c.name == "bm25" and c.first == (Bm25Stage(1.2, 0.75),)
    assert (c.fusion, c.rerank, c.cv, c.tuned) == (None, None, None, None)
    assert c.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_grid_needs_cross_validation(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cv"):
        load_config(write(tmp_path, "hybrid", BM25 + DENSE + RRF_GRID))
    assert (
        load_config(write(tmp_path, "tuned", BM25 + DENSE + RRF_GRID + CV)).tuned == "k"
    )


def test_two_first_stages_need_a_fusion(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="fusion"):
        load_config(write(tmp_path, "two", BM25 + DENSE))


def test_a_fusion_needs_two_first_stages(tmp_path: Path) -> None:
    body = BM25 + '[fusion]\nmethod = "rrf"\nk = 60\n'
    with pytest.raises(ConfigError, match="two first stages"):
        load_config(write(tmp_path, "one", body))


@pytest.mark.parametrize("field", ["revision", "weights_sha256"])
def test_a_model_needs_its_revision_and_weights_checksum(
    tmp_path: Path, field: str
) -> None:
    body = "\n".join(line for line in DENSE.splitlines() if not line.startswith(field))
    with pytest.raises(ConfigError, match=field):
        load_config(write(tmp_path, "dense", body))


def test_the_name_must_match_the_file_name(tmp_path: Path) -> None:
    path = tmp_path / "other.toml"
    path.write_text('name = "bm25"\n' + BM25, encoding="utf-8", newline="\n")
    with pytest.raises(ConfigError, match="other"):
        load_config(path)


def test_only_one_setting_may_be_tuned(tmp_path: Path) -> None:
    rerank = (
        f'[rerank]\nmodel = "m"\nrevision = "r"\nweights_sha256 = "{SHA}"\n'
        "depth = [10, 20]\nmax_length = 512\n"
    )
    with pytest.raises(ConfigError, match="one setting"):
        load_config(write(tmp_path, "both", BM25 + DENSE + RRF_GRID + rerank + CV))


def test_fixed_replaces_the_grid(tmp_path: Path) -> None:
    c = load_config(write(tmp_path, "rrf", BM25 + DENSE + RRF_GRID + CV))
    one = fixed(c, 30)
    assert one.fusion is not None and one.fusion.values == (30.0,)
    assert one.tuned is None
    with pytest.raises(ConfigError, match="grid"):
        fixed(c, 45)


RERANK = (
    f'[rerank]\nmodel = "m"\nrevision = "r"\nweights_sha256 = "{SHA}"\n'
    "depth = 20\nmax_length = 512\n"
)


@pytest.mark.parametrize(
    ("body", "match"),
    [
        # A misspelt key would run without its setting while the file seems to set it.
        (DENSE.replace("query_prompt", "query_promt"), "unknown keys query_promt"),
        (BM25 + RERANK.replace("[rerank]", "[rerankk]"), "unknown keys rerankk"),
        (BM25 + RERANK + 'loadr = "transformers"\n', "unknown keys loadr"),
        (BM25.replace("k1 = 1.2", "k1 = 1.2\nkl = 1.5"), "unknown keys kl"),
        (
            BM25 + DENSE + '[fusion]\nmethod = "rrf"\nk = 60\nalpha = 0.5\n',
            "keys alpha",
        ),
        (BM25 + RERANK + CV.replace("seed", "sed"), "unknown keys sed"),
        ("seed = 1\n" + BM25, "unknown keys seed"),
        # A forgotten prompt is refused; a model without one says so with "".
        (DENSE.replace('query_prompt = ""\n', ""), "query_prompt"),
        # A value that would run other than written.
        (BM25 + DENSE + '[fusion]\nmethod = "weighted"\nalpha = 7\n', "alpha"),
        (BM25 + RERANK.replace("depth = 20", "depth = [10.5, 20]") + CV, "depth"),
        (BM25 + RERANK.replace("depth = 20", "depth = 60"), "depth"),
        (BM25.replace("k1 = 1.2", "k1 = true"), "k1"),
        (BM25.replace("b = 0.75", "b = 7.5"), "b from 0 to 1"),
        (BM25 + DENSE + '[fusion]\nmethod = "rrf"\nk = []\n', "k needs"),
        (BM25 + DENSE + RRF_GRID + CV.replace("folds = 5", "folds = 1"), "folds"),
        (BM25 + CV, "no grid"),
        ('first_stage = ["bm25"]\n', "not a table"),
        (DENSE + 'dtype = "int8"\n', "dtype must be"),
    ],
)
def test_a_config_that_would_run_other_than_written_is_refused(
    tmp_path: Path, body: str, match: str
) -> None:
    with pytest.raises(ConfigError, match=match):
        load_config(write(tmp_path, "c", body))


def test_a_dense_stage_states_its_precision_or_runs_in_float32(tmp_path: Path) -> None:
    # The precision a model runs in can change its vectors, so it is a setting; a config
    # that states none, as E1's, runs in float32, the precision E1 ran in.
    stage = load_config(write(tmp_path, "dense", DENSE)).first[0]
    assert isinstance(stage, DenseStage) and stage.dtype == "float32"
    half = load_config(write(tmp_path, "half", DENSE + 'dtype = "bfloat16"\n'))
    assert isinstance(half.first[0], DenseStage) and half.first[0].dtype == "bfloat16"


def test_a_prompt_keeps_its_newline(tmp_path: Path) -> None:
    body = DENSE.replace('query_prompt = ""', 'query_prompt = "Instruct: x\\nQuery:"')
    stage = load_config(write(tmp_path, "dense", body)).first[0]
    assert isinstance(stage, DenseStage) and stage.query_prompt == "Instruct: x\nQuery:"
