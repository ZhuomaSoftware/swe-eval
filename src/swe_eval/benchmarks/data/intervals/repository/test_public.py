import unittest

from intervals import merge_ranges


class PublicTests(unittest.TestCase):
    def test_disjoint(self):
        self.assertEqual(merge_ranges([(4, 6), (1, 2)]), [(1, 2), (4, 6)])

    def test_overlap(self):
        self.assertEqual(merge_ranges([(1, 4), (2, 6)]), [(1, 6)])


if __name__ == "__main__":
    unittest.main()
