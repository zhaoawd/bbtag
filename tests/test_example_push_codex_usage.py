from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo


def _load_example_module():
    module_path = (
        Path(__file__).resolve().parent.parent / "examples" / "push_codex_usage.py"
    )
    spec = importlib.util.spec_from_file_location("push_codex_usage_example", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PushCodexUsageExampleTests(unittest.TestCase):
    def test_render_usage_image_for_2_9inch(self) -> None:
        module = _load_example_module()
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

        image = module.render_usage_for_screen(
            payload,
            screen="2.9inch",
            tzinfo=ZoneInfo("UTC"),
            font_path=None,
        )

        self.assertEqual(image.size, (296, 128))

    def test_find_target_uses_cached_device_without_scanning(self) -> None:
        module = _load_example_module()
        profile = module.get_screen_profile("2.9inch")
        args = SimpleNamespace(device=None, address=None, scan_timeout=12.0)

        cached = {
            "name": "EDP-200009EB",
            "address": "E9A9C839-4F27-A7BD-B9FE-272434C3D68E",
        }

        with (
            patch.object(module, "_load_device", return_value=cached),
            patch("bluetag.ble.find_device", side_effect=AssertionError("should not scan")),
        ):
            target = module.asyncio.run(module._find_target(args, profile))

        self.assertEqual(target, cached)


if __name__ == "__main__":
    unittest.main()
