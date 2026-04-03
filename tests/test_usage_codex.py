from __future__ import annotations

import unittest
from zoneinfo import ZoneInfo

from bluetag.usage_codex import build_codex_rows, render_codex_2_13, render_codex_3_7


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
        large = render_codex_3_7(payload, ZoneInfo("UTC"))

        self.assertEqual(small.size, (250, 122))
        self.assertEqual(large.size, (416, 240))


if __name__ == "__main__":
    unittest.main()
