from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bluetag.usage_codex import (
    build_codex_panel_rows,
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


def _count_rgb_pixels(image, rgb):
    count = 0
    converted = image.convert("RGB")
    for y in range(converted.height):
        for x in range(converted.width):
            if converted.getpixel((x, y)) == rgb:
                count += 1
    return count


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

        self.assertEqual([row.label for row in rows], ["5h", "7d"])
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

    def test_build_codex_panel_rows_compacts_labels_for_3_7(self) -> None:
        now = datetime.now(timezone.utc)
        payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 45.2,
                    "limit_window_seconds": 18_000,
                    "reset_at": int((now + timedelta(hours=4, minutes=52)).timestamp()),
                },
                "secondary_window": {
                    "used_percent": 12.0,
                    "limit_window_seconds": 604_800,
                    "reset_at": int((now + timedelta(hours=126, minutes=52)).timestamp()),
                },
            }
        }

        rows = build_codex_panel_rows(payload, ZoneInfo("UTC"))

        self.assertEqual([row.label for row in rows], ["5h", "7d"])
        self.assertAlmostEqual(rows[0].used_percent, 45.2)
        self.assertIn(":", rows[0].remaining_text)
        self.assertIn("/", rows[1].remaining_text)
        self.assertIn(":", rows[1].remaining_text)

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
        self.assertLessEqual(max_x, 288)
        self.assertLessEqual(max_y, 123)
        self.assertLessEqual(_max_blank_row_run(image), 70)

    def test_render_codex_images_use_red_for_high_usage(self) -> None:
        payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 82.0,
                    "limit_window_seconds": 18_000,
                    "reset_at": 1_775_242_400,
                },
                "secondary_window": {
                    "used_percent": 88.0,
                    "limit_window_seconds": 604_800,
                    "reset_at": 1_775_520_000,
                },
            }
        }

        for image in (
            render_codex_2_13(payload, ZoneInfo("UTC")),
            render_codex_2_9(payload, ZoneInfo("UTC")),
            render_codex_3_7(payload, ZoneInfo("UTC")),
        ):
            self.assertGreater(_count_rgb_pixels(image, (255, 0, 0)), 0)

    def test_render_codex_images_keep_low_usage_black_only(self) -> None:
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

        for image in (
            render_codex_2_13(payload, ZoneInfo("UTC")),
            render_codex_2_9(payload, ZoneInfo("UTC")),
            render_codex_3_7(payload, ZoneInfo("UTC")),
        ):
            self.assertEqual(_count_rgb_pixels(image, (255, 0, 0)), 0)

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

        self.assertEqual(rows, [("5h", 45.2), ("7d", 12.0)])


if __name__ == "__main__":
    unittest.main()
