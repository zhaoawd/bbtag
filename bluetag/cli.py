"""
CLI 入口 — bluetag 命令行工具
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image

from bluetag import __version__
from bluetag.ble import BleDependencyError
from bluetag.image import (
    indices_to_image,
    layer_to_bytes,
    pack_2bpp,
    process_bicolor_image,
    quantize,
    unpack_2bpp,
)
from bluetag.protocol import build_frame, packetize, parse_mac_suffix
from bluetag.screens import ScreenProfile, get_screen_profile
from bluetag.text import render_text
from bluetag.transfer import send_bicolor_image
from bluetag.usage_claude import (
    build_claude_panel_rows,
    build_claude_refresh_rows,
    fetch_claude_usage,
    render_claude_2_13,
    render_claude_2_9,
    render_claude_3_7,
)
from bluetag.usage_codex import (
    build_codex_panel_rows,
    build_codex_refresh_rows,
    fetch_codex_usage,
    render_codex_2_13,
    render_codex_2_9,
    render_codex_3_7,
)
from bluetag.usage_layout_2_9 import (
    PANEL_BAR_INNER_WIDTH_2_9,
    render_usage_panel_2_9,
)
from bluetag.usage_layout_3_7 import PANEL_BAR_INNER_WIDTH, render_usage_panel_3_7

DEFAULT_SCAN_TIMEOUT = 5.0
DEFAULT_SCAN_RETRIES = 3
DEFAULT_CONNECT_RETRIES = 3
DEFAULT_SCREEN = "3.7inch"
REFRESH_PERCENT_THRESHOLD = 2
REFRESH_BAR_PX_THRESHOLD = 3


@dataclass(frozen=True)
class UsageLoopSource:
    name: str
    timeout: float
    fetch: Callable[..., dict]
    refresh_rows: Callable[..., list[tuple[str, float]]]
    bar_inner_width: int
    render: Callable[..., Image.Image]


@dataclass(frozen=True)
class UsageRefreshRow:
    label: str
    left_percent_int: int
    bar_fill_px: int


@dataclass(frozen=True)
class UsageRefreshState:
    source: str
    screen: str
    rows: tuple[UsageRefreshRow, ...]


LayerBytes = tuple[bytes, bytes]
LoopPushResult = tuple[bool, LayerBytes | None]


def _default_text_title() -> str:
    return f"{date.today():%Y-%m-%d}"


def _resolve_profile(screen: str) -> ScreenProfile:
    try:
        return get_screen_profile(screen)
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def _save_device(device: dict, profile: ScreenProfile):
    """将设备信息写入对应屏幕的缓存文件。"""
    profile.cache_path.parent.mkdir(parents=True, exist_ok=True)
    profile.cache_path.write_text(f"{device['name']}\n{device['address']}\n")
    print(f"  💾 已保存到 {profile.cache_path}")


def _load_device(profile: ScreenProfile) -> dict | None:
    """从对应屏幕的缓存文件读取设备信息。"""
    if not profile.cache_path.exists():
        return None
    lines = profile.cache_path.read_text().strip().splitlines()
    if len(lines) >= 2:
        return {"name": lines[0], "address": lines[1]}
    return None


async def _find_target(args, profile: ScreenProfile) -> dict | None:
    from bluetag.ble import find_device

    if not args.device and not args.address:
        cached = _load_device(profile)
        if cached:
            print(
                f"使用 {profile.name} 缓存设备: {cached['name']} ({cached['address']})"
            )
            return cached

    print(f"扫描 {profile.name} 设备 ({profile.device_prefix}*)...")
    target = await find_device(
        device_name=args.device,
        device_address=args.address,
        timeout=DEFAULT_SCAN_TIMEOUT,
        scan_retries=DEFAULT_SCAN_RETRIES,
        prefixes=(profile.device_prefix,),
    )
    if target:
        _save_device(target, profile)
    return target


def _frame_progress(sent: int, total: int):
    if sent == total:
        print(f"\r✅ 发送完成! ({total} 包)")
    elif sent == 1 or sent % 10 == 0:
        print(f"\r  发送中 {sent}/{total}...", end="", flush=True)


def _layer_progress(layer_name: str, sent: int, total: int):
    if sent == total:
        print(f"\r✅ {layer_name}发送完成! ({total} 包)")
    elif sent == 1 or sent % 10 == 0:
        print(f"\r  {layer_name}发送中 {sent}/{total}...", end="", flush=True)


def _build_frame_preview_and_payload(
    img: Image.Image,
    profile: ScreenProfile,
) -> tuple[Image.Image, bytes]:
    prepared = img.convert("RGB")
    if profile.name == "3.7inch" and prepared.size == (416, 240):
        prepared = prepared.transpose(Image.Transpose.ROTATE_90)
    indices = quantize(prepared, flip=profile.mirror, size=profile.size)
    preview = indices_to_image(indices, size=profile.size)
    data_2bpp = pack_2bpp(indices)
    return preview, data_2bpp


def _build_layer_preview_and_payload(
    img: Image.Image,
    profile: ScreenProfile,
) -> tuple[Image.Image, bytes, bytes]:
    black_layer, red_layer, preview = process_bicolor_image(
        img,
        profile.name,
        threshold=128,
        dither=False,
        rotate=profile.rotate,
        mirror=profile.mirror,
        swap_wh=profile.swap_wh,
        detect_red=profile.detect_red,
    )
    black_data = layer_to_bytes(black_layer, profile.encoding)
    red_data = layer_to_bytes(red_layer, profile.encoding)
    return preview, black_data, red_data


async def _push_frame_image(
    profile: ScreenProfile,
    target: dict,
    data_2bpp: bytes,
    interval_ms: int,
) -> bool:
    from bluetag.ble import push

    mac_suffix = parse_mac_suffix(target["name"])
    frame = build_frame(mac_suffix, data_2bpp)
    packets = packetize(frame)
    print(
        f"连接 {target['name']} [{profile.name}], {len(frame)} bytes, {len(packets)} 包"
    )

    return await push(
        packets,
        device_address=target["address"],
        packet_interval=interval_ms / 1000,
        on_progress=_frame_progress,
        prefixes=(profile.device_prefix,),
        scan_timeout=DEFAULT_SCAN_TIMEOUT,
    )


async def _push_layer_image(
    profile: ScreenProfile,
    target: dict,
    black_data: bytes,
    red_data: bytes,
    interval_ms: int,
    prev_black_data: bytes | None = None,
    prev_red_data: bytes | None = None,
) -> bool:
    from bluetag.ble import connect_session

    session = await connect_session(
        target.get("_ble_device") or target["address"],
        timeout=20.0,
        connect_retries=DEFAULT_CONNECT_RETRIES,
    )
    if not session:
        return False

    try:
        print(
            f"连接 {target['name']} [{profile.name}], "
            f"黑层 {len(black_data)} bytes, 红层 {len(red_data)} bytes"
        )
        return await send_bicolor_image(
            session,
            black_data,
            red_data,
            delay_ms=interval_ms,
            settle_ms=profile.settle_ms,
            flush_every=profile.flush_every,
            initial_repeat_packets=profile.initial_repeat_packets,
            on_progress=_layer_progress,
            prev_black_data=prev_black_data,
            prev_red_data=prev_red_data,
        )
    finally:
        await session.close()


async def _push_rendered_image(
    profile: ScreenProfile,
    target: dict,
    image: Image.Image,
    prev_black_data: bytes | None = None,
    prev_red_data: bytes | None = None,
) -> bool:
    interval_ms = profile.default_interval_ms
    if profile.transport == "frame":
        _preview, data_2bpp = _build_frame_preview_and_payload(image, profile)
        return await _push_frame_image(profile, target, data_2bpp, interval_ms)

    _preview, black_data, red_data = _build_layer_preview_and_payload(image, profile)
    return await _push_layer_image(
        profile,
        target,
        black_data,
        red_data,
        interval_ms,
        prev_black_data=prev_black_data,
        prev_red_data=prev_red_data,
    )


def _resolve_timezone(name: str | None):
    if not name:
        return datetime.now().astimezone().tzinfo or timezone.utc
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        print(f"❌ Unknown timezone: {name}", file=sys.stderr)
        raise SystemExit(2) from exc


def _current_log_time() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _loop_log(message: str) -> None:
    print(f"[{_current_log_time()}] {message}")


def _loop_error(message: str) -> None:
    print(f"[{_current_log_time()}] {message}", file=sys.stderr)


def _build_loop_sources(screen: str) -> list[UsageLoopSource]:
    if screen == "2.13inch":
        return [
            UsageLoopSource(
                name="codex",
                timeout=30.0,
                fetch=fetch_codex_usage,
                refresh_rows=build_codex_refresh_rows,
                bar_inner_width=232,
                render=render_codex_2_13,
            ),
            UsageLoopSource(
                name="claude",
                timeout=10.0,
                fetch=fetch_claude_usage,
                refresh_rows=lambda payload: build_claude_refresh_rows(
                    payload, include_sonnet=False
                ),
                bar_inner_width=232,
                render=render_claude_2_13,
            ),
        ]

    if screen == "2.9inch":
        last_payloads: dict[str, dict] = {"claude": {}, "codex": {}}

        def fetch_overview(*, timeout: float) -> dict[str, dict]:
            del timeout
            try:
                last_payloads["claude"] = fetch_claude_usage(timeout=10.0)
            except Exception as exc:
                _loop_error(f"⚠️ claude fetch failed in overview: {exc}")
            
            try:
                last_payloads["codex"] = fetch_codex_usage(timeout=30.0)
            except Exception as exc:
                _loop_error(f"⚠️ codex fetch failed in overview: {exc}")
            
            if not last_payloads["claude"] and not last_payloads["codex"]:
                raise RuntimeError("Both claude and codex fetch failed")

            return {
                "claude": last_payloads["claude"],
                "codex": last_payloads["codex"],
            }

        def refresh_overview_rows(payload: dict[str, dict]) -> list[tuple[str, float]]:
            claude_payload = payload.get("claude", {})
            codex_payload = payload.get("codex", {})
            rows = [
                (f"claude:{label}", left_percent)
                for label, left_percent in build_claude_refresh_rows(
                    claude_payload, include_sonnet=False
                )
            ]
            rows.extend(
                (f"codex:{label}", left_percent)
                for label, left_percent in build_codex_refresh_rows(codex_payload)
            )
            return rows

        def render_overview(
            payload: dict[str, dict], tzinfo, *, font_path: str | None = None
        ):
            return render_usage_panel_2_9(
                sections=[
                    (
                        "Claude",
                        build_claude_panel_rows(
                            payload.get("claude", {}),
                            tzinfo,
                            include_sonnet=False,
                        ),
                    ),
                    ("Codex", build_codex_panel_rows(payload.get("codex", {}), tzinfo)),
                ],
                tzinfo=tzinfo,
                font_path=font_path,
            )

        return [
            UsageLoopSource(
                name="overview",
                timeout=30.0,
                fetch=fetch_overview,
                refresh_rows=refresh_overview_rows,
                bar_inner_width=PANEL_BAR_INNER_WIDTH_2_9,
                render=render_overview,
            )
        ]

    last_payloads_3_7: dict[str, dict] = {"claude": {}, "codex": {}}

    def fetch_overview(*, timeout: float) -> dict[str, dict]:
        del timeout
        try:
            last_payloads_3_7["claude"] = fetch_claude_usage(timeout=10.0)
        except Exception as exc:
            _loop_error(f"⚠️ claude fetch failed in overview: {exc}")
        
        try:
            last_payloads_3_7["codex"] = fetch_codex_usage(timeout=30.0)
        except Exception as exc:
            _loop_error(f"⚠️ codex fetch failed in overview: {exc}")
        
        if not last_payloads_3_7["claude"] and not last_payloads_3_7["codex"]:
            raise RuntimeError("Both claude and codex fetch failed")

        return {
            "claude": last_payloads_3_7["claude"],
            "codex": last_payloads_3_7["codex"],
        }

    def refresh_overview_rows(payload: dict[str, dict]) -> list[tuple[str, float]]:
        claude_payload = payload.get("claude", {})
        codex_payload = payload.get("codex", {})
        rows = [
            (f"claude:{label}", left_percent)
            for label, left_percent in build_claude_refresh_rows(
                claude_payload, include_sonnet=False
            )
        ]
        rows.extend(
            (f"codex:{label}", left_percent)
            for label, left_percent in build_codex_refresh_rows(codex_payload)
        )
        return rows

    def render_overview(payload: dict[str, dict], tzinfo, *, font_path: str | None = None):
        return render_usage_panel_3_7(
            sections=[
                (
                    "Claude",
                    build_claude_panel_rows(
                        payload.get("claude", {}),
                        tzinfo,
                        include_sonnet=False,
                    ),
                ),
                ("OpenAI Codex", build_codex_panel_rows(payload.get("codex", {}), tzinfo)),
            ],
            tzinfo=tzinfo,
            font_path=font_path,
        )

    return [
        UsageLoopSource(
            name="overview",
            timeout=30.0,
            fetch=fetch_overview,
            refresh_rows=refresh_overview_rows,
            bar_inner_width=PANEL_BAR_INNER_WIDTH,
            render=render_overview,
        )
    ]


def _build_refresh_state(
    *,
    source_name: str,
    screen_name: str,
    rows: Sequence[tuple[str, float]],
    bar_inner_width: int,
) -> UsageRefreshState:
    refresh_rows = tuple(
        UsageRefreshRow(
            label=label,
            left_percent_int=int(round(left_percent)),
            bar_fill_px=round(
                bar_inner_width * max(0.0, min(100.0, left_percent)) / 100.0
            ),
        )
        for label, left_percent in rows
    )
    return UsageRefreshState(
        source=source_name,
        screen=screen_name,
        rows=refresh_rows,
    )


def _refresh_reason(
    previous: UsageRefreshState | None,
    current: UsageRefreshState,
) -> str | None:
    if previous is None:
        return "first frame"
    if len(previous.rows) != len(current.rows):
        return "row count changed"

    for old_row, new_row in zip(previous.rows, current.rows):
        if old_row.label != new_row.label:
            return "labels changed"
        if (
            abs(old_row.left_percent_int - new_row.left_percent_int)
            >= REFRESH_PERCENT_THRESHOLD
        ):
            return "percent changed"
        if (
            abs(old_row.bar_fill_px - new_row.bar_fill_px)
            >= REFRESH_BAR_PX_THRESHOLD
        ):
            return "bar width changed"
    return None


async def _run_loop_cycle(
    *,
    sources: Sequence[UsageLoopSource],
    screen_name: str,
    tzinfo,
    font_path: str | None,
    push_image: Callable[
        [str, Image.Image, bytes | None, bytes | None],
        Awaitable[LoopPushResult],
    ],
    interval_seconds: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    refresh_states: dict[str, UsageRefreshState] | None = None,
    prev_layer_bytes: dict[str, tuple[bytes, bytes]] | None = None,
    push_counts: dict[str, int] | None = None,
    full_refresh_every: int = 5,
    supports_partial_diff: bool = True,
) -> dict[str, UsageRefreshState]:
    states = {} if refresh_states is None else dict(refresh_states)
    layer_bytes = {} if prev_layer_bytes is None else prev_layer_bytes
    partial_counts = {} if push_counts is None else push_counts

    for source in sources:
        try:
            payload = source.fetch(timeout=source.timeout)
            current_state = _build_refresh_state(
                source_name=source.name,
                screen_name=screen_name,
                rows=source.refresh_rows(payload),
                bar_inner_width=source.bar_inner_width,
            )
        except Exception as exc:
            _loop_error(f"❌ {source.name} usage failed: {exc}")
            await sleep(interval_seconds)
            continue

        previous = states.get(source.name)
        reason = _refresh_reason(previous, current_state)
        if reason is None:
            _loop_log(f"skip {source.name} refresh: no meaningful value change")
            await sleep(interval_seconds)
            continue

        try:
            image = source.render(payload, tzinfo, font_path=font_path)
            force_full = not supports_partial_diff or (
                full_refresh_every > 0
                and partial_counts.get(source.name, 0) >= full_refresh_every
            )
            if force_full:
                prev_black = None
                prev_red = None
            else:
                prev_black, prev_red = layer_bytes.get(source.name, (None, None))
            ok, latest_layer_bytes = await push_image(
                source.name, image, prev_black, prev_red
            )
        except Exception as exc:
            _loop_error(f"❌ {source.name} push failed: {exc}")
            ok = False
            latest_layer_bytes = None

        if ok:
            states[source.name] = current_state
            if latest_layer_bytes is not None:
                layer_bytes[source.name] = latest_layer_bytes
            if force_full:
                partial_counts[source.name] = 0
            else:
                partial_counts[source.name] = partial_counts.get(source.name, 0) + 1
            _loop_log(f"push {source.name} refresh: {reason}")
        else:
            _loop_error(f"❌ {source.name} push failed")
        await sleep(interval_seconds)

    return states


def cmd_scan(args):
    from bluetag.ble import scan

    profile = _resolve_profile(args.screen)
    retries = args.retries

    async def _scan():
        all_devices: list[dict] = []
        for attempt in range(retries):
            if attempt == 0:
                print(f"扫描蓝签设备 ({profile.name}, {args.timeout}s)...")
            else:
                print(f"  未发现，重试 ({attempt + 1}/{retries})...")
            devices = await scan(
                timeout=args.timeout,
                prefixes=(profile.device_prefix,),
                debug_raw=args.debug_raw,
            )
            if devices:
                all_devices = devices
                break
        if not all_devices:
            print("  未发现蓝签设备")
            return
        for device in all_devices:
            print(
                f"  📺 {device['name']}  ({device['address']})  RSSI: {device['rssi']}"
            )
        _save_device(all_devices[0], profile)

    asyncio.run(_scan())


def cmd_push(args):
    profile = _resolve_profile(args.screen)
    interval_ms = args.interval or profile.default_interval_ms
    img = Image.open(args.image)

    if profile.transport == "frame":
        preview, data_2bpp = _build_frame_preview_and_payload(img, profile)
        preview.show()

        async def _push():
            target = await _find_target(args, profile)
            if not target:
                print("❌ 未找到设备")
                return False

            ok = await _push_frame_image(profile, target, data_2bpp, interval_ms)
            if not ok:
                print("❌ 发送失败")
            return ok

    else:
        preview, black_data, red_data = _build_layer_preview_and_payload(img, profile)
        preview.show()

        async def _push():
            target = await _find_target(args, profile)
            if not target:
                print("❌ 未找到设备")
                return False

            ok = await _push_layer_image(
                profile,
                target,
                black_data,
                red_data,
                interval_ms,
            )
            if not ok:
                print("❌ 发送失败")
            return ok

    asyncio.run(_push())


def cmd_text(args):
    """渲染文字并推送到设备"""
    profile = _resolve_profile(args.screen)
    interval_ms = args.interval or profile.default_interval_ms

    body = args.body.replace("\\n", "\n")
    title = args.title

    rendered = render_text(
        body=body,
        title=title,
        title_color=args.title_color,
        body_color=args.body_color,
        separator_color=args.separator_color,
        font_path=args.font,
        align=args.align,
        screen=profile.name,
    )

    if profile.transport == "frame":
        preview, data_2bpp = _build_frame_preview_and_payload(rendered, profile)
    else:
        preview, black_data, red_data = _build_layer_preview_and_payload(
            rendered, profile
        )

    if args.preview_only:
        if profile.mirror:
            preview = preview.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        preview.show()
        print("仅预览模式，不推送")
        return

    async def _push():
        target = await _find_target(args, profile)
        if not target:
            print("❌ 未找到设备")
            return False

        if profile.transport == "frame":
            ok = await _push_frame_image(profile, target, data_2bpp, interval_ms)
        else:
            ok = await _push_layer_image(
                profile,
                target,
                black_data,
                red_data,
                interval_ms,
            )

        if not ok:
            print("❌ 发送失败")
        return ok

    asyncio.run(_push())


def cmd_loop(args):
    profile = _resolve_profile(args.screen)
    tzinfo = _resolve_timezone(args.timezone)
    sources = _build_loop_sources(profile.name)
    supports_partial_diff = profile.supports_partial_diff

    async def _loop():
        target = await _find_target(args, profile)
        if not target:
            _loop_error("❌ 未找到设备")
            return

        _loop_log(
            f"开始循环刷新 {profile.name} 设备 {target['name']} ({target['address']}), "
            f"间隔 {args.interval}s"
        )

        prev_layer_bytes: dict[str, tuple[bytes, bytes]] = {}
        push_counts: dict[str, int] = {}

        async def _push(
            source_name: str,
            image: Image.Image,
            prev_black: bytes | None = None,
            prev_red: bytes | None = None,
        ) -> LoopPushResult:
            if profile.transport == "frame":
                ok = await _push_rendered_image(profile, target, image)
                return ok, None

            _preview, black_data, red_data = _build_layer_preview_and_payload(
                image, profile
            )
            ok = await _push_layer_image(
                profile,
                target,
                black_data,
                red_data,
                profile.default_interval_ms,
                prev_black_data=prev_black,
                prev_red_data=prev_red,
            )
            if ok:
                return True, (black_data, red_data)
            return False, None

        refresh_states: dict[str, UsageRefreshState] = {}
        while True:
            refresh_states = await _run_loop_cycle(
                sources=sources,
                screen_name=profile.name,
                tzinfo=tzinfo,
                font_path=args.font,
                push_image=_push,
                interval_seconds=float(args.interval),
                refresh_states=refresh_states,
                prev_layer_bytes=prev_layer_bytes,
                push_counts=push_counts,
                full_refresh_every=args.full_refresh_every,
                supports_partial_diff=supports_partial_diff,
            )

    try:
        asyncio.run(_loop())
    except KeyboardInterrupt:
        _loop_log("已停止循环刷新")


def cmd_decode(args):
    """从 btsnoop HCI 日志解码图像 (调试用)"""
    import subprocess

    import lzo

    result = subprocess.run(
        [
            "tshark",
            "-r",
            args.log,
            "-Y",
            "btatt.opcode == 0x52 && btatt.handle == 0x0015",
            "-T",
            "fields",
            "-e",
            "btatt.value",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"❌ tshark 失败: {result.stderr}")
        return

    seen = set()
    payload = bytearray()
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line and line not in seen:
            seen.add(line)
            pkt = bytes.fromhex(line)
            if pkt not in (b"\x00\x00", b"\xff\xff"):
                payload.extend(pkt[3:-1])

    if len(payload) < 30:
        print("❌ 数据不足")
        return

    s1 = (payload[13] << 8) | payload[14]
    s2 = (payload[15] << 8) | payload[16]
    l1_lzo_size = (payload[25] << 8) | payload[26]
    l1_method = payload[29]
    l1_block = payload[30 : 30 + s1]

    l1_full = bytes([l1_method]) + bytes(l1_block[: l1_lzo_size - 1])
    l1_dec = lzo.decompress(l1_full, False, 20480)

    l1_remaining = l1_block[l1_lzo_size - 1 :]
    if l1_remaining[0] == 0x00:
        l2_meta = l1_remaining[1:]
    else:
        l2_meta = l1_remaining
    l2_method = l2_meta[-1]
    if len(l2_meta) == 5:
        l2_full_size = (l2_meta[0] << 8) | l2_meta[1]
    else:
        l2_full_size = l2_meta[0]

    l2_block = payload[30 + s1 : 30 + s1 + s2]
    l2_lzo_data = l2_block[: l2_full_size - 1]
    l2_full = bytes([l2_method]) + bytes(l2_lzo_data)
    l2_dec = lzo.decompress(l2_full, False, 4480)

    full_2bpp = l1_dec + l2_dec
    indices = unpack_2bpp(full_2bpp)
    img = indices_to_image(indices)

    output = args.output or (Path(args.log).stem + "_decoded.png")
    img.save(output)
    print(f"✅ 图像已保存: {output}")


def main():
    parser = argparse.ArgumentParser(
        prog="bluetag",
        description="BluETag — 蓝签电子墨水标签 BLE 图像推送工具",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command")

    screen_help = "屏幕尺寸: 3.7inch/3.7 或 2.13inch/2.13 (默认 3.7inch)"

    scan_p = sub.add_parser("scan", help="扫描附近的蓝签设备")
    scan_p.add_argument(
        "--timeout", "-t", type=float, default=5.0, help="扫描超时 (秒)"
    )
    scan_p.add_argument(
        "--retries", "-r", type=int, default=3, help="扫描重试次数 (默认 3)"
    )
    scan_p.add_argument(
        "--debug-raw",
        action="store_true",
        help="打印过滤前的原始 BLE 发现结果",
    )
    scan_p.add_argument("--screen", default=DEFAULT_SCREEN, help=screen_help)

    push_p = sub.add_parser("push", help="推送图片到设备")
    push_p.add_argument("image", help="图片文件路径")
    push_p.add_argument("--device", "-d", help="设备名")
    push_p.add_argument("--address", "-a", help="设备 BLE 地址")
    push_p.add_argument("--screen", default=DEFAULT_SCREEN, help=screen_help)
    push_p.add_argument(
        "--interval", "-i", type=int, help="包间隔 (ms，默认按屏幕选择)"
    )

    text_p = sub.add_parser("text", help="推送文字到设备 (自动排版)")
    text_p.add_argument("body", help="正文内容 (支持 \\n 换行)")
    default_title = _default_text_title()
    text_p.add_argument(
        "--title",
        "-T",
        default=default_title,
        help=f"标题 (默认 {default_title})",
    )
    text_p.add_argument(
        "--title-color",
        default="red",
        choices=["black", "red", "yellow"],
        help="标题颜色",
    )
    text_p.add_argument(
        "--body-color",
        default="black",
        choices=["black", "red", "yellow"],
        help="正文颜色",
    )
    text_p.add_argument(
        "--separator-color",
        default="yellow",
        choices=["black", "red", "yellow"],
        help="分隔线颜色",
    )
    text_p.add_argument(
        "--align", default="left", choices=["left", "center"], help="正文对齐"
    )
    text_p.add_argument("--font", help="自定义字体路径")
    text_p.add_argument(
        "--preview-only", action="store_true", help="仅生成预览图，不推送"
    )
    text_p.add_argument("--device", "-d", help="设备名")
    text_p.add_argument("--address", "-a", help="设备 BLE 地址")
    text_p.add_argument("--screen", default=DEFAULT_SCREEN, help=screen_help)
    text_p.add_argument(
        "--interval", "-i", type=int, help="包间隔 (ms，默认按屏幕选择)"
    )

    loop_p = sub.add_parser("loop", help="交替推送 Codex / Claude Code usage")
    loop_p.add_argument("--device", "-d", help="设备名")
    loop_p.add_argument("--address", "-a", help="设备 BLE 地址")
    loop_p.add_argument(
        "--screen",
        required=True,
        help="屏幕尺寸: 3.7inch/3.7 或 2.13inch/2.13",
    )
    loop_p.add_argument(
        "--interval",
        type=int,
        default=300,
        help="刷新间隔 (秒，默认 300)",
    )
    loop_p.add_argument(
        "--full-refresh-every",
        type=int,
        default=5,
        help="每 N 次局部刷新后强制全刷一次 (默认 5，0 表示禁用)",
    )
    loop_p.add_argument("--timezone", help="时区，例如 Asia/Shanghai")
    loop_p.add_argument("--font", help="自定义字体路径")

    decode_p = sub.add_parser("decode", help="从抓包文件解码图片 (调试)")
    decode_p.add_argument("log", help="btsnoop HCI 日志文件")
    decode_p.add_argument("--output", "-o", help="输出图片路径")

    args = parser.parse_args()

    if args.command == "scan":
        try:
            cmd_scan(args)
        except BleDependencyError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
    elif args.command == "push":
        try:
            cmd_push(args)
        except BleDependencyError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
    elif args.command == "text":
        try:
            cmd_text(args)
        except BleDependencyError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
    elif args.command == "loop":
        try:
            cmd_loop(args)
        except BleDependencyError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
    elif args.command == "decode":
        cmd_decode(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
