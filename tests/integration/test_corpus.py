# Author: Nicola Antonello
from pathlib import Path

from regulator_graded_rag.manifest import Manifest


def test_the_corpus_is_parts_171_to_180_of_the_2025_edition(
    manifest: Manifest, corpus_dir: Path
) -> None:
    assert [f.name for f in manifest.files] == [
        f"CFR-2025-title49-vol{2 if part <= 177 else 3}-part{part}.xml"
        for part in range(171, 181)
    ]
    assert (
        sum((corpus_dir / f.name).stat().st_size for f in manifest.files) == 9_266_626
    )
