# Author: Nicola Antonello
"""The local models behind the dense stage (ADR-0009).

They come from the models dependency group, which CI never installs, so torch,
sentence-transformers and huggingface_hub are imported only inside the functions that
use them. A model runs only from its pinned revision, once its weights file matches the
SHA-256 its config pins; transformers then loads those safetensors weights, never a
pickle file, and never code from the model's repository. Every download is asked for:
by default only the local cache is read, and missing weights are refused.
"""

import hashlib
from collections.abc import Sequence
from pathlib import Path

from regulator_graded_rag.configs import DenseStage


class WeightsMismatch(RuntimeError):
    """Weights that are not the ones the config pins: another file, or a model loaded at
    another precision."""


class WeightsMissing(RuntimeError):
    """Weights that are not downloaded, where no download was asked for."""


def require_sha256(path: Path, sha256: str) -> Path:
    """The path, refused unless the file's SHA-256 is the pinned one."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(1 << 20):
            digest.update(block)
    if digest.hexdigest() != sha256:
        raise WeightsMismatch(
            f"{path.name} has SHA-256 {digest.hexdigest()}, not the pinned {sha256}"
        )
    return path


def verified_file(
    repo: str, revision: str, filename: str, sha256: str, *, offline: bool = True
) -> Path:
    """The file at the revision, refused unless it is the pinned one. Offline, the
    default, only the Hugging Face cache is read and a missing file is refused; with
    offline False, a missing file is downloaded from the Hub."""
    from huggingface_hub import hf_hub_download

    if offline and cached_file(repo, revision, filename) is None:
        raise WeightsMissing(
            f"{repo}/{filename} at {revision} is not downloaded: run the embed command"
            " with --download"
        )
    found = hf_hub_download(
        repo_id=repo, filename=filename, revision=revision, local_files_only=offline
    )
    return require_sha256(Path(found), sha256)


def cached_file(repo: str, revision: str, filename: str) -> Path | None:
    """The file if the Hugging Face cache holds it at the revision; nothing is
    downloaded."""
    from huggingface_hub import try_to_load_from_cache

    found = try_to_load_from_cache(repo_id=repo, filename=filename, revision=revision)
    return Path(found) if isinstance(found, str) else None


class SentenceTransformerEncoder:
    """A dense stage's model through sentence-transformers, in the precision its config
    states, which is checked once the model is loaded. Vectors come back L2-normalized;
    texts longer than the stage's max_length are cut to it."""

    def __init__(self, stage: DenseStage, *, offline: bool = True) -> None:
        verified_file(
            stage.model,
            stage.revision,
            "model.safetensors",
            stage.weights_sha256,
            offline=offline,
        )
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            stage.model,
            revision=stage.revision,
            trust_remote_code=False,
            local_files_only=offline,
            model_kwargs={"use_safetensors": True, "dtype": stage.dtype},
        )
        # The run record names the config's dtype, so a library that ignored it would
        # leave a record that is wrong; torch names a dtype "torch.float32".
        loaded = str(self._model.dtype).removeprefix("torch.")
        if loaded != stage.dtype:
            raise WeightsMismatch(
                f"{stage.model} loaded in {loaded}, not the config's {stage.dtype}"
            )
        self._model.max_seq_length = stage.max_length
        self.dim = int(self._model.get_embedding_dimension())

    def runtime(self) -> dict[str, str]:
        """The GPU, or "cpu", and torch's and CUDA's versions the model runs on."""
        import torch

        device = self._model.device
        gpu = torch.cuda.get_device_name(device) if device.type == "cuda" else "cpu"
        return {
            "gpu": str(gpu),
            "torch": str(torch.__version__),
            "cuda": str(torch.version.cuda or "none"),
        }

    def _encode(self, texts: Sequence[str], prompt: str) -> list[list[float]]:
        vectors = self._model.encode(
            list(texts),
            prompt=prompt or None,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(x) for x in row] for row in vectors]

    def queries(self, texts: Sequence[str], prompt: str) -> list[list[float]]:
        return self._encode(texts, prompt)

    def passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(texts, "")

    def too_long(self, texts: Sequence[str]) -> int:
        """How many texts hold more tokens than the model reads."""
        tokenized = self._model.tokenizer(
            list(texts), add_special_tokens=True, truncation=False
        )
        limit = self._model.max_seq_length
        return sum(len(ids) > limit for ids in tokenized["input_ids"])
