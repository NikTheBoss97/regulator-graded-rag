# Author: Nicola Antonello
"""Group the letters that must fall on the same side of the split (ADR-0018).

Two letters link when the Jaccard similarity of their 5-word shingles is at least 0.5,
once every shingle found in more than a fifth of the letters is removed as the frame they
all share (salutation, standard opening, closing, signature), or when one cites the
other's reference number. Groups are the connected components of the links. Nobody reads
a letter before the split, so report() gives counts only, and a group of more than 20
letters stops the split for the owner.
"""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

SHINGLE_WORDS = 5
FRAME_SHARE = 0.2
LINK_AT = 0.5
MAX_GROUP = 20
# A reference number such as 18-0123 that is not part of a longer token, so a docket
# number (PHMSA-2016-0123) or a ZIP+4 code (20590-0001) is not one.
REFERENCE = re.compile(r"(?<![\w-])(\d{2}-\d{4})(?![\w-])")


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def shingles(text: str) -> frozenset[str]:
    """Every run of SHINGLE_WORDS consecutive words; a shorter text gives one shingle."""
    found = words(text)
    if len(found) < SHINGLE_WORDS:
        return frozenset({" ".join(found)}) if found else frozenset()
    last = len(found) - SHINGLE_WORDS + 1
    return frozenset(" ".join(found[i : i + SHINGLE_WORDS]) for i in range(last))


def frame(
    sets: Mapping[str, frozenset[str]], share: float = FRAME_SHARE
) -> frozenset[str]:
    """The shingles found in more than share of the letters: the frame they all share."""
    counts = Counter(s for found in sets.values() for s in found)
    return frozenset(s for s, n in counts.items() if n > share * len(sets))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    common = len(a & b)
    return common / (len(a) + len(b) - common)


def cited(text: str, own: str, pool: AbstractSet[str]) -> set[str]:
    """The pool's reference numbers the text cites, other than its own."""
    return {n for n in REFERENCE.findall(text) if n in pool and n != own}


@dataclass(frozen=True)
class Grouping:
    groups: tuple[tuple[str, ...], ...]  # each sorted, and sorted by first letter
    text_links: int
    citation_links: int
    best: Mapping[
        str, float
    ]  # each letter with text: its highest similarity to another
    without_text: int


def group_letters(
    texts: Mapping[str, str | None],
    pool: Sequence[str],
    *,
    frame_share: float = FRAME_SHARE,
) -> Grouping:
    """Link the letters by shingle overlap and by citation, and group the links.

    A letter whose text is None links only through citations.
    """
    sets = {k: shingles(v) for k, v in texts.items() if v is not None}
    shared = frame(sets, frame_share)
    sets = {k: v - shared for k, v in sets.items()}
    parent = {k: k for k in [*pool, *texts]}

    def root(k: str) -> str:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    ids = sorted(sets)
    best = dict.fromkeys(ids, 0.0)
    text_links = 0
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            similarity = jaccard(sets[a], sets[b])
            best[a] = max(best[a], similarity)
            best[b] = max(best[b], similarity)
            if similarity >= LINK_AT:
                text_links += 1
                parent[root(a)] = root(b)
    members = set(parent)
    citations = {
        (min(k, c), max(k, c))
        for k, v in texts.items()
        if v is not None
        for c in cited(v, k, members)
    }
    for a, b in citations:
        parent[root(a)] = root(b)
    components: dict[str, list[str]] = {}
    for k in parent:
        components.setdefault(root(k), []).append(k)
    return Grouping(
        tuple(sorted(tuple(sorted(c)) for c in components.values())),
        text_links,
        len(citations),
        best,
        sum(1 for k in parent if texts.get(k) is None),
    )


def report(g: Grouping) -> list[str]:
    """Counts only: letters, links, how similar each letter's closest letter is, groups."""
    bins = Counter(min(int(s * 10), 9) for s in g.best.values())
    sizes = Counter(len(group) for group in g.groups)
    return [
        f"letters: {sum(sizes[n] * n for n in sizes)} ({g.without_text} without text)",
        f"links: {g.text_links} by text, {g.citation_links} by citation",
        *(
            f"best similarity {i / 10:.1f}–{(i + 1) / 10:.1f}: {bins[i]}"
            for i in range(10)
        ),
        f"groups: {len(g.groups)}; sizes: "
        + ", ".join(f"{n} ×{count}" for n, count in sorted(sizes.items())),
        f"largest group: {max(sizes, default=0)} letters",
    ]


class GroupTooLarge(ValueError):
    """A group holds more letters than the limit, so the owner looks at it first."""


def check_sizes(g: Grouping, limit: int = MAX_GROUP) -> None:
    size = max((len(group) for group in g.groups), default=0)
    if size > limit:
        raise GroupTooLarge(
            f"the largest group holds {size} letters; the limit is {limit}:"
            " bring it to the owner"
        )
