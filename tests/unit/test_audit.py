# Author: Nicola Antonello
import random
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from regulator_graded_rag import audit
from regulator_graded_rag.audit import (
    Audit,
    changed,
    describe,
    draw,
    draw_sample,
    load_audit,
    upper_bound,
    write_audit,
)
from regulator_graded_rag.checks import CHECKS
from regulator_graded_rag.drafts import Draft
from regulator_graded_rag.letter_page import LetterPage
from regulator_graded_rag.split import SEED, draw_key

QUESTION = "Is it the case that the marking must be durable?"
ANSWER = (
    "The answer is yes. The marking must be durable in accordance with § 172.401(a)(2)."
    " The mark stays on the package."
)
OPENING = (
    "This letter is in response to your email requesting clarification of the"
    " Hazardous Materials Regulations (HMR; 49 CFR Parts 171-180)."
)
PAGE = LetterPage(
    "article",
    None,
    "",
    "",
    ("June 1, 2020", "Dear Ms. Doe:", OPENING, f"Q1. {QUESTION}", f"A1. {ANSWER}"),
)
DRAFT = Draft(
    id="99-0001-Q1",
    letter="99-0001",
    number=1,
    numbered=True,
    question=QUESTION,
    rewritten=True,
    answer="yes",
    evidence=("172.401(a)(2)",),
    outside=(),
    type="lookup",
    letter_date="2020-06-01",
    date_source="letter",
    source="https://example.com/99-0001",
    split="dev",
    drift={"172.401(a)(2)": "unchanged"},
    kept=True,
    flags=(),
)


def ids(n: int) -> list[str]:
    return [f"99-{i:04d}-Q1" for i in range(n)]


def test_the_draw_takes_the_lowest_keys_whatever_the_order() -> None:
    pool = ids(100)
    shuffled = list(pool)
    random.Random(1).shuffle(shuffled)
    expected = set(sorted(pool, key=lambda i: draw_key(SEED, f"audit:{i}"))[:40])
    assert set(draw_sample(pool)) == expected
    assert draw_sample(pool) == draw_sample(shuffled)
    assert len(draw_sample(pool)) == 40


def test_a_small_pool_is_audited_whole() -> None:
    assert draw_sample(ids(30)) == tuple(sorted(ids(30)))


@pytest.mark.parametrize(
    ("pool", "sampled", "n_changed", "bound"),
    [
        (93, 40, 0, 5),
        (93, 40, 1, 8),
        (90, 40, 0, 4),
        (90, 40, 1, 8),
        (85, 40, 0, 4),
        (40, 40, 0, 0),
    ],
)
def test_the_bound_for_a_finite_pool(
    pool: int, sampled: int, n_changed: int, bound: int
) -> None:
    assert upper_bound(pool, sampled, n_changed) == bound


def test_changes_count_edits_and_rejects_of_the_sample_only() -> None:
    sample = ("a", "b", "c", "d")
    drawn = Audit("dev", CHECKS, "2026-11-21", ("a", "b", "c", "d", "e"), sample)
    actions = {"a": "approve", "b": "read", "c": "edit", "d": "reject", "e": "edit"}
    assert changed(drawn, actions) == 2
    assert changed(drawn, {"a": "approve", "b": "read", "e": "edit"}) == 0


def test_the_pool_is_the_undecided_drafts_with_no_reason() -> None:
    flagged = replace(DRAFT, id="99-0002-Q1", flags=("picture",))
    lost = replace(DRAFT, id="99-0003-Q1", letter="99-0003")
    clean = replace(DRAFT, id="99-0004-Q1")

    def page(draft: Draft) -> LetterPage | None:
        return None if draft.letter == "99-0003" else PAGE

    result = draw([DRAFT, flagged, lost, clean], page, "dev", date(2026, 11, 21))
    assert result.pool == ("99-0001-Q1", "99-0004-Q1")
    assert result.sample == result.pool
    assert result.checks == CHECKS
    assert result.drawn == "2026-11-21"
    assert result.split == "dev"


def test_an_audit_reads_back_and_is_drawn_once(tmp_path: Path) -> None:
    path = tmp_path / "eval" / "dev" / "audit.json"
    drawn = Audit("dev", CHECKS, "2026-11-21", ("a", "b", "c"), ("a", "c"))
    write_audit(path, drawn)
    assert load_audit(path) == drawn
    assert b"\r" not in path.read_bytes()
    with pytest.raises(FileExistsError):
        write_audit(path, drawn)
    assert not path.with_name("audit.json.part").exists()


def test_a_second_draw_is_refused_and_leaves_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "eval" / "dev" / "audit.json"
    write_audit(path, Audit("dev", CHECKS, "2026-11-21", ("a",), ("a",)))
    before = path.read_bytes()
    assert audit.main(["--split", "dev", "--draw"]) == 1
    assert path.read_bytes() == before


def test_a_draw_needs_the_unanswerable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert audit.main(["--split", "dev", "--draw"]) == 1
    assert not (tmp_path / "eval" / "dev" / "audit.json").exists()


def test_a_held_out_draw_needs_the_owners_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert audit.main(["--split", "heldout", "--draw"]) == 2


def test_describe_states_the_bound_three_ways() -> None:
    pool = tuple(ids(93))
    drawn = Audit("dev", CHECKS, "2026-11-21", pool, draw_sample(pool))
    assert describe(drawn, {}, 53, 259) == (
        "audit: 0 of 40 sampled drafts changed; at most 5 of the 53 items only code"
        " verified would have been changed (95%): 9.4% of them, 1.9% of the 259 items"
    )
    small = Audit("dev", CHECKS, "2026-11-21", tuple(ids(30)), draw_sample(ids(30)))
    assert describe(small, {}, 0, 100) == (
        "audit: the owner checked the whole pool of 30"
    )


def test_describe_after_two_changes() -> None:
    pool = tuple(ids(93))
    drawn = Audit("dev", CHECKS, "2026-11-21", pool, draw_sample(pool))
    actions = {drawn.sample[0]: "edit", drawn.sample[1]: "reject"}
    assert describe(drawn, actions, 0, 200) == (
        "audit: 2 of 40 sampled drafts changed, so the owner checked the whole pool"
        " of 93"
    )


def test_describe_with_nothing_left_to_code_alone() -> None:
    pool = tuple(ids(93))
    drawn = Audit("dev", CHECKS, "2026-11-21", pool, draw_sample(pool))
    assert describe(drawn, {}, 0, 200) == (
        "audit: 0 of 40 sampled drafts changed; no item rests on code's checks alone"
    )
