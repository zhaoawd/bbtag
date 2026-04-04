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

            def refresh_rows(payload):
                return [(payload["name"], 54.8)]

            def render(payload, tzinfo, *, font_path=None):
                events.append(("render", payload["name"]))
                self.assertEqual(tzinfo, ZoneInfo("UTC"))
                self.assertIsNone(font_path)
                return f"image:{payload['name']}"

            return UsageLoopSource(
                name=name,
                timeout=9.0,
                fetch=fetch,
                refresh_rows=refresh_rows,
                bar_inner_width=100,
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
                screen_name="2.13inch",
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

        def broken_refresh_rows(payload):
            raise AssertionError("refresh_rows should not be called")

        def render_never_called(payload, tzinfo, *, font_path=None):
            raise AssertionError("render should not be called")

        def ok_fetch(*, timeout: float):
            events.append(("fetch", "claude"))
            return {"name": "claude"}

        def ok_refresh_rows(payload):
            return [(payload["name"], 54.8)]

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
                        refresh_rows=broken_refresh_rows,
                        bar_inner_width=100,
                        render=render_never_called,
                    ),
                    UsageLoopSource(
                        name="claude",
                        timeout=9.0,
                        fetch=ok_fetch,
                        refresh_rows=ok_refresh_rows,
                        bar_inner_width=100,
                        render=ok_render,
                    ),
                ],
                screen_name="2.13inch",
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

    def test_run_loop_cycle_skips_push_when_refresh_state_is_unchanged(self) -> None:
        events: list[tuple[str, object]] = []

        def fetch(*, timeout: float):
            events.append(("fetch", "codex"))
            return {"name": "codex"}

        def refresh_rows(payload):
            return [("5h limit", 54.8)]

        def render(payload, tzinfo, *, font_path=None):
            events.append(("render", payload["name"]))
            return "image:codex"

        async def push_image(image):
            events.append(("push", image))
            return True

        async def sleep(seconds: float):
            events.append(("sleep", seconds))

        source = UsageLoopSource(
            name="codex",
            timeout=9.0,
            fetch=fetch,
            refresh_rows=refresh_rows,
            bar_inner_width=100,
            render=render,
        )

        states = asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
            )
        )
        states = asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
                refresh_states=states,
            )
        )

        self.assertEqual(
            events,
            [
                ("fetch", "codex"),
                ("render", "codex"),
                ("push", "image:codex"),
                ("sleep", 10),
                ("fetch", "codex"),
                ("sleep", 10),
            ],
        )

    def test_run_loop_cycle_pushes_when_bar_width_changes(self) -> None:
        events: list[tuple[str, object]] = []
        percents = iter([54.1, 55.7])

        def fetch(*, timeout: float):
            events.append(("fetch", "codex"))
            return {"name": "codex"}

        def refresh_rows(payload):
            return [("5h limit", next(percents))]

        def render(payload, tzinfo, *, font_path=None):
            events.append(("render", payload["name"]))
            return "image:codex"

        async def push_image(image):
            events.append(("push", image))
            return True

        async def sleep(seconds: float):
            events.append(("sleep", seconds))

        source = UsageLoopSource(
            name="codex",
            timeout=9.0,
            fetch=fetch,
            refresh_rows=refresh_rows,
            bar_inner_width=200,
            render=render,
        )

        states = asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
            )
        )
        asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
                refresh_states=states,
            )
        )

        self.assertEqual(
            events,
            [
                ("fetch", "codex"),
                ("render", "codex"),
                ("push", "image:codex"),
                ("sleep", 10),
                ("fetch", "codex"),
                ("render", "codex"),
                ("push", "image:codex"),
                ("sleep", 10),
            ],
        )

    def test_run_loop_cycle_skips_one_percent_change_below_threshold(self) -> None:
        events: list[tuple[str, object]] = []
        percents = iter([100.0, 99.0])

        def fetch(*, timeout: float):
            events.append(("fetch", "codex"))
            return {"name": "codex"}

        def refresh_rows(payload):
            return [("5h limit", next(percents))]

        def render(payload, tzinfo, *, font_path=None):
            events.append(("render", payload["name"]))
            return "image:codex"

        async def push_image(image):
            events.append(("push", image))
            return True

        async def sleep(seconds: float):
            events.append(("sleep", seconds))

        source = UsageLoopSource(
            name="codex",
            timeout=9.0,
            fetch=fetch,
            refresh_rows=refresh_rows,
            bar_inner_width=100,
            render=render,
        )

        states = asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
            )
        )
        asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
                refresh_states=states,
            )
        )

        self.assertEqual(
            events,
            [
                ("fetch", "codex"),
                ("render", "codex"),
                ("push", "image:codex"),
                ("sleep", 10),
                ("fetch", "codex"),
                ("sleep", 10),
            ],
        )

    def test_run_loop_cycle_pushes_when_bar_px_changes_by_threshold(self) -> None:
        events: list[tuple[str, object]] = []
        percents = iter([100.0, 97.0])

        def fetch(*, timeout: float):
            events.append(("fetch", "codex"))
            return {"name": "codex"}

        def refresh_rows(payload):
            return [("5h limit", next(percents))]

        def render(payload, tzinfo, *, font_path=None):
            events.append(("render", payload["name"]))
            return "image:codex"

        async def push_image(image):
            events.append(("push", image))
            return True

        async def sleep(seconds: float):
            events.append(("sleep", seconds))

        source = UsageLoopSource(
            name="codex",
            timeout=9.0,
            fetch=fetch,
            refresh_rows=refresh_rows,
            bar_inner_width=100,
            render=render,
        )

        states = asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
            )
        )
        asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
                refresh_states=states,
            )
        )

        self.assertEqual(
            events,
            [
                ("fetch", "codex"),
                ("render", "codex"),
                ("push", "image:codex"),
                ("sleep", 10),
                ("fetch", "codex"),
                ("render", "codex"),
                ("push", "image:codex"),
                ("sleep", 10),
            ],
        )

    def test_run_loop_cycle_does_not_update_state_after_failed_push(self) -> None:
        events: list[tuple[str, object]] = []

        def fetch(*, timeout: float):
            events.append(("fetch", "codex"))
            return {"name": "codex"}

        def refresh_rows(payload):
            return [("5h limit", 54.8)]

        def render(payload, tzinfo, *, font_path=None):
            events.append(("render", payload["name"]))
            return "image:codex"

        push_results = iter([False, True])

        async def push_image(image):
            events.append(("push", image))
            return next(push_results)

        async def sleep(seconds: float):
            events.append(("sleep", seconds))

        source = UsageLoopSource(
            name="codex",
            timeout=9.0,
            fetch=fetch,
            refresh_rows=refresh_rows,
            bar_inner_width=100,
            render=render,
        )

        states = asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
            )
        )
        self.assertEqual(states, {})

        states = asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
                refresh_states=states,
            )
        )

        self.assertEqual(
            events,
            [
                ("fetch", "codex"),
                ("render", "codex"),
                ("push", "image:codex"),
                ("sleep", 10),
                ("fetch", "codex"),
                ("render", "codex"),
                ("push", "image:codex"),
                ("sleep", 10),
            ],
        )

    def test_run_loop_cycle_ignores_reset_text_changes(self) -> None:
        events: list[tuple[str, object]] = []
        reset_texts = iter(["resets 14:00", "resets 14:01"])

        def fetch(*, timeout: float):
            events.append(("fetch", "codex"))
            return {"name": "codex"}

        def refresh_rows(payload):
            return [("5h limit", 54.8)]

        def render(payload, tzinfo, *, font_path=None):
            events.append(("render", payload["name"]))
            next(reset_texts)
            return "image:codex"

        async def push_image(image):
            events.append(("push", image))
            return True

        async def sleep(seconds: float):
            events.append(("sleep", seconds))

        source = UsageLoopSource(
            name="codex",
            timeout=9.0,
            fetch=fetch,
            refresh_rows=refresh_rows,
            bar_inner_width=100,
            render=render,
        )

        states = asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
            )
        )
        asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
                refresh_states=states,
            )
        )

        self.assertEqual(
            events,
            [
                ("fetch", "codex"),
                ("render", "codex"),
                ("push", "image:codex"),
                ("sleep", 10),
                ("fetch", "codex"),
                ("sleep", 10),
            ],
        )


    def test_run_loop_cycle_ignores_resets_text_changes(self) -> None:
        events: list[tuple[str, object]] = []
        resets = iter(["resets 18:00", "resets 19:00"])

        def fetch(*, timeout: float):
            events.append(("fetch", "codex"))
            return {"name": "codex"}

        def refresh_rows(payload):
            next(resets)
            return [("5h limit", 54.8)]

        def render(payload, tzinfo, *, font_path=None):
            events.append(("render", payload["name"]))
            return "image:codex"

        async def push_image(image):
            events.append(("push", image))
            return True

        async def sleep(seconds: float):
            events.append(("sleep", seconds))

        source = UsageLoopSource(
            name="codex",
            timeout=9.0,
            fetch=fetch,
            refresh_rows=refresh_rows,
            bar_inner_width=100,
            render=render,
        )

        states = asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
            )
        )
        asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
                refresh_states=states,
            )
        )

        self.assertEqual(
            events,
            [
                ("fetch", "codex"),
                ("render", "codex"),
                ("push", "image:codex"),
                ("sleep", 10),
                ("fetch", "codex"),
                ("sleep", 10),
            ],
        )


if __name__ == "__main__":
    unittest.main()
