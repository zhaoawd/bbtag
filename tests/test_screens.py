from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import bluetag.screens as screens
from bluetag.screens import ScreenProfile, get_screen_profile


class ScreenProfileTests(unittest.TestCase):
    def test_cache_path_is_resolved_from_package_directory_not_cwd(self) -> None:
        profile = get_screen_profile("2.9inch")
        expected = Path(screens.__file__).resolve().parent / ".device.2.9inch"
        original_cwd = Path.cwd()

        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                self.assertEqual(profile.cache_path, expected)
                self.assertNotEqual(profile.cache_path.parent, Path.cwd())
            finally:
                os.chdir(original_cwd)

    def test_absolute_cache_path_is_preserved(self) -> None:
        profile = ScreenProfile(
            name="test",
            aliases=("test",),
            width=4,
            height=1,
            device_prefix="EDP-",
            cache_file="/tmp/.device.test",
            transport="layer",
            default_interval_ms=100,
        )

        self.assertEqual(profile.cache_path, Path("/tmp/.device.test"))

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
