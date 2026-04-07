from __future__ import annotations

import unittest
from zoneinfo import ZoneInfo

from bluetag.usage_codex import (
    build_codex_refresh_rows,
    build_codex_rows,
    render_codex_2_13,
    render_codex_2_9,
    render_codex_3_7,
)


def _black_bbox(image):
    pixels = image.convert("1")
    xs: list[int] = []
    ys: list[int] = []
    for y in range(pixels.height):
        for x in range(pixels.width):
            if pixels.getpixel((x, y)) == 0:
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _max_blank_row_run(image) -> int:
    pixels = image.convert("1")
    longest = 0
    current = 0
    for y in range(pixels.height):
        has_black = False
        for x in range(pixels.width):
            if pixels.getpixel((x, y)) == 0:
                has_black = True
                break
        if has_black:
            longest = max(longest, current)
            current = 0
        else:
            current += 1
    return max(longest, current)


class CodexUsageTests(unittest.TestCase):
    def test_build_codex_rows_from_rate_limit_payload(self) -> None:
        payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 45.2,
                    "limit_window_seconds": 18_000,
                    "reset_at": 1_775_242_400,
                },
                "secondary_window": {
                    "used_percent": 12.0,
                    "limit_window_seconds": 604_800,
                    "reset_at": 1_775_520_000,
                },
            }
        }

        rows = build_codex_rows(payload, ZoneInfo("UTC"))

        self.assertEqual([row.label for row in rows], ["5h limit", "weekly limit"])
        self.assertAlmostEqual(rows[0].left_percent, 54.8)
        self.assertAlmostEqual(rows[1].left_percent, 88.0)
        self.assertTrue(rows[0].resets_text.startswith("resets "))

    def test_render_codex_images_for_both_screen_sizes(self) -> None:
        payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 45.2,
                    "limit_window_seconds": 18_000,
                    "reset_at": 1_775_242_400,
                },
                "secondary_window": {
                    "used_percent": 12.0,
                    "limit_window_seconds": 604_800,
                    "reset_at": 1_775_520_000,
                },
            }
        }

        small = render_codex_2_13(payload, ZoneInfo("UTC"))
        medium = render_codex_2_9(payload, ZoneInfo("UTC"))
        large = render_codex_3_7(payload, ZoneInfo("UTC"))

        self.assertEqual(small.size, (250, 122))
        self.assertEqual(medium.size, (296, 128))
        self.assertEqual(large.size, (416, 240))

    def test_render_codex_2_9_keeps_footer_and_right_edge_safe(self) -> None:
        payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 1.0,
                    "limit_window_seconds": 18_000,
                    "reset_at": 1_775_242_400,
                },
                "secondary_window": {
                    "used_percent": 42.0,
                    "limit_window_seconds": 604_800,
                    "reset_at": 1_775_520_000,
                },
            }
        }

        image = render_codex_2_9(payload, ZoneInfo("Asia/Shanghai"))
        _min_x, _min_y, max_x, max_y = _black_bbox(image)
        self.assertLessEqual(max_x, 283)
        self.assertLessEqual(max_y, 123)
        self.assertLessEqual(_max_blank_row_run(image), 18)


    def test_build_codex_refresh_rows(self) -> None:
        payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 45.2,
                    "limit_window_seconds": 18_000,
                    "reset_at": 1_775_242_400,
                },
                "secondary_window": {
                    "used_percent": 12.0,
                    "limit_window_seconds": 604_800,
                    "reset_at": 1_775_520_000,
                },
            }
        }

        rows = build_codex_refresh_rows(payload)

        self.assertEqual(rows, [("5h limit", 54.8), ("weekly limit", 88.0)])


if __name__ == "__main__":
    unittest.main()
