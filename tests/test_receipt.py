"""The receipt's arithmetic: whatever the amount, the parts sum to it, to the cent."""
import random
import unittest

from civictools import receipt
from tests import fixtures


class Allocate(unittest.TestCase):
    def lines(self, fy=2026):
        return sorted((receipt.cents(a) for _, a in fixtures.function_amounts(fy)), reverse=True)

    def test_parts_always_sum_to_the_amount_entered(self):
        rng = random.Random(7)
        for fy in fixtures.YEARS:
            lines = self.lines(fy)
            for amount in [0, 1, 2, 99, 100, 1_000_000, 999_999_999] + [rng.randrange(1, 10**9) for _ in range(200)]:
                parts = receipt.allocate(amount, lines)
                self.assertEqual(sum(parts), amount)
                self.assertEqual(len(parts), len(lines))

    def test_each_part_is_within_a_cent_of_its_exact_share(self):
        lines = self.lines()
        total = sum(lines)
        for amount in (1_000_000, 123_456_789):
            for part, line in zip(receipt.allocate(amount, lines), lines):
                exact = amount * line / total
                self.assertLess(abs(part - exact), 1.0000001)

    def test_negative_lines_get_negative_parts(self):
        lines = self.lines()
        parts = receipt.allocate(1_000_000, lines)
        for part, line in zip(parts, lines):
            self.assertEqual(part < 0, line < 0 and part != 0)
        self.assertTrue(any(p < 0 for p in parts))

    def test_leftover_cents_go_to_the_largest_remainders(self):
        self.assertEqual(receipt.allocate(100, [1, 1, 1]), [34, 33, 33])
        self.assertEqual(receipt.allocate(200, [1, 1, 1]), [67, 67, 66])
        self.assertEqual(receipt.allocate(10, [3, 1]), [8, 2])      # 7.5 and 2.5: the tie goes to the earlier line
        self.assertEqual(receipt.allocate(1, [5, -1, -1]), [2, 0, -1])   # exact shares 1.67, -0.33, -0.33: each part within a cent

    def test_a_total_that_is_not_positive_is_refused(self):
        with self.assertRaises(ValueError):
            receipt.allocate(100, [5, -5])

    def test_cents_and_dollars(self):
        self.assertEqual(receipt.cents("965160356821.48"), 96516035682148)
        self.assertEqual(receipt.cents("-15465292145.92"), -1546529214592)
        self.assertEqual(receipt.cents("0.1"), 10)
        self.assertEqual(receipt.usd(123456789), "$1,234,567.89")
        self.assertEqual(receipt.usd(-2091), "-$20.91")
        self.assertEqual(receipt.usd(5), "$0.05")

    def test_share_is_rounded_half_up_to_one_decimal(self):
        self.assertEqual(receipt.share(225, 1000), 22.5)
        self.assertEqual(receipt.share(1235, 100000), 1.2)
        self.assertEqual(receipt.share(125, 10000), 1.3)
        self.assertEqual(receipt.share(-21, 1000), -2.1)


if __name__ == "__main__":
    unittest.main()
