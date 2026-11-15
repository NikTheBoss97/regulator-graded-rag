# Author: Nicola Antonello
import hashlib
from pathlib import Path

import pytest

from regulator_graded_rag import letters
from regulator_graded_rag.letters import Letter, write_letters
from regulator_graded_rag.split import (
    Assigned,
    assign,
    draw_key,
    heldout_count,
    load_split,
    main,
    write_split,
)
from tests.unit.test_letter_page import ARTICLE

YEAR_2017 = [
    ("17-0001",),
    ("17-0002", "17-0009"),
    ("17-0003",),
    ("17-0004",),
    ("17-0005",),
]
YEAR_2020 = [
    ("20-0003",),
    ("20-0018", "20-0040"),
    ("20-0050",),
    ("20-0060",),
    ("20-0070",),
]


def heldout(rows: list[Assigned]) -> list[str]:
    return [r.letter for r in rows if r.split == "heldout"]


def test_draw_keys_are_fixed_sha256_values() -> None:
    assert (
        draw_key("seed", "17-0001")
        == "2450f286eeecc48824498e04b53788de13bd7123bcccc7a47e9e3f7ad555c570"
    )


def test_forty_percent_of_a_years_groups_rounded_half_up() -> None:
    assert [heldout_count(n) for n in (0, 1, 2, 3, 4, 5, 10, 118)] == [
        0,
        0,
        1,
        1,
        2,
        2,
        4,
        47,
    ]


def test_the_draw_takes_the_lowest_keys_and_keeps_groups_together() -> None:
    assert heldout(assign(YEAR_2017, seed="s")) == ["17-0002", "17-0004", "17-0009"]


def test_letters_already_read_go_to_dev_and_the_year_still_sends_forty_percent() -> (
    None
):
    rows = assign(YEAR_2020, seed="s")
    assert heldout(rows) == ["20-0060", "20-0070"]
    assert {r.letter: r.split for r in rows}["20-0040"] == "dev"


def test_another_seed_gives_another_split() -> None:
    assert heldout(assign(YEAR_2017, seed="t")) == ["17-0001", "17-0002", "17-0009"]


def test_the_draw_ignores_input_order() -> None:
    assert assign(YEAR_2017[::-1] + YEAR_2020, seed="s") == assign(
        YEAR_2020 + YEAR_2017, seed="s"
    )


def test_a_groups_year_is_its_lowest_numbered_letters() -> None:
    rows = assign([("17-0005", "18-0001")], seed="s")
    assert [(r.letter, r.year, r.group) for r in rows] == [
        ("17-0005", 2017, "17-0005"),
        ("18-0001", 2017, "17-0005"),
    ]


def test_the_split_file_round_trips_with_lf(tmp_path: Path) -> None:
    rows = assign(YEAR_2017, seed="s")
    write_split(tmp_path / "split.jsonl", rows)
    assert b"\r" not in (tmp_path / "split.jsonl").read_bytes()
    assert load_split(tmp_path / "split.jsonl") == {r.letter: r.split for r in rows}


def test_a_draw_moves_every_letter_into_its_split(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("UNSPLIT", "DEV_LETTERS", "HELDOUT_LETTERS"):
        monkeypatch.setattr(letters, name, tmp_path / name.lower())
    (tmp_path / "unsplit").mkdir()
    rows = []
    for i in range(1, 6):
        body = " ".join(f"w{i}x{j}" for j in range(40))
        data = ARTICLE.replace("A1. Yes. See &sect;&#8201;171.1.", body).encode()
        (tmp_path / "unsplit" / f"17-000{i}.html").write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        url = f"https://www.phmsa.dot.gov/regulations/title49/interp/17-000{i}"
        rows.append(
            Letter(
                f"17-000{i}", 2017, "20260101000000", url, "article", len(data), digest
            )
        )
    write_letters(tmp_path / "letters.jsonl", rows)
    args = [
        "--letters",
        str(tmp_path / "letters.jsonl"),
        "--split",
        str(tmp_path / "split.jsonl"),
    ]

    assert main([*args, "--dry-run"]) == 0
    dry = capsys.readouterr().out
    assert (
        not (tmp_path / "split.jsonl").exists()
        and len(list((tmp_path / "unsplit").iterdir())) == 5
    )
    assert main(args) == 0
    digest_line = next(x for x in dry.splitlines() if x.startswith("assignment digest"))
    assert digest_line in capsys.readouterr().out
    splits = load_split(tmp_path / "split.jsonl")
    assert sorted(splits.values()) == ["dev", "dev", "dev", "heldout", "heldout"]
    for letter_id, side in splits.items():
        assert (tmp_path / f"{side}_letters" / f"{letter_id}.html").is_file()
    assert not (tmp_path / "unsplit").exists()


def test_the_split_is_drawn_once(tmp_path: Path) -> None:
    (tmp_path / "split.jsonl").write_text("{}\n", encoding="utf-8")
    assert (
        main(
            [
                "--split",
                str(tmp_path / "split.jsonl"),
                "--letters",
                str(tmp_path / "letters.jsonl"),
            ]
        )
        == 2
    )
