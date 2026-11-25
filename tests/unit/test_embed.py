# Author: Nicola Antonello
import hashlib
from pathlib import Path
from typing import cast

import pytest

from regulator_graded_rag.bm25 import Conn
from regulator_graded_rag.embed import embed_stage, main
from regulator_graded_rag.embeddings import model_key, write_vectors
from regulator_graded_rag.models import WeightsMismatch, require_sha256
from tests.unit.test_dense import CORPUS, STAGE, FakeEncoder


def test_embed_needs_a_dense_stage(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--config", "eval/configs/bm25.toml"]) == 1
    assert "no dense stage" in capsys.readouterr().out


def test_vectors_made_with_another_max_length_are_not_reused(tmp_path: Path) -> None:
    # The file is named by model and revision alone, so a config that reads more or
    # fewer tokens must not take vectors computed for another length.
    key = model_key(STAGE.model, STAGE.revision)
    header = {
        "model": STAGE.model,
        "revision": STAGE.revision,
        "corpus_version": CORPUS,
        "max_length": 256,
        "truncated": 0,
    }
    write_vectors(tmp_path / f"{key}.f32", [[1.0, 0.0, 0.0]], header)
    with pytest.raises(ValueError, match="max_length"):
        embed_stage(
            cast(Conn, None),
            STAGE,
            FakeEncoder(),
            corpus_version=CORPUS,
            folder=tmp_path,
        )


def test_a_file_with_another_sha256_is_refused(tmp_path: Path) -> None:
    # Weights are loaded only when they are the file the config pins.
    path = tmp_path / "model.safetensors"
    path.write_bytes(b"weights")
    with pytest.raises(WeightsMismatch, match="not the pinned"):
        require_sha256(path, "0" * 64)
    assert require_sha256(path, hashlib.sha256(b"weights").hexdigest()) == path
