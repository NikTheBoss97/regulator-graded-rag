# Author: Nicola Antonello
import math
import os

import pytest

from regulator_graded_rag.configs import DenseStage

BGE = DenseStage(
    "BAAI/bge-base-en-v1.5",
    "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a",
    "c7c1988aae201f80cf91a5dbbd5866409503b89dcaba877ca6dba7dd0a5167d7",
    "Represent this sentence for searching relevant passages: ",
    512,
)


def cached_bge() -> None:
    """Skip unless asked for with RGR_MODEL_SMOKE=1, since loading the model takes about
    a minute, and unless the models group is installed and bge-base's weights are
    already cached: this test never downloads, so the gates stay offline."""
    if os.environ.get("RGR_MODEL_SMOKE") != "1":
        pytest.skip("set RGR_MODEL_SMOKE=1 to run the real model")
    pytest.importorskip("sentence_transformers")
    from regulator_graded_rag.models import cached_file

    if cached_file(BGE.model, BGE.revision, "model.safetensors") is None:
        pytest.skip("bge-base's weights are not in the Hugging Face cache")


def test_models_smoke() -> None:
    cached_bge()
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


def test_cached_weights_with_another_checksum_are_refused() -> None:
    cached_bge()
    from regulator_graded_rag.models import WeightsMismatch, verified_file

    with pytest.raises(WeightsMismatch, match="not the pinned"):
        verified_file(
            BGE.model, BGE.revision, "model.safetensors", "0" * 64, offline=True
        )
