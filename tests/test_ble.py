from __future__ import annotations

import io
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from bluetag.ble import scan


class BleScanTests(unittest.IsolatedAsyncioTestCase):
    async def test_scan_uses_adv_local_name_when_device_name_is_missing(self) -> None:
        device = types.SimpleNamespace(name=None, address="AA:BB:CC:DD:EE:FF")
        adv = types.SimpleNamespace(local_name="EDP-200009EB", rssi=-48)

        class FakeScanner:
            @staticmethod
            async def discover(*, timeout: float, return_adv: bool):
                self.assertEqual(timeout, 5.0)
                self.assertTrue(return_adv)
                return {device.address: (device, adv)}

        with patch("bluetag.ble._require_bleak", return_value=(object(), FakeScanner)):
            devices = await scan(timeout=5.0, prefixes=("EDP-",))

        self.assertEqual(
            devices,
            [
                {
                    "name": "EDP-200009EB",
                    "address": "AA:BB:CC:DD:EE:FF",
                    "rssi": -48,
                    "_ble_device": device,
                }
            ],
        )

    async def test_scan_debug_raw_prints_all_discovered_results_before_filtering(self) -> None:
        first_device = types.SimpleNamespace(name=None, address="AA:BB:CC:DD:EE:FF")
        first_adv = types.SimpleNamespace(local_name="EDP-200009EB", rssi=-48)
        second_device = types.SimpleNamespace(
            name="Random-Device", address="11:22:33:44:55:66"
        )
        second_adv = types.SimpleNamespace(local_name="Other-Name", rssi=-70)

        class FakeScanner:
            @staticmethod
            async def discover(*, timeout: float, return_adv: bool):
                self.assertEqual(timeout, 5.0)
                self.assertTrue(return_adv)
                return {
                    first_device.address: (first_device, first_adv),
                    second_device.address: (second_device, second_adv),
                }

        stdout = io.StringIO()
        with (
            patch("bluetag.ble._require_bleak", return_value=(object(), FakeScanner)),
            redirect_stdout(stdout),
        ):
            devices = await scan(timeout=5.0, prefixes=("EDP-",), debug_raw=True)

        output = stdout.getvalue()
        self.assertIn("EDP-200009EB", output)
        self.assertIn("Random-Device", output)
        self.assertIn("Other-Name", output)
        self.assertIn("AA:BB:CC:DD:EE:FF", output)
        self.assertIn("11:22:33:44:55:66", output)
        self.assertEqual(len(devices), 1)


if __name__ == "__main__":
    unittest.main()
