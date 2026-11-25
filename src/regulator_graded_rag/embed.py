# Author: Nicola Antonello
"""Compute a dense config's passage vectors once, and load them for exact search
(ADR-0009).

Usage: uv run --group models --env-file .env python -m regulator_graded_rag.embed
--config PATH, from the repository root.

For each dense first stage of the config, the vectors file indexes/vectors/<model
key>.f32 is computed when it is missing, from the index's passages in ordinal order, with
a progress counter, and its header records how many passages hold more tokens than the
model reads. The file is then loaded into pgvector, which refuses one that does not
match. A file made with another max_length is never reused, since the file is named by
model and revision alone.
Exit code 0 when every dense stage's vectors are loaded, 1 when they cannot be.
"""

import argparse
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from psycopg import sql

from regulator_graded_rag.bm25 import Conn
from regulator_graded_rag.configs import DenseStage, load_config
from regulator_graded_rag.db import connect, database_url
from regulator_graded_rag.embeddings import (
    VECTORS,
    Encoder,
    load_vectors,
    model_key,
    read_header,
    write_vectors,
)
from regulator_graded_rag.index import SCHEMA, indexed_version
from regulator_graded_rag.manifest import DEFAULT_MANIFEST, load_manifest
from regulator_graded_rag.models import SentenceTransformerEncoder, WeightsMismatch

VECTOR_DIR = Path("indexes/vectors")
BATCH = 256


def embed_stage(
    conn: Conn,
    stage: DenseStage,
    encoder: Encoder,
    *,
    corpus_version: str,
    folder: Path = VECTOR_DIR,
    schema: str = VECTORS,
    index_schema: str = SCHEMA,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Compute the stage's vectors file when it is missing, then load it; the file's
    path. progress hears how many passages are done, and how many there are."""
    path = folder / f"{model_key(stage.model, stage.revision)}.f32"
    if path.exists():
        made_with = read_header(path).get("max_length")
        if made_with != stage.max_length:
            raise ValueError(
                f"{path.as_posix()} was made with max_length {made_with}, not"
                f" {stage.max_length}: delete it to compute it again"
            )
    else:
        indexed = indexed_version(conn, index_schema)
        if indexed != corpus_version:
            raise ValueError(
                f"the index holds corpus version {indexed}, not {corpus_version}:"
                ' run "uv run python -m regulator_graded_rag.index" first'
            )
        query = sql.SQL("SELECT text FROM {s}.passages ORDER BY ordinal")
        found = conn.execute(query.format(s=sql.Identifier(index_schema)))
        texts: Sequence[str] = [text for (text,) in found.fetchall()]
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH):
            vectors.extend(encoder.passages(texts[start : start + BATCH]))
            if progress is not None:
                progress(len(vectors), len(texts))
        header = {
            "model": stage.model,
            "revision": stage.revision,
            "corpus_version": corpus_version,
            "max_length": stage.max_length,
            "truncated": encoder.too_long(texts),
        }
        write_vectors(path, vectors, header)
    load_vectors(
        conn,
        path,
        model=stage.model,
        revision=stage.revision,
        corpus_version=corpus_version,
        schema=schema,
        index_schema=index_schema,
    )
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m regulator_graded_rag.embed",
        description="Compute a dense config's passage vectors once, and load them.",
    )
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except (OSError, ValueError) as err:
        print(err)
        return 1
    stages = [stage for stage in config.first if isinstance(stage, DenseStage)]
    if not stages:
        print(f"{args.config.as_posix()} has no dense stage to embed passages for")
        return 1
    try:
        manifest = load_manifest(DEFAULT_MANIFEST)
        url = database_url()
    except (RuntimeError, ValueError) as err:
        print(err)
        return 1
    start = time.monotonic()

    def show(done: int, total: int) -> None:
        elapsed = int(time.monotonic() - start)
        clock = f"{elapsed // 3600:02}:{elapsed // 60 % 60:02}:{elapsed % 60:02}"
        print(f"[{done}/{total} {clock}] passages", flush=True)

    with connect(url) as conn:
        for stage in stages:
            try:
                encoder = SentenceTransformerEncoder(stage)
                path = embed_stage(
                    conn,
                    stage,
                    encoder,
                    corpus_version=str(manifest.version),
                    progress=show,
                )
            except ImportError:
                print('the models group is not installed: run "uv sync --group models"')
                return 1
            except (ValueError, WeightsMismatch) as err:
                print(err)
                return 1
            header = read_header(path)
            print(
                f"{stage.model}: {header['count']} passages loaded,"
                f" {header['truncated']} longer than {stage.max_length} tokens,"
                f" SHA-256 {header['sha256']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
