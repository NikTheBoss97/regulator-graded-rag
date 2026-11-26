# Author: Nicola Antonello
import math
import os
from dataclasses import replace

import pytest

from regulator_graded_rag.configs import DenseStage

BGE = DenseStage(
    "BAAI/bge-base-en-v1.5",
    "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a",
    "c7c1988aae201f80cf91a5dbbd5866409503b89dcaba877ca6dba7dd0a5167d7",
    "Represent this sentence for searching relevant passages: ",
    512,
)
# Stored in 16 bits, unlike bge-base, so it shows whether the config's dtype is used.
GTE = DenseStage(
    "Alibaba-NLP/gte-modernbert-base",
    "e7f32e3c00f91d699e8c43b53106206bcc72bb22",
    "3e85899d5728cb7de79781c0c3acfb91ccef9f875f1f7e0b3c9f3dd4b6a724ba",
    "",
    8192,
)


def cached(stage: DenseStage) -> None:
    """Skip unless asked for with RGR_MODEL_SMOKE=1, since loading a model takes about a
    minute, and unless the models group is installed and the stage's weights are
    already cached: these tests never download, so the gates stay offline."""
    if os.environ.get("RGR_MODEL_SMOKE") != "1":
        pytest.skip("set RGR_MODEL_SMOKE=1 to run the real model")
    pytest.importorskip("sentence_transformers")
    from regulator_graded_rag.models import cached_file

    if cached_file(stage.model, stage.revision, "model.safetensors") is None:
        pytest.skip(f"{stage.model}'s weights are not in the Hugging Face cache")


def test_models_smoke() -> None:
    cached(BGE)
    from regulator_graded_rag.models import SentenceTransformerEncoder

    encoder = SentenceTransformerEncoder(BGE, offline=True)
    passages = encoder.passages(
        [
            "Lithium batteries must be protected against short circuits.",
            "A placard is required on each side of a cargo tank.",
        ]
    )
    [query] = encoder.queries(
        ["Must a lithium battery be protected?"], BGE.query_prompt
    )
    assert encoder.dim == 768 and all(len(v) == 768 for v in [*passages, query])
    assert all(
        math.isclose(math.fsum(x * x for x in v), 1.0, rel_tol=1e-5)
        for v in [*passages, query]
    )
    # The question about batteries is nearer the battery passage.
    near, far = (math.fsum(q * p for q, p in zip(query, v)) for v in passages)
    assert near > far
    # The prompt reaches the model: without it the question embeds differently.
    assert encoder.queries(["Must a lithium battery be protected?"], "") != [query]
    # The run record names the libraries and the GPU the model ran on.
    runtime = encoder.runtime()
    assert runtime["torch"].startswith("2.14.1") and runtime["gpu"]


def test_a_16_bit_model_loads_in_the_precision_its_config_states() -> None:
    cached(GTE)
    from regulator_graded_rag.models import SentenceTransformerEncoder

    # The encoder refuses a model that did not load in the config's dtype, so building
    # it is the check; the dtype is read as well, in case that refusal is ever lost.
    for dtype in ("float32", "float16"):
        encoder = SentenceTransformerEncoder(replace(GTE, dtype=dtype), offline=True)
        assert str(encoder._model.dtype) == f"torch.{dtype}"


def test_cached_weights_with_another_checksum_are_refused() -> None:
    cached(BGE)
    from regulator_graded_rag.models import WeightsMismatch, verified_file

    with pytest.raises(WeightsMismatch, match="not the pinned"):
        verified_file(
            BGE.model, BGE.revision, "model.safetensors", "0" * 64, offline=True
        )
