"""Trusted grader. This file is present only in the evaluator image."""

import importlib.util
import sys
import unittest

spec = importlib.util.spec_from_file_location("candidate_intervals", "/workspace/intervals.py")
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


class RegressionTests(unittest.TestCase):
    def test_touching(self):
        self.assertEqual(candidate.merge_ranges([(1, 3), (3, 5)]), [(1, 5)])

    def test_transitive(self):
        self.assertEqual(candidate.merge_ranges([(5, 8), (1, 3), (3, 5)]), [(1, 8)])

    def test_disjoint_adjacent(self):
        self.assertEqual(candidate.merge_ranges([(1, 2), (3, 4)]), [(1, 2), (3, 4)])

    def test_nested(self):
        self.assertEqual(candidate.merge_ranges([(1, 9), (2, 4), (9, 10)]), [(1, 10)])

    def test_duplicates(self):
        self.assertEqual(candidate.merge_ranges([(2, 2), (2, 2)]), [(2, 2)])

    def test_negative(self):
        self.assertEqual(candidate.merge_ranges([(-3, 0), (0, 2), (-8, -6)]), [(-8, -6), (-3, 2)])

    def test_empty(self):
        self.assertEqual(candidate.merge_ranges([]), [])

    def test_input_not_mutated(self):
        source = [[3, 5], [1, 3]]
        self.assertEqual(candidate.merge_ranges(source), [(1, 5)])
        self.assertEqual(source, [[3, 5], [1, 3]])

    def test_invalid(self):
        with self.assertRaises(ValueError):
            candidate.merge_ranges([(3, 1)])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RegressionTests)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    if not result.wasSuccessful() or result.testsRun != 9 or result.skipped:
        raise SystemExit(1)
    print("SWE_EVAL_REGRESSION_PASSED:9", flush=True)
