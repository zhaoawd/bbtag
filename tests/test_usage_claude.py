from __future__ import annotations

import json
import unittest
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from bluetag.usage_claude import (
    build_claude_refresh_rows,
    build_claude_rows,
    fetch_claude_usage,
    render_claude_2_13,
    render_claude_2_9,
    render_claude_3_7,
)


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
            ["5h session", "7d all models"],
        )
        self.assertEqual(
            [row.label for row in full_rows],
            ["5h session", "7d all models", "sonnet"],
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

        self.assertEqual(compact, [("5h session", 54.8), ("7d all models", 88.0)])
        self.assertEqual(
            full,
            [("5h session", 54.8), ("7d all models", 88.0), ("sonnet", 91.5)],
        )


if __name__ == "__main__":
    unittest.main()
