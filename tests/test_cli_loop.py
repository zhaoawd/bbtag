from __future__ import annotations

import asyncio
import unittest
from zoneinfo import ZoneInfo

from bluetag.cli import (
    UsageLoopSource,
    _build_loop_sources,
    _build_refresh_state,
    _run_loop_cycle,
)


class CliLoopTests(unittest.TestCase):
    def test_build_loop_sources_3_7_uses_single_overview_panel(self) -> None:
        sources = _build_loop_sources("3.7inch")

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].name, "overview")

    def test_build_loop_sources_2_9_uses_single_overview_panel(self) -> None:
        sources = _build_loop_sources("2.9inch")

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].name, "overview")

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

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            events.append(("push", image))
            return True, None

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

    def test_run_loop_cycle_passes_prev_layer_bytes_for_partial_refresh(self) -> None:
        push_calls: list[tuple[str, object, bytes | None, bytes | None]] = []

        def fetch(*, timeout: float):
            return {"name": "codex"}

        def refresh_rows(payload):
            return [("5h limit", 57.0)]

        def render(payload, tzinfo, *, font_path=None):
            return "image:codex"

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            push_calls.append((source_name, image, prev_black, prev_red))
            return True, (b"new-black", b"new-red")

        async def sleep(_: float):
            return None

        source = UsageLoopSource(
            name="codex",
            timeout=9.0,
            fetch=fetch,
            refresh_rows=refresh_rows,
            bar_inner_width=100,
            render=render,
        )
        prev_layer_bytes = {"codex": (b"old-black", b"old-red")}
        push_counts = {"codex": 2}
        refresh_states = {
            "codex": _build_refresh_state(
                source_name="codex",
                screen_name="2.13inch",
                rows=[("5h limit", 54.8)],
                bar_inner_width=100,
            )
        }

        asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
                refresh_states=refresh_states,
                prev_layer_bytes=prev_layer_bytes,
                push_counts=push_counts,
                full_refresh_every=5,
            )
        )

        self.assertEqual(
            push_calls,
            [("codex", "image:codex", b"old-black", b"old-red")],
        )
        self.assertEqual(prev_layer_bytes["codex"], (b"new-black", b"new-red"))
        self.assertEqual(push_counts["codex"], 3)

    def test_run_loop_cycle_forces_full_refresh_after_threshold(self) -> None:
        push_calls: list[tuple[str, object, bytes | None, bytes | None]] = []

        def fetch(*, timeout: float):
            return {"name": "codex"}

        def refresh_rows(payload):
            return [("5h limit", 57.0)]

        def render(payload, tzinfo, *, font_path=None):
            return "image:codex"

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            push_calls.append((source_name, image, prev_black, prev_red))
            return True, (b"full-black", b"full-red")

        async def sleep(_: float):
            return None

        source = UsageLoopSource(
            name="codex",
            timeout=9.0,
            fetch=fetch,
            refresh_rows=refresh_rows,
            bar_inner_width=100,
            render=render,
        )
        prev_layer_bytes = {"codex": (b"old-black", b"old-red")}
        push_counts = {"codex": 5}
        refresh_states = {
            "codex": _build_refresh_state(
                source_name="codex",
                screen_name="2.13inch",
                rows=[("5h limit", 54.8)],
                bar_inner_width=100,
            )
        }

        asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.13inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
                refresh_states=refresh_states,
                prev_layer_bytes=prev_layer_bytes,
                push_counts=push_counts,
                full_refresh_every=5,
            )
        )

        self.assertEqual(
            push_calls,
            [("codex", "image:codex", None, None)],
        )
        self.assertEqual(prev_layer_bytes["codex"], (b"full-black", b"full-red"))
        self.assertEqual(push_counts["codex"], 0)

    def test_run_loop_cycle_disables_partial_diff_when_profile_does_not_support_it(self) -> None:
        push_calls: list[tuple[str, object, bytes | None, bytes | None]] = []

        def fetch(*, timeout: float):
            return {"name": "codex"}

        def refresh_rows(payload):
            return [("5h limit", 57.0)]

        def render(payload, tzinfo, *, font_path=None):
            return "image:codex"

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            push_calls.append((source_name, image, prev_black, prev_red))
            return True, (b"new-black", b"new-red")

        async def sleep(_: float):
            return None

        source = UsageLoopSource(
            name="codex",
            timeout=9.0,
            fetch=fetch,
            refresh_rows=refresh_rows,
            bar_inner_width=100,
            render=render,
        )
        prev_layer_bytes = {"codex": (b"old-black", b"old-red")}
        push_counts = {"codex": 2}
        refresh_states = {
            "codex": _build_refresh_state(
                source_name="codex",
                screen_name="2.9inch",
                rows=[("5h limit", 54.8)],
                bar_inner_width=100,
            )
        }

        asyncio.run(
            _run_loop_cycle(
                sources=[source],
                screen_name="2.9inch",
                tzinfo=ZoneInfo("UTC"),
                font_path=None,
                push_image=push_image,
                interval_seconds=10,
                sleep=sleep,
                refresh_states=refresh_states,
                prev_layer_bytes=prev_layer_bytes,
                push_counts=push_counts,
                full_refresh_every=5,
                supports_partial_diff=False,
            )
        )

        self.assertEqual(
            push_calls,
            [("codex", "image:codex", None, None)],
        )
        self.assertEqual(prev_layer_bytes["codex"], (b"new-black", b"new-red"))
        self.assertEqual(push_counts["codex"], 0)

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

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            events.append(("push", image))
            return True, None

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

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            events.append(("push", image))
            return True, None

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

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            events.append(("push", image))
            return True, None

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

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            events.append(("push", image))
            return True, None

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

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            events.append(("push", image))
            return True, None

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

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            events.append(("push", image))
            return next(push_results), None

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

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            events.append(("push", image))
            return True, None

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
