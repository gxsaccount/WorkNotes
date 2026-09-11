"""Dependency-free checks for the arithmetic examples in the Coalesce notes."""

import unittest
from math import prod


def offsets(shape, stride):
    """Return Layout(i) for scalar natural coordinates in mode-0-first order."""
    result = []
    for natural_index in range(prod(shape)):
        remaining = natural_index
        offset = 0
        for extent, step in zip(shape, stride):
            coordinate = remaining % extent
            remaining //= extent
            offset += coordinate * step
        result.append(offset)
    return result


class CoalesceExampleTest(unittest.TestCase):
    def assert_same_mapping(
        self,
        source_shape,
        source_stride,
        result_shape,
        result_stride,
    ):
        self.assertEqual(prod(source_shape), prod(result_shape))
        self.assertEqual(
            offsets(source_shape, source_stride),
            offsets(result_shape, result_stride),
        )

    def test_official_example_coalesces_to_12_by_1(self):
        # Flattened official example:
        # (2,(1,6)):(1,(6,2)) -> (2,1,6):(1,6,2) -> 12:1.
        self.assert_same_mapping((2, 1, 6), (1, 6, 2), (12,), (1,))

    def test_row_major_mapping_cannot_be_replaced_by_8_by_1(self):
        source = offsets((2, 4), (4, 1))
        candidate = offsets((8,), (1,))
        self.assertEqual(source, [0, 4, 1, 5, 2, 6, 3, 7])
        self.assertNotEqual(source, candidate)

    def test_static_size_one_mode_has_no_mapping_contribution(self):
        self.assert_same_mapping((4, 1, 3), (2, 99, 8), (12,), (2,))

    def test_chain_coalesce(self):
        self.assert_same_mapping((2, 3, 5), (1, 2, 6), (30,), (1,))

    def test_coalesced_layout_can_still_broadcast(self):
        self.assert_same_mapping((4, 3), (0, 0), (12,), (0,))
        self.assertEqual(set(offsets((12,), (0,))), {0})

    def test_positive_strides_can_alias_without_coalescing(self):
        self.assertEqual(offsets((2, 2), (1, 1)), [0, 1, 1, 2])

    def test_by_mode_result_preserves_top_level_modes(self):
        self.assert_same_mapping((2, 1, 6), (1, 6, 2), (2, 6), (1, 2))


if __name__ == "__main__":
    unittest.main()
