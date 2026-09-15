"""Executable checks for non-normative claims in the tiling notes.

The official CUTLASS documentation defines complement, divide, and product.
These dependency-free tests verify the additional interpretations used by the
notes, such as "divide cuts / product lays out" and the condition under which
their resulting tiled layouts are equal.
"""

from dataclasses import dataclass
from math import ceil, prod
import unittest


@dataclass(frozen=True)
class Layout:
    shape: tuple[int, ...]
    stride: tuple[int, ...]

    def __post_init__(self):
        if len(self.shape) != len(self.stride):
            raise ValueError("shape and stride must have the same rank")
        if not self.shape:
            raise ValueError("layout must have at least one mode")

    @property
    def size(self):
        return prod(self.shape)

    def __call__(self, natural_index, *, extend_terminal=False):
        """Evaluate a scalar natural coordinate.

        ``extend_terminal`` models the terminal shape-1 mode intentionally
        retained by pure complement: the final coordinate receives the
        remaining quotient instead of wrapping at its nominal extent.
        """
        if natural_index < 0:
            raise ValueError("natural index must be non-negative")
        if not extend_terminal and natural_index >= self.size:
            raise ValueError("natural index is outside the finite domain")

        remaining = natural_index
        offset = 0
        last = len(self.shape) - 1
        for mode, (extent, step) in enumerate(zip(self.shape, self.stride)):
            if extend_terminal and mode == last:
                coordinate = remaining
            else:
                coordinate = remaining % extent
                remaining //= extent
            offset += coordinate * step
        return offset

    def values(self):
        return [self(i) for i in range(self.size)]


def coalesce(layout):
    shape = list(layout.shape)
    stride = list(layout.stride)
    i = 0
    while i < len(shape):
        if shape[i] == 1:
            shape.pop(i)
            stride.pop(i)
            continue
        if i + 1 < len(shape) and stride[i + 1] == shape[i] * stride[i]:
            shape[i] *= shape[i + 1]
            shape.pop(i + 1)
            stride.pop(i + 1)
            continue
        i += 1

    if not shape:
        return Layout((1,), (0,))
    return Layout(tuple(shape), tuple(stride))


def complement_prefix(layout):
    """Translate the static positive-stride prefix algorithm in layout.hpp."""
    shape = list(layout.shape)
    stride = list(layout.stride)
    result_shape = []
    result_stride = [1]

    for _ in range(len(shape) - 1):
        min_stride = min(stride)
        min_index = stride.index(min_stride)
        new_shape = min_stride // result_stride[-1]
        if new_shape == 0:
            raise ValueError("non-injective layout")
        result_shape.append(new_shape)
        result_stride.append(min_stride * shape[min_index])
        shape.pop(min_index)
        stride.pop(min_index)

    new_shape = stride[0] // result_stride[-1]
    if new_shape == 0:
        raise ValueError("non-injective layout")
    result_shape.append(new_shape)
    new_stride = stride[0] * shape[0]
    return Layout(tuple(result_shape), tuple(result_stride)), new_stride


def pure_complement(layout):
    prefix, new_stride = complement_prefix(layout)
    result = coalesce(prefix)
    if result.size == 1:
        return Layout((1,), (new_stride,))
    return Layout(result.shape + (1,), result.stride + (new_stride,))


def bounded_complement(layout, cotarget):
    prefix, new_stride = complement_prefix(layout)
    repeat_count = ceil(cotarget / new_stride)
    return coalesce(
        Layout(
            prefix.shape + (repeat_count,),
            prefix.stride + (new_stride,),
        )
    )


def compose_values(outer, inner, *, extend_outer=False):
    return [
        outer(inner(i), extend_terminal=extend_outer)
        for i in range(inner.size)
    ]


def tiled_values(tile_values, bases):
    return [
        tile_offset + base
        for base in bases
        for tile_offset in tile_values
    ]


class ComplementRelationTest(unittest.TestCase):
    def test_reference_complement_algorithm_matches_official_examples(self):
        cases = [
            (Layout((4,), (1,)), Layout((6,), (4,))),
            (Layout((6,), (4,)), Layout((4,), (1,))),
            (Layout((4, 6), (1, 4)), Layout((1,), (0,))),
            (Layout((4,), (2,)), Layout((2, 3), (1, 8))),
            (Layout((2, 4), (1, 6)), Layout((3,), (2,))),
            (Layout((2, 2), (1, 6)), Layout((3, 2), (2, 12))),
        ]

        for layout, expected in cases:
            with self.subTest(layout=layout):
                result = bounded_complement(layout, 24)
                completed = tiled_values(layout.values(), result.values())
                self.assertEqual(result, expected)
                self.assertEqual(len(completed), len(set(completed)))
                self.assertEqual(set(completed), set(range(24)))

    def test_non_multiple_cotarget_is_covered_by_whole_replicas(self):
        tile = Layout((4,), (1,))
        result = bounded_complement(tile, 10)
        completed = tiled_values(tile.values(), result.values())

        self.assertEqual(result, Layout((3,), (4,)))
        self.assertEqual(completed, list(range(12)))
        self.assertGreaterEqual(max(completed) + 1, 10)

    def test_pure_complement_retains_the_extension_mode(self):
        tile = Layout((4,), (1,))

        self.assertEqual(pure_complement(tile), Layout((1,), (4,)))
        self.assertEqual(
            bounded_complement(tile, 24),
            Layout((6,), (4,)),
        )

    def test_bounded_complement_extends_pure_repetition_rule(self):
        tile = Layout((2, 2), (4, 1))
        repeat = pure_complement(tile)
        grid = Layout((6,), (1,))

        self.assertEqual(repeat, Layout((2, 1), (2, 8)))
        self.assertEqual(
            bounded_complement(tile, 24),
            Layout((2, 3), (2, 8)),
        )
        self.assertEqual(
            compose_values(repeat, grid, extend_outer=True),
            bounded_complement(tile, 24).values(),
        )

    def test_divide_and_product_match_when_tile_bases_match(self):
        full = Layout((4, 2, 3), (2, 1, 8))
        selector = Layout((4,), (2,))
        rest = bounded_complement(selector, full.size)

        tile_values = compose_values(full, selector)
        divide_bases = compose_values(full, rest)
        divide_values = [
            full(selector(i) + rest(j))
            for j in range(rest.size)
            for i in range(selector.size)
        ]

        tile = Layout((2, 2), (4, 1))
        repeat = pure_complement(tile)
        grid = Layout((6,), (1,))
        product_bases = compose_values(repeat, grid, extend_outer=True)
        product_values = tiled_values(tile.values(), product_bases)

        self.assertEqual(tile_values, tile.values())
        self.assertEqual(divide_bases, product_bases)
        self.assertEqual(divide_values, product_values)

    def test_equal_count_and_base_set_do_not_imply_equal_layout_order(self):
        repeat = pure_complement(Layout((2, 2), (4, 1)))
        ordered_grid = Layout((6,), (1,))
        reordered_grid = Layout((2, 3), (3, 1))

        ordered = compose_values(repeat, ordered_grid, extend_outer=True)
        reordered = compose_values(repeat, reordered_grid, extend_outer=True)

        self.assertEqual(len(ordered), len(reordered))
        self.assertEqual(set(ordered), set(reordered))
        self.assertNotEqual(ordered, reordered)

    def test_each_tile_is_a_translation_of_the_prototype_tile(self):
        tile = Layout((2, 2), (4, 1))
        bases = [0, 2, 8, 10, 16, 18]
        tiled = tiled_values(tile.values(), bases)

        for tile_number, base in enumerate(bases):
            begin = tile_number * tile.size
            end = begin + tile.size
            self.assertEqual(
                tiled[begin:end],
                [offset + base for offset in tile.values()],
            )


if __name__ == "__main__":
    unittest.main()
