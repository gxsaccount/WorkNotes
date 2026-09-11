"""Boundary-condition tests used by the CuTe layout-algebra notes.

These are intentionally dependency-free: they validate the arithmetic claims in
the notes even when the local NVIDIA CuTe Python DSL is not installed.
"""

import unittest
from pathlib import Path
import subprocess
import sys

from sim import L


def concat_1d(left_shape, left_stride, right_shape, right_stride):
    return [
        left_stride * i + right_stride * j
        for j in range(right_shape)
        for i in range(left_shape)
    ]


class NoteInvariantTest(unittest.TestCase):
    def test_single_mode_layout_extends_for_scalar_coordinates(self):
        # Matches the integral composition identity:
        # (2:2) o (100:1) == 100:2, so result(99) == 198.
        self.assertEqual(L([2], [2])(99), 198)

    def test_non_multiple_cotarget_requires_a_whole_final_replica(self):
        # complement(4:1, 10) == 3:4; concatenation covers 0..11.
        self.assertEqual(concat_1d(4, 1, 3, 4), list(range(12)))

    def test_broadcast_source_prevents_divide_from_being_a_permutation(self):
        # A=10:0 maps every coordinate to zero even if the tiler table is
        # injective. This is the key distinction between reindexing and a
        # permutation.
        self.assertEqual([L([10], [0])(i) for i in range(12)], [0] * 12)

    def test_positive_strides_can_still_alias(self):
        # (2,2):(1,1) has L(1,0) == L(0,1) == 1; broadcasting is not the
        # only route to non-injectivity.
        layout = L([2, 2], [1, 1])
        self.assertEqual(layout(1), layout(2))
        self.assertEqual(layout(1), 1)

    def test_compatible_script_distinguishes_postcondition_from_range_check(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "p8.py"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("compatible((6,2), (4,3)) = False", result.stdout)
        self.assertIn("compatible((4,3), ((2,2),3)) = True", result.stdout)


if __name__ == "__main__":
    unittest.main()
