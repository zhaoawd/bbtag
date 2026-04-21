from __future__ import annotations

import unittest

from bluetag.screens import get_screen_profile


class ScreenProfileTests(unittest.TestCase):
    def test_2_9inch_uses_faster_but_conservative_default_interval(self) -> None:
        profile = get_screen_profile("2.9inch")
        self.assertEqual(profile.default_interval_ms, 70)

    def test_2_9inch_repeats_first_four_layer_packets(self) -> None:
        profile = get_screen_profile("2.9inch")
        self.assertEqual(profile.initial_repeat_packets, 4)

    def test_2_9inch_disables_partial_diff_refresh(self) -> None:
        profile = get_screen_profile("2.9inch")
        self.assertFalse(profile.supports_partial_diff)

    def test_2_9inch_uses_row_encoding(self) -> None:
        profile = get_screen_profile("2.9inch")
        self.assertEqual(profile.encoding, "row")

    def test_2_9inch_applies_red_layer_vertical_compensation(self) -> None:
        profile = get_screen_profile("2.9inch")
        self.assertEqual(profile.red_offset_x, 0)
        self.assertEqual(profile.red_offset_y, -8)


if __name__ == "__main__":
    unittest.main()
