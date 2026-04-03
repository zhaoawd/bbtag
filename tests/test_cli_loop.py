from __future__ import annotations

import asyncio
import unittest
from zoneinfo import ZoneInfo

from bluetag.cli import UsageLoopSource, _run_loop_cycle


class CliLoopTests(unittest.TestCase):
    def test_run_loop_cycle_alternates_sources(self) -> None:
        events: list[tuple[str, object]] = []

        def make_source(name: str) -> UsageLoopSource:
            def fetch(*, timeout: float):
                events.append(("fetch", name))
                return {"name": name, "timeout": timeout}

            def render(payload, tzinfo, *, font_path=None):
                events.append(("render", payload["name"]))
                self.assertEqual(tzinfo, ZoneInfo("UTC"))
                self.assertIsNone(font_path)
                return f"image:{payload['name']}"

            return UsageLoopSource(
                name=name,
                timeout=9.0,
                fetch=fetch,
                render=render,
            )

        async def push_image(image):
            events.append(("push", image))
            return True

        async def sleep(seconds: float):
            events.append(("sleep", seconds))

        asyncio.run(
            _run_loop_cycle(
                sources=[make_source("codex"), make_source("claude")],
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=90,
                sleep=sleep,
            )
        )

        self.assertEqual(
            events,
            [
                ("fetch", "codex"),
                ("render", "codex"),
                ("push", "image:codex"),
                ("sleep", 90),
                ("fetch", "claude"),
                ("render", "claude"),
                ("push", "image:claude"),
                ("sleep", 90),
            ],
        )

    def test_run_loop_cycle_continues_after_source_failure(self) -> None:
        events: list[tuple[str, object]] = []

        def broken_fetch(*, timeout: float):
            events.append(("fetch", "codex"))
            raise RuntimeError("boom")

        def render_never_called(payload, tzinfo, *, font_path=None):
            raise AssertionError("render should not be called")

        def ok_fetch(*, timeout: float):
            events.append(("fetch", "claude"))
            return {"name": "claude"}

        def ok_render(payload, tzinfo, *, font_path=None):
            events.append(("render", payload["name"]))
            return "image:claude"

        async def push_image(image):
            events.append(("push", image))
            return True

        async def sleep(seconds: float):
            events.append(("sleep", seconds))

        asyncio.run(
            _run_loop_cycle(
                sources=[
                    UsageLoopSource(
                        name="codex",
                        timeout=9.0,
                        fetch=broken_fetch,
                        render=render_never_called,
                    ),
                    UsageLoopSource(
                        name="claude",
                        timeout=9.0,
                        fetch=ok_fetch,
                        render=ok_render,
                    ),
                ],
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=30,
                sleep=sleep,
            )
        )

        self.assertEqual(
            events,
            [
                ("fetch", "codex"),
                ("sleep", 30),
                ("fetch", "claude"),
                ("render", "claude"),
                ("push", "image:claude"),
                ("sleep", 30),
            ],
        )


if __name__ == "__main__":
    unittest.main()
