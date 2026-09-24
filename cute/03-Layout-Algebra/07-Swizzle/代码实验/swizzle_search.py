#!/usr/bin/env python3
"""Search CuTe-style Swizzle<B, M, S> candidates.

Addresses passed to this module are element indices.  ``element_bytes`` turns
them into byte addresses before shared-memory bank mapping is evaluated.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Access:
    """One lane's contiguous shared-memory access."""

    element_index: int
    access_bytes: int


@dataclass(frozen=True)
class AccessGroup:
    """Accesses participating in one bank-arbitration group."""

    accesses: tuple[Access, ...]
    name: str = ""


@dataclass(frozen=True, order=True)
class SearchResult:
    """One candidate, ordered by score and then implementation complexity."""

    conflicts: int
    bits: int
    shift_magnitude: int
    base: int
    shift: int

    def __str__(self) -> str:
        return (
            f"Swizzle<{self.bits},{self.base},{self.shift}>: "
            f"conflicts={self.conflicts}"
        )


def apply_swizzle(index: int, bits: int, base: int, shift: int) -> int:
    """Apply the bit transformation used by ``cute::Swizzle<B, M, S>``."""
    if index < 0:
        raise ValueError("index must be non-negative")
    if bits < 0:
        raise ValueError("bits must be non-negative")
    if base < 0:
        raise ValueError("base must be non-negative")
    if bits == 0:
        return index
    if shift == 0 or abs(shift) < bits:
        raise ValueError("shift must be non-zero and abs(shift) >= bits")

    bit_mask = (1 << bits) - 1
    source_bit = base + max(shift, 0)
    destination_bit = base + max(-shift, 0)
    source_value = (index >> source_bit) & bit_mask
    return index ^ (source_value << destination_bit)


def is_domain_permutation(
    domain_size: int,
    bits: int,
    base: int,
    shift: int,
) -> bool:
    """Return whether the swizzle maps ``[0, domain_size)`` onto itself."""
    if domain_size <= 0:
        raise ValueError("domain_size must be positive")

    outputs = {
        apply_swizzle(index, bits, base, shift)
        for index in range(domain_size)
    }
    return outputs == set(range(domain_size))


def count_group_conflicts(
    group: AccessGroup,
    bits: int,
    base: int,
    shift: int,
    *,
    element_bytes: int,
    bank_count: int = 32,
    bank_bytes: int = 4,
) -> int:
    """Count conflicts using distinct words requested from each bank.

    Multiple reads of the same word are treated as a broadcast and therefore
    do not add a conflict.
    """
    if element_bytes <= 0:
        raise ValueError("element_bytes must be positive")
    if bank_count <= 0 or bank_bytes <= 0:
        raise ValueError("bank geometry must be positive")

    words_by_bank: dict[int, set[int]] = defaultdict(set)

    for access in group.accesses:
        if access.access_bytes <= 0:
            raise ValueError("access_bytes must be positive")

        swizzled_index = apply_swizzle(
            access.element_index,
            bits,
            base,
            shift,
        )
        first_byte = swizzled_index * element_bytes
        last_byte = first_byte + access.access_bytes - 1
        first_word = first_byte // bank_bytes
        last_word = last_byte // bank_bytes

        for word in range(first_word, last_word + 1):
            words_by_bank[word % bank_count].add(word)

    return sum(
        max(0, len(words) - 1)
        for words in words_by_bank.values()
    )


def _alignment_is_valid(
    groups: Sequence[AccessGroup],
    bits: int,
    base: int,
    shift: int,
    *,
    element_bytes: int,
    required_alignment_bytes: int,
) -> bool:
    for group in groups:
        for access in group.accesses:
            index = apply_swizzle(
                access.element_index,
                bits,
                base,
                shift,
            )
            if index * element_bytes % required_alignment_bytes != 0:
                return False
    return True


def search_swizzles(
    groups: Iterable[AccessGroup],
    *,
    element_bytes: int,
    domain_size: int | None = None,
    required_alignment_bytes: int | None = None,
    max_bits: int = 5,
    max_base: int = 8,
    max_shift: int = 12,
) -> list[SearchResult]:
    """Enumerate legal candidates and return them from best to worst."""
    materialized_groups = tuple(groups)
    if not materialized_groups:
        raise ValueError("at least one access group is required")
    if element_bytes <= 0:
        raise ValueError("element_bytes must be positive")
    if min(max_bits, max_base, max_shift) < 0:
        raise ValueError("search bounds must be non-negative")
    if required_alignment_bytes is not None:
        if required_alignment_bytes <= 0:
            raise ValueError("required_alignment_bytes must be positive")

    results: list[SearchResult] = []

    for bits in range(1, max_bits + 1):
        for base in range(max_base + 1):
            for shift in range(-max_shift, max_shift + 1):
                if shift == 0 or abs(shift) < bits:
                    continue

                if domain_size is not None and not is_domain_permutation(
                    domain_size,
                    bits,
                    base,
                    shift,
                ):
                    continue

                if (
                    required_alignment_bytes is not None
                    and not _alignment_is_valid(
                        materialized_groups,
                        bits,
                        base,
                        shift,
                        element_bytes=element_bytes,
                        required_alignment_bytes=required_alignment_bytes,
                    )
                ):
                    continue

                conflicts = sum(
                    count_group_conflicts(
                        group,
                        bits,
                        base,
                        shift,
                        element_bytes=element_bytes,
                    )
                    for group in materialized_groups
                )
                results.append(
                    SearchResult(
                        conflicts=conflicts,
                        bits=bits,
                        shift_magnitude=abs(shift),
                        base=base,
                        shift=shift,
                    )
                )

    return sorted(results)


def transpose_example() -> list[SearchResult]:
    """Search swizzles for row and column loads of a 32x32 float tile."""
    row_load = AccessGroup(
        tuple(Access(lane, 4) for lane in range(32)),
        name="row-load",
    )
    column_load = AccessGroup(
        tuple(Access(lane * 32, 4) for lane in range(32)),
        name="column-load",
    )
    return search_swizzles(
        [row_load, column_load],
        element_bytes=4,
        domain_size=32 * 32,
        max_bits=5,
        max_base=5,
        max_shift=10,
    )


def load_problem(
    path: str | Path,
) -> tuple[tuple[AccessGroup, ...], dict[str, int]]:
    """Load access groups and search arguments from a JSON file."""
    problem_path = Path(path)
    with problem_path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)

    groups = []
    for raw_group in data["groups"]:
        name = str(raw_group.get("name", ""))
        has_range = "range" in raw_group
        has_accesses = "accesses" in raw_group
        if has_range == has_accesses:
            raise ValueError(
                f"group {name!r} must contain exactly one of "
                "'range' or 'accesses'"
            )

        if has_range:
            raw_range = raw_group["range"]
            count = int(raw_range["count"])
            if count <= 0:
                raise ValueError(f"group {name!r} range count must be positive")
            start = int(raw_range.get("start", 0))
            step = int(raw_range.get("step", 1))
            access_bytes = int(raw_group["access_bytes"])
            accesses = tuple(
                Access(start + lane * step, access_bytes)
                for lane in range(count)
            )
        else:
            accesses = tuple(
                Access(
                    int(raw_access["element_index"]),
                    int(raw_access["access_bytes"]),
                )
                for raw_access in raw_group["accesses"]
            )
            if not accesses:
                raise ValueError(
                    f"group {name!r} must contain at least one access"
                )

        groups.append(AccessGroup(accesses, name=name))

    raw_search = data.get("search", {})
    arguments = {
        "element_bytes": int(data["element_bytes"]),
        "max_bits": int(raw_search.get("max_bits", 5)),
        "max_base": int(raw_search.get("max_base", 8)),
        "max_shift": int(raw_search.get("max_shift", 12)),
    }
    if data.get("domain_size") is not None:
        arguments["domain_size"] = int(data["domain_size"])
    if data.get("required_alignment_bytes") is not None:
        arguments["required_alignment_bytes"] = int(
            data["required_alignment_bytes"]
        )

    return tuple(groups), arguments


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search CuTe-style Swizzle<B,M,S> candidates."
    )
    parser.add_argument(
        "--problem",
        type=Path,
        help="JSON problem description; defaults to the transpose example",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="number of candidates to print",
    )
    args = parser.parse_args(argv)

    if args.top <= 0:
        parser.error("--top must be positive")

    if args.problem is None:
        results = transpose_example()
    else:
        groups, search_arguments = load_problem(args.problem)
        results = search_swizzles(groups, **search_arguments)

    if not results:
        print("No candidate satisfies all constraints.")
        return 1

    for candidate in results[: args.top]:
        print(candidate)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
