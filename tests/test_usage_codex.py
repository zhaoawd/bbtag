from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from bluetag.usage_codex import (
    build_codex_panel_rows,
    build_codex_refresh_rows,
    build_codex_rows,
    render_codex_2_13,
    render_codex_2_9,
    render_codex_3_7,
)
from bluetag.usage_layout_3_7 import (
    PanelRow,
    _build_usage_panel_2_9_layout,
    _compute_fill_width,
    _format_timestamp_2_9,
    _load_usage_reset_font,
    _load_usage_value_font,
    render_usage_panel_2_9,
    render_usage_panel_3_7,
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


def _count_rgb_pixels_in_box(image, rgb, box):
    count = 0
    converted = image.convert("RGB")
    left, top, right, bottom = box
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            if converted.getpixel((x, y)) == rgb:
                count += 1
    return count


class CodexUsageTests(unittest.TestCase):
    def test_usage_value_font_prefers_regular_font_over_mono(self) -> None:
        with (
            patch("bluetag.usage_layout_3_7._load_font", return_value="regular") as load_font,
            patch("bluetag.usage_layout_3_7._load_mono_font", return_value="mono") as load_mono,
        ):
            result = _load_usage_value_font(14)

        self.assertEqual(result, "regular")
        load_font.assert_called_once_with(14, font_path=None)
        load_mono.assert_not_called()

    def test_usage_reset_font_prefers_regular_font_over_mono(self) -> None:
        with (
            patch("bluetag.usage_layout_3_7._load_font", return_value="regular") as load_font,
            patch("bluetag.usage_layout_3_7._load_mono_font", return_value="mono") as load_mono,
        ):
            result = _load_usage_reset_font(12)

        self.assertEqual(result, "regular")
        load_font.assert_called_once_with(12, font_path=None)
        load_mono.assert_not_called()

    def test_format_timestamp_2_9_uses_compact_numeric_clock(self) -> None:
        tzinfo = ZoneInfo("Asia/Shanghai")
        now = datetime(2026, 4, 20, 11, 24, tzinfo=tzinfo)

        self.assertEqual(_format_timestamp_2_9(now), "4/20 11:24")

    def test_build_usage_panel_2_9_layout_compacts_header_and_preserves_right_columns(
        self,
    ) -> None:
        layout = _build_usage_panel_2_9_layout(
            title_text="Today Usage",
            timestamp_text="4/20 11:24",
            font_path=None,
        )

        self.assertLessEqual(layout.title_font_size, 11)
        self.assertGreaterEqual(layout.body_font_size, 10)
        self.assertGreaterEqual(layout.timestamp_x - layout.title_right, 12)
        self.assertLessEqual(layout.timestamp_x, 226)
        self.assertEqual(layout.title_y, 7)
        self.assertEqual(layout.timestamp_y, 8)
        self.assertEqual(layout.bar_x, 33)
        self.assertGreaterEqual(layout.percent_right - layout.bar_right, 18)
        self.assertGreaterEqual(layout.time_right - layout.percent_right, 64)
        self.assertLessEqual(layout.time_right - layout.percent_right, 65)
        self.assertGreaterEqual(layout.time_right - layout.percent_right, 58)
        self.assertGreaterEqual(layout.used_header_right, layout.percent_right + 4)
        self.assertLessEqual(layout.reset_header_right, layout.time_right - 7)
        self.assertEqual(layout.section_tops, (27, 76))
        self.assertEqual(layout.section_title_gap, 13)
        self.assertGreaterEqual(layout.section_tops[1] - layout.section_tops[0], 47)

    def test_compute_fill_width_keeps_tiny_percentages_visible_but_compact(self) -> None:
        self.assertEqual(_compute_fill_width(144, 0.0), 0)
        self.assertEqual(_compute_fill_width(144, 1.0), 1)
        self.assertEqual(_compute_fill_width(144, 3.0), 1)
        self.assertGreaterEqual(_compute_fill_width(144, 4.0), 5)

    def test_render_codex_2_9_keeps_gap_between_number_and_percent_sign(self) -> None:
        payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 8.0,
                    "limit_window_seconds": 18_000,
                    "reset_at": 1_775_242_400,
                },
                "secondary_window": {
                    "used_percent": 45.0,
                    "limit_window_seconds": 604_800,
                    "reset_at": 1_775_520_000,
                },
            }
        }

        image = render_codex_2_9(payload, ZoneInfo("UTC")).convert("1")
        blank_found = False
        for x in range(204, 222):
            has_black = any(image.getpixel((x, y)) == 0 for y in range(40, 49))
            if not has_black:
                blank_found = True
                break
        self.assertTrue(blank_found)

    def test_render_codex_2_9_uses_short_section_title(self) -> None:
        payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 8.0,
                    "limit_window_seconds": 18_000,
                    "reset_at": 1_775_242_400,
                },
                "secondary_window": {
                    "used_percent": 45.0,
                    "limit_window_seconds": 604_800,
                    "reset_at": 1_775_520_000,
                },
            }
        }

        image = render_codex_2_9(payload, ZoneInfo("UTC")).convert("1")
        lower_title_region = 0
        for y in range(35, 40):
            for x in range(60, 110):
                if image.getpixel((x, y)) == 0:
                    lower_title_region += 1
        self.assertEqual(lower_title_region, 0)

    def test_render_codex_2_9_keeps_reset_text_left_edge_clean(self) -> None:
        payload = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 2.0,
                    "limit_window_seconds": 18_000,
                    "reset_at": 1_775_242_400,
                },
                "secondary_window": {
                    "used_percent": 25.0,
                    "limit_window_seconds": 604_800,
                    "reset_at": 1_775_520_000,
                },
            }
        }

        image = render_codex_2_9(payload, ZoneInfo("Asia/Shanghai")).convert("1")
        for y0, y1 in ((43, 49), (58, 64)):
            stray_pixels = sum(
                1
                for y in range(y0, y1)
                for x in range(232, 238)
                if image.getpixel((x, y)) == 0
            )
            self.assertEqual(stray_pixels, 0)

    def test_render_usage_panel_2_9_softens_divider_and_tightens_left_column(self) -> None:
        image = render_usage_panel_2_9(
            sections=[
                (
                    "Claude",
                    [
                        PanelRow("5h", 100.0, 0.0, "--:--"),
                        PanelRow("7d", 75.0, 25.0, "4/24 09:00"),
                    ],
                ),
                (
                    "Codex",
                    [
                        PanelRow("5h", 78.0, 22.0, "15:22"),
                        PanelRow("7d", 97.0, 3.0, "4/28 10:22"),
                    ],
                ),
            ],
            tzinfo=ZoneInfo("UTC"),
        ).convert("1")

        divider_black = sum(
            1 for x in range(8, 288) if image.getpixel((x, 70)) == 0
        )
        self.assertLessEqual(divider_black, 110)

        leftmost = []
        for y0, y1 in ((40, 49), (55, 64), (92, 101), (107, 116)):
            for y in range(y0, y1):
                xs = [x for x in range(33, 70) if image.getpixel((x, y)) == 0]
                if xs:
                    leftmost.append(min(xs))
        self.assertEqual(min(leftmost), 33)

        row1_label_top = min(
            y
            for y in range(39, 51)
            for x in range(8, 32)
            if image.getpixel((x, y)) == 0
        )
        row1_pct_top = min(
            y
            for y in range(39, 51)
            for x in range(195, 224)
            if image.getpixel((x, y)) == 0
        )
        row1_reset_top = min(
            y
            for y in range(39, 51)
            for x in range(240, 286)
            if image.getpixel((x, y)) == 0
        )
        self.assertLessEqual(abs(row1_label_top - row1_pct_top), 1)
        self.assertLessEqual(abs(row1_label_top - row1_reset_top), 1)

        section2_title_top = min(
            y
            for y in range(76, 89)
            for x in range(8, 70)
            if image.getpixel((x, y)) == 0
        )
        self.assertLessEqual(section2_title_top, 79)

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

    def test_render_usage_panel_2_9_keeps_red_out_of_used_percent_text(self) -> None:
        image = render_usage_panel_2_9(
            sections=[
                ("Claude", [PanelRow("5h", 15.0, 85.0, "19:00")]),
            ],
            tzinfo=ZoneInfo("UTC"),
        )

        self.assertGreater(
            _count_rgb_pixels_in_box(image, (255, 0, 0), (35, 43, 175, 48)),
            0,
        )
        self.assertEqual(
            _count_rgb_pixels_in_box(image, (255, 0, 0), (190, 39, 220, 50)),
            0,
        )

    def test_render_usage_panel_3_7_keeps_red_out_of_used_percent_text(self) -> None:
        image = render_usage_panel_3_7(
            sections=[
                ("Claude", [PanelRow("5h", 15.0, 85.0, "19:00")]),
            ],
            tzinfo=ZoneInfo("UTC"),
        )

        self.assertGreater(
            _count_rgb_pixels_in_box(image, (255, 0, 0), (48, 73, 225, 84)),
            0,
        )
        self.assertEqual(
            _count_rgb_pixels_in_box(image, (255, 0, 0), (287, 68, 311, 82)),
            0,
        )

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
