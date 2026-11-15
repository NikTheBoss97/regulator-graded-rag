# Author: Nicola Antonello
import pytest

from regulator_graded_rag.groups import (
    GroupTooLarge,
    check_sizes,
    cited,
    frame,
    group_letters,
    jaccard,
    report,
    shingles,
)

# Invented text shaped like a letter's frame and body; no real letter.
FRAME = "This letter responds to your request for clarification of the Hazardous Materials Regulations."


def body(i: int) -> str:
    return " ".join(f"w{i}x{j}" for j in range(40))


def test_shingles_are_five_lowercase_words() -> None:
    assert shingles("The HMR apply to each Person who offers") == {
        "the hmr apply to each",
        "hmr apply to each person",
        "apply to each person who",
        "to each person who offers",
    }
    assert shingles("Yes, it does.") == {"yes it does"} and shingles("") == frozenset()


def test_the_frame_is_what_more_than_a_fifth_share() -> None:
    sets = {k: frozenset({"f", k}) for k in "abcde"} | {"z": frozenset({"z"})}
    assert frame(sets, share=0.5) == {"f"}


def test_jaccard() -> None:
    assert jaccard(frozenset("abc"), frozenset("bcd")) == 0.5
    assert jaccard(frozenset(), frozenset()) == 0.0


def test_copies_link_and_letters_sharing_only_the_frame_do_not() -> None:
    texts = {f"17-{i:04d}": f"{FRAME} {body(i)}" for i in range(1, 20)}
    texts["17-0020"] = f"{FRAME} {body(1)} Sincerely."
    g = group_letters(texts, sorted(texts))
    assert (
        ("17-0001", "17-0020") in g.groups and len(g.groups) == 19 and g.text_links == 1
    )


def test_letters_left_empty_by_the_frame_link_nothing() -> None:
    texts = {f"17-{i:04d}": FRAME for i in range(1, 6)}
    assert len(group_letters(texts, sorted(texts)).groups) == 5


def test_citations_ignore_itself_and_unknown_numbers() -> None:
    text = "See Ref. No. 18-0123 and 19-0042; docket PHMSA-2016-0123; ZIP 20590-0001; § 178.337-10; our 20-0003."
    assert cited(text, own="20-0003", pool={"18-0123", "20-0003"}) == {"18-0123"}


def test_a_citation_joins_a_letter_without_text() -> None:
    g = group_letters(
        {"17-0001": f"{FRAME} {body(1)} as in 18-0002.", "18-0002": None},
        ["17-0001", "18-0002"],
    )
    assert (
        g.groups == (("17-0001", "18-0002"),)
        and g.citation_links == 1
        and g.without_text == 1
    )


def test_groups_chain_through_their_links() -> None:
    texts = {
        "17-0001": f"{FRAME} {body(1)}",
        "17-0002": f"{FRAME} {body(1)} see 17-0003",
        "17-0003": f"{FRAME} {body(3)}",
    }
    g = group_letters(texts, sorted(texts), frame_share=1.0)
    assert g.groups == (("17-0001", "17-0002", "17-0003"),) and (
        g.text_links,
        g.citation_links,
    ) == (1, 1)


def test_a_group_over_the_limit_stops() -> None:
    texts = {
        f"17-{i:04d}": f"{FRAME} {body(i)} see 17-{i + 1:04d}" for i in range(1, 22)
    }
    with pytest.raises(GroupTooLarge, match="21 letters; the limit is 20"):
        check_sizes(group_letters(texts, sorted(texts)))


def test_the_report_holds_counts_only() -> None:
    texts = {
        "17-0001": f"{FRAME} secretword {body(1)}",
        "17-0002": f"{FRAME} {body(2)}",
    }
    lines = report(group_letters(texts, sorted(texts)))
    assert lines[0] == "letters: 2 (0 without text)" and not any(
        "secretword" in line for line in lines
    )
