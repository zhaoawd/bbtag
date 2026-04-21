from __future__ import annotations

import io
import sys
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, patch

from bluetag import cli


class CliScanTests(unittest.TestCase):
    def test_main_prints_version(self) -> None:
        stdout = io.StringIO()

        with (
            patch.object(sys, "argv", ["bluetag", "--version"]),
            redirect_stdout(stdout),
        ):
            with self.assertRaises(SystemExit) as exc:
                cli.main()

        self.assertEqual(exc.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"bluetag {cli.__version__}")

    def test_main_parses_scan_retries_argument(self) -> None:
        captured = {}

        def fake_cmd_scan(args):
            captured["args"] = args

        with (
            patch.object(sys, "argv", ["bluetag", "scan", "--retries", "4"]),
            patch("bluetag.cli.cmd_scan", side_effect=fake_cmd_scan),
        ):
            cli.main()

        self.assertEqual(captured["args"].command, "scan")
        self.assertEqual(captured["args"].retries, 4)

    def test_cmd_scan_retries_until_device_is_found(self) -> None:
        args = types.SimpleNamespace(
            screen="2.9inch",
            timeout=5.0,
            retries=3,
            debug_raw=False,
        )
        device = {
            "name": "EDP-200009EB",
            "address": "AA:BB:CC:DD:EE:FF",
            "rssi": -48,
        }
        stdout = io.StringIO()
        scan_mock = AsyncMock(side_effect=[[], [device]])

        with (
            patch("bluetag.ble.scan", scan_mock),
            patch("bluetag.cli._save_device") as save_device_mock,
            redirect_stdout(stdout),
        ):
            cli.cmd_scan(args)

        output = stdout.getvalue()
        self.assertIn("扫描蓝签设备 (2.9inch, 5.0s)...", output)
        self.assertIn("未发现，重试 (2/3)...", output)
        self.assertIn("📺 EDP-200009EB", output)
        self.assertEqual(scan_mock.await_count, 2)
        save_device_mock.assert_called_once()

    def test_cmd_scan_reports_not_found_after_retries_exhausted(self) -> None:
        args = types.SimpleNamespace(
            screen="2.9inch",
            timeout=5.0,
            retries=3,
            debug_raw=False,
        )
        stdout = io.StringIO()
        scan_mock = AsyncMock(side_effect=[[], [], []])

        with (
            patch("bluetag.ble.scan", scan_mock),
            patch("bluetag.cli._save_device") as save_device_mock,
            redirect_stdout(stdout),
        ):
            cli.cmd_scan(args)

        output = stdout.getvalue()
        self.assertIn("未发现，重试 (2/3)...", output)
        self.assertIn("未发现，重试 (3/3)...", output)
        self.assertIn("未发现蓝签设备", output)
        self.assertEqual(scan_mock.await_count, 3)
        save_device_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
