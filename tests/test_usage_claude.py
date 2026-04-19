from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from bluetag.usage_claude import (
    build_claude_panel_rows,
    build_claude_refresh_rows,
    build_claude_rows,
    fetch_claude_usage,
    render_claude_2_13,
    render_claude_2_9,
    render_claude_3_7,
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


class ClaudeUsageTests(unittest.TestCase):
    def test_build_rows_omits_sonnet_on_small_screen(self) -> None:
        payload = {
            "five_hour": {"utilization": 45.2, "resets_at": "2026-04-03T18:00:00Z"},
            "seven_day": {"utilization": 12.0, "resets_at": "2026-04-07T00:00:00Z"},
            "seven_day_sonnet": {
                "utilization": 8.5,
                "resets_at": "2026-04-07T00:00:00Z",
            },
        }

        compact_rows = build_claude_rows(payload, ZoneInfo("UTC"), include_sonnet=False)
        full_rows = build_claude_rows(payload, ZoneInfo("UTC"), include_sonnet=True)

        self.assertEqual(
            [row.label for row in compact_rows],
            ["5h", "7d"],
        )
        self.assertEqual(
            [row.label for row in full_rows],
            ["5h", "7d", "sonnet"],
        )
        self.assertAlmostEqual(compact_rows[0].left_percent, 54.8)

    def test_fetch_claude_usage_from_keychain_and_api(self) -> None:
        payload = {
            "five_hour": {"utilization": 45.2, "resets_at": "2026-04-03T18:00:00Z"}
        }
        response = Mock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)

        keychain_result = Mock(
            stdout='{"claudeAiOauth":{"accessToken":"token-123"}}\n',
            stderr="",
            returncode=0,
        )

        with patch("subprocess.run", return_value=keychain_result) as run_mock:
            with patch("urllib.request.urlopen", return_value=response) as urlopen_mock:
                result = fetch_claude_usage(timeout=7.5)

        self.assertEqual(result, payload)
        run_mock.assert_called_once()
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.anthropic.com/api/oauth/usage")
        self.assertEqual(request.headers["Authorization"], "Bearer token-123")

    def test_fetch_claude_usage_refreshes_expired_access_token(self) -> None:
        refreshed_usage = {
            "five_hour": {"utilization": 22.0, "resets_at": "2026-04-03T18:00:00Z"}
        }
        keychain_result = Mock(
            stdout=(
                '{"claudeAiOauth":{"accessToken":"expired-token","refreshToken":"refresh-123",'
                '"expiresAt":1775294632955}}'
            ),
            stderr="",
            returncode=0,
        )
        save_result = Mock(stdout="", stderr="", returncode=0)

        usage_401 = HTTPError(
            url="https://api.anthropic.com/api/oauth/usage",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=BytesIO(
                b'{"type":"error","error":{"type":"authentication_error","details":{"error_code":"token_expired"}}}'
            ),
        )
        refresh_response = Mock()
        refresh_response.read.return_value = json.dumps(
            {
                "access_token": "fresh-token",
                "refresh_token": "refresh-456",
                "expires_in": 3600,
            }
        ).encode("utf-8")
        refresh_response.__enter__ = Mock(return_value=refresh_response)
        refresh_response.__exit__ = Mock(return_value=False)

        usage_response = Mock()
        usage_response.read.return_value = json.dumps(refreshed_usage).encode("utf-8")
        usage_response.__enter__ = Mock(return_value=usage_response)
        usage_response.__exit__ = Mock(return_value=False)

        with patch("subprocess.run", side_effect=[keychain_result, save_result]) as run_mock:
            with patch(
                "urllib.request.urlopen",
                side_effect=[usage_401, refresh_response, usage_response],
            ) as urlopen_mock:
                result = fetch_claude_usage(timeout=7.5)

        self.assertEqual(result, refreshed_usage)
        self.assertEqual(run_mock.call_count, 2)
        refresh_request = urlopen_mock.call_args_list[1].args[0]
        retry_request = urlopen_mock.call_args_list[2].args[0]
        self.assertEqual(refresh_request.full_url, "https://api.anthropic.com/v1/oauth/token")
        self.assertEqual(retry_request.headers["Authorization"], "Bearer fresh-token")

    def test_fetch_claude_usage_from_linux_credentials_file(self) -> None:
        payload = {
            "five_hour": {"utilization": 45.2, "resets_at": "2026-04-03T18:00:00Z"}
        }
        response = Mock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = os.path.join(tmpdir, ".credentials.json")
            with open(credentials_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {"claudeAiOauth": {"accessToken": "token-file-123"}},
                    handle,
                )

            with patch("subprocess.run", side_effect=FileNotFoundError("security")):
                with patch.dict(
                    os.environ,
                    {"CLAUDE_CREDENTIALS_PATH": credentials_path},
                    clear=False,
                ):
                    with patch("urllib.request.urlopen", return_value=response) as urlopen_mock:
                        result = fetch_claude_usage(timeout=7.5)

        self.assertEqual(result, payload)
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.headers["Authorization"], "Bearer token-file-123")

    def test_fetch_claude_usage_refreshes_and_saves_linux_credentials_file(self) -> None:
        refreshed_usage = {
            "five_hour": {"utilization": 22.0, "resets_at": "2026-04-03T18:00:00Z"}
        }

        usage_401 = HTTPError(
            url="https://api.anthropic.com/api/oauth/usage",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=BytesIO(
                b'{"type":"error","error":{"type":"authentication_error","details":{"error_code":"token_expired"}}}'
            ),
        )
        refresh_response = Mock()
        refresh_response.read.return_value = json.dumps(
            {
                "access_token": "fresh-file-token",
                "refresh_token": "fresh-file-refresh",
                "expires_in": 3600,
            }
        ).encode("utf-8")
        refresh_response.__enter__ = Mock(return_value=refresh_response)
        refresh_response.__exit__ = Mock(return_value=False)

        usage_response = Mock()
        usage_response.read.return_value = json.dumps(refreshed_usage).encode("utf-8")
        usage_response.__enter__ = Mock(return_value=usage_response)
        usage_response.__exit__ = Mock(return_value=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            credentials_path = os.path.join(tmpdir, ".credentials.json")
            with open(credentials_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "claudeAiOauth": {
                            "accessToken": "expired-file-token",
                            "refreshToken": "refresh-file-123",
                            "expiresAt": 1775294632955,
                        }
                    },
                    handle,
                )

            with patch("subprocess.run", side_effect=FileNotFoundError("security")):
                with patch.dict(
                    os.environ,
                    {"CLAUDE_CREDENTIALS_PATH": credentials_path},
                    clear=False,
                ):
                    with patch(
                        "urllib.request.urlopen",
                        side_effect=[usage_401, refresh_response, usage_response],
                    ) as urlopen_mock:
                        result = fetch_claude_usage(timeout=7.5)

            with open(credentials_path, "r", encoding="utf-8") as handle:
                updated_payload = json.load(handle)

        self.assertEqual(result, refreshed_usage)
        retry_request = urlopen_mock.call_args_list[2].args[0]
        self.assertEqual(retry_request.headers["Authorization"], "Bearer fresh-file-token")
        self.assertEqual(
            updated_payload["claudeAiOauth"]["accessToken"],
            "fresh-file-token",
        )
        self.assertEqual(
            updated_payload["claudeAiOauth"]["refreshToken"],
            "fresh-file-refresh",
        )

    def test_render_claude_images_for_both_screen_sizes(self) -> None:
        payload = {
            "five_hour": {"utilization": 45.2, "resets_at": "2026-04-03T18:00:00Z"},
            "seven_day": {"utilization": 12.0, "resets_at": "2026-04-07T00:00:00Z"},
            "seven_day_sonnet": {
                "utilization": 8.5,
                "resets_at": "2026-04-07T00:00:00Z",
            },
        }

        small = render_claude_2_13(payload, ZoneInfo("UTC"))
        medium = render_claude_2_9(payload, ZoneInfo("UTC"))
        large = render_claude_3_7(payload, ZoneInfo("UTC"))

        self.assertEqual(small.size, (250, 122))
        self.assertEqual(medium.size, (296, 128))
        self.assertEqual(large.size, (416, 240))

    def test_build_claude_panel_rows_compacts_labels_for_3_7(self) -> None:
        now = datetime.now(timezone.utc)
        payload = {
            "five_hour": {
                "utilization": 94.0,
                "resets_at": (now + timedelta(hours=4, minutes=52)).isoformat(),
            },
            "seven_day": {
                "utilization": 88.0,
                "resets_at": (now + timedelta(hours=126, minutes=52)).isoformat(),
            },
            "seven_day_sonnet": {
                "utilization": 8.5,
                "resets_at": (now + timedelta(hours=120)).isoformat(),
            },
        }

        rows = build_claude_panel_rows(payload, ZoneInfo("UTC"), include_sonnet=False)

        self.assertEqual([row.label for row in rows], ["5h", "7d"])
        self.assertAlmostEqual(rows[0].used_percent, 94.0)
        self.assertIn(":", rows[0].remaining_text)
        self.assertIn("/", rows[1].remaining_text)
        self.assertIn(":", rows[1].remaining_text)

    def test_render_claude_2_9_keeps_footer_and_right_edge_safe(self) -> None:
        payload = {
            "five_hour": {"utilization": 100.0, "resets_at": "2026-04-08T09:40:00Z"},
            "seven_day": {"utilization": 61.0, "resets_at": "2026-04-08T15:00:00Z"},
            "seven_day_sonnet": {
                "utilization": 8.5,
                "resets_at": "2026-04-07T00:00:00Z",
            },
        }

        image = render_claude_2_9(payload, ZoneInfo("Asia/Shanghai"))
        _min_x, _min_y, max_x, max_y = _black_bbox(image)
        self.assertLessEqual(max_x, 288)
        self.assertLessEqual(max_y, 123)

    def test_build_claude_refresh_rows(self) -> None:
        payload = {
            "five_hour": {"utilization": 45.2, "resets_at": "2026-04-03T18:00:00Z"},
            "seven_day": {"utilization": 12.0, "resets_at": "2026-04-07T00:00:00Z"},
            "seven_day_sonnet": {
                "utilization": 8.5,
                "resets_at": "2026-04-07T00:00:00Z",
            },
        }

        compact = build_claude_refresh_rows(payload, include_sonnet=False)
        full = build_claude_refresh_rows(payload, include_sonnet=True)

        self.assertEqual(compact, [("5h", 45.2), ("7d", 12.0)])
        self.assertEqual(
            full,
            [("5h", 45.2), ("7d", 12.0), ("sonnet", 8.5)],
        )


if __name__ == "__main__":
    unittest.main()
