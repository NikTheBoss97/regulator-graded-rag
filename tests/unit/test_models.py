# Author: Nicola Antonello
import hashlib
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

from regulator_graded_rag.configs import DenseStage
from regulator_graded_rag.models import (
    SentenceTransformerEncoder,
    WeightsMismatch,
    WeightsMissing,
)

WEIGHTS = b"weights"
PINNED = hashlib.sha256(WEIGHTS).hexdigest()


def stub_libraries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    cached: bool = True,
    loaded: str = "torch.float32",
    device: str = "cuda",
) -> list[tuple[object, ...]]:
    """Stand-ins for huggingface_hub, sentence_transformers and torch that record each
    call, so the loader's arguments are checked without the models group. The model
    reports the precision it loaded in as `loaded`, as torch names it, and runs on a
    device of type `device`."""
    calls: list[tuple[object, ...]] = []
    path = tmp_path / "model.safetensors"
    path.write_bytes(WEIGHTS)

    def hf_hub_download(
        *, repo_id: str, filename: str, revision: str, local_files_only: bool
    ) -> str:
        calls.append(("download", repo_id, filename, revision, local_files_only))
        return str(path)

    def try_to_load_from_cache(
        *, repo_id: str, filename: str, revision: str
    ) -> str | None:
        return str(path) if cached else None

    class SentenceTransformer:
        def __init__(self, name: str, **kwargs: object) -> None:
            calls.append(("load", name, kwargs))
            self.max_seq_length = 0
            self.dtype = loaded
            self.device = types.SimpleNamespace(type=device)

        def get_embedding_dimension(self) -> int:
            return 3

    hub = types.ModuleType("huggingface_hub")
    vars(hub).update(
        hf_hub_download=hf_hub_download, try_to_load_from_cache=try_to_load_from_cache
    )
    library = types.ModuleType("sentence_transformers")
    vars(library).update(SentenceTransformer=SentenceTransformer)
    torch = types.ModuleType("torch")
    vars(torch).update(
        __version__="2.14.1",
        version=types.SimpleNamespace(cuda="12.6"),
        cuda=types.SimpleNamespace(get_device_name=lambda device: "A GPU"),
    )
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setitem(sys.modules, "sentence_transformers", library)
    monkeypatch.setitem(sys.modules, "torch", torch)
    return calls


def stage(sha256: str) -> DenseStage:
    return DenseStage("org/model", "rev1", sha256, "", 512)


def test_the_encoder_loads_only_verified_safetensors_without_remote_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = stub_libraries(monkeypatch, tmp_path)
    SentenceTransformerEncoder(stage(PINNED))
    # The weights are checked first, at the pinned revision and from the cache only;
    # the model then loads safetensors alone, with no code from its repository.
    assert calls == [
        ("download", "org/model", "model.safetensors", "rev1", True),
        (
            "load",
            "org/model",
            {
                "revision": "rev1",
                "trust_remote_code": False,
                "local_files_only": True,
                "model_kwargs": {"use_safetensors": True, "dtype": "float32"},
            },
        ),
    ]


def test_a_model_loaded_at_another_precision_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A library that ignored the requested dtype would run the model in its stored 16
    # bits while the run record says float32, so the loaded precision is checked.
    stub_libraries(monkeypatch, tmp_path, loaded="torch.float16")
    with pytest.raises(WeightsMismatch, match="loaded in float16, not the config's"):
        SentenceTransformerEncoder(stage(PINNED))
    # A model asked for in 16 bits and loaded in them is the config's.
    stub_libraries(monkeypatch, tmp_path, loaded="torch.bfloat16")
    SentenceTransformerEncoder(replace(stage(PINNED), dtype="bfloat16"))


def test_the_record_names_the_device_a_model_runs_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stub_libraries(monkeypatch, tmp_path, device="cuda")
    encoder = SentenceTransformerEncoder(stage(PINNED))
    assert encoder.runtime() == {"gpu": "A GPU", "torch": "2.14.1", "cuda": "12.6"}
    # Apple's GPU is not a CUDA device, but a run on it is not a CPU run either: the
    # run record and the stage's cache key must tell the two apart.
    stub_libraries(monkeypatch, tmp_path, device="mps")
    assert SentenceTransformerEncoder(stage(PINNED)).runtime()["gpu"] == "mps"


def test_weights_with_another_checksum_are_never_loaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = stub_libraries(monkeypatch, tmp_path)
    with pytest.raises(WeightsMismatch):
        SentenceTransformerEncoder(stage("0" * 64))
    assert [call[0] for call in calls] == ["download"]


def test_missing_weights_are_downloaded_only_when_asked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Every download needs a go-ahead, so a run never fetches weights by itself.
    calls = stub_libraries(monkeypatch, tmp_path, cached=False)
    with pytest.raises(WeightsMissing, match="--download"):
        SentenceTransformerEncoder(stage(PINNED))
    assert calls == []
    SentenceTransformerEncoder(stage(PINNED), offline=False)
    assert calls[0] == ("download", "org/model", "model.safetensors", "rev1", False)
