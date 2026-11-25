# Author: Nicola Antonello
import hashlib
import json
import struct
from pathlib import Path

import pytest

from regulator_graded_rag.embeddings import (
    model_key,
    read_header,
    read_vectors,
    write_vectors,
)

# Values float32 holds exactly, so the round trip can be compared exactly.
ROWS = [[0.5, -0.25, 1.0], [0.0, 0.125, -1.0]]
HEADER = {"model": "m", "revision": "r", "corpus_version": "c" * 64, "truncated": 0}


def test_vectors_round_trip_with_their_checksum(tmp_path: Path) -> None:
    path = tmp_path / "v.f32"
    sha256 = write_vectors(path, ROWS, HEADER)
    raw = path.read_bytes()
    # Raw little-endian float32, one row after another: no pickle, no numpy.
    assert raw == struct.pack("<6f", *ROWS[0], *ROWS[1])
    assert sha256 == hashlib.sha256(raw).hexdigest()
    header = read_header(path)
    assert header == {**HEADER, "count": 2, "dim": 3, "sha256": sha256}
    assert read_vectors(path) == (header, ROWS)


def test_a_changed_byte_or_a_wrong_count_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "v.f32"
    write_vectors(path, ROWS, HEADER)
    raw = bytearray(path.read_bytes())
    raw[5] ^= 0x01
    path.write_bytes(bytes(raw))
    with pytest.raises(ValueError, match="SHA-256"):
        read_vectors(path)
    write_vectors(path, ROWS, HEADER)
    sidecar = tmp_path / "v.f32.json"
    header = json.loads(sidecar.read_text(encoding="utf-8"))
    sidecar.write_text(json.dumps(header | {"count": 3}), encoding="utf-8")
    with pytest.raises(ValueError, match="3 rows"):
        read_vectors(path)


def test_vectors_of_mixed_dimensions_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="dimension"):
        write_vectors(tmp_path / "v.f32", [[1.0, 0.0], [1.0]], HEADER)
    with pytest.raises(ValueError, match="dimension"):
        write_vectors(tmp_path / "v.f32", [], HEADER)


def test_model_key_is_a_safe_identifier() -> None:
    key = model_key("BAAI/bge-base-en-v1.5", "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a")
    assert key == "baai_bge_base_en_v1_5_a5beb1e3"
