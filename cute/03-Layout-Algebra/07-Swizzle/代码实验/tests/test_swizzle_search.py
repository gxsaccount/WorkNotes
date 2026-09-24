import sys
import tempfile
import unittest
from pathlib import Path


EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENT_DIR))

from swizzle_search import (  # noqa: E402
    Access,
    AccessGroup,
    apply_swizzle,
    count_group_conflicts,
    is_domain_permutation,
    load_problem,
    search_swizzles,
)


class ApplySwizzleTest(unittest.TestCase):
    def test_swizzle_is_its_own_inverse(self):
        for index in range(1024):
            transformed = apply_swizzle(index, bits=3, base=3, shift=3)
            restored = apply_swizzle(
                transformed,
                bits=3,
                base=3,
                shift=3,
            )
            self.assertEqual(index, restored)

    def test_rejects_overlapping_bit_fields(self):
        with self.assertRaises(ValueError):
            apply_swizzle(1, bits=3, base=0, shift=2)

    def test_domain_permutation(self):
        self.assertTrue(
            is_domain_permutation(
                1024,
                bits=5,
                base=0,
                shift=5,
            )
        )


class ConflictModelTest(unittest.TestCase):
    def test_same_word_load_is_broadcast(self):
        group = AccessGroup(
            tuple(Access(0, 4) for _ in range(32)),
            name="broadcast",
        )
        self.assertEqual(
            0,
            count_group_conflicts(
                group,
                bits=1,
                base=0,
                shift=1,
                element_bytes=4,
            ),
        )

    def test_column_load_conflicts_without_effective_swizzle(self):
        column = AccessGroup(
            tuple(Access(lane * 32, 4) for lane in range(32)),
            name="column",
        )
        self.assertEqual(
            31,
            count_group_conflicts(
                column,
                bits=1,
                base=0,
                shift=10,
                element_bytes=4,
            ),
        )

    def test_search_finds_conflict_free_transpose_swizzle(self):
        row = AccessGroup(
            tuple(Access(lane, 4) for lane in range(32)),
            name="row",
        )
        column = AccessGroup(
            tuple(Access(lane * 32, 4) for lane in range(32)),
            name="column",
        )

        results = search_swizzles(
            [row, column],
            element_bytes=4,
            domain_size=32 * 32,
            max_bits=5,
            max_base=5,
            max_shift=10,
        )

        self.assertTrue(results)
        self.assertEqual(0, results[0].conflicts)
        self.assertTrue(
            any(
                result.conflicts == 0
                and result.bits == 5
                and result.base == 0
                and result.shift == 5
                for result in results
            )
        )


class ProblemFileTest(unittest.TestCase):
    def test_loads_range_and_explicit_access_groups(self):
        contents = """
        {
          "element_bytes": 2,
          "domain_size": 64,
          "required_alignment_bytes": 4,
          "search": {"max_bits": 3, "max_base": 4, "max_shift": 6},
          "groups": [
            {
              "name": "range",
              "access_bytes": 4,
              "range": {"start": 0, "step": 2, "count": 4}
            },
            {
              "name": "explicit",
              "accesses": [
                {"element_index": 0, "access_bytes": 2},
                {"element_index": 1, "access_bytes": 2}
              ]
            }
          ]
        }
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "problem.json"
            path.write_text(contents, encoding="utf-8")
            groups, arguments = load_problem(path)

        self.assertEqual(
            (0, 2, 4, 6),
            tuple(access.element_index for access in groups[0].accesses),
        )
        self.assertEqual("explicit", groups[1].name)
        self.assertEqual(2, arguments["element_bytes"])
        self.assertEqual(4, arguments["required_alignment_bytes"])


if __name__ == "__main__":
    unittest.main()
