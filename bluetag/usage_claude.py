"""Claude Code usage fetching and rendering helpers."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image, ImageDraw, ImageFont

API_URL = "https://api.anthropic.com/api/oauth/usage"
API_BETA = "oauth-2025-04-20"
WIDTH_2_13 = 250
HEIGHT_2_13 = 122
WIDTH_3_7 = 416
HEIGHT_3_7 = 240

_FONT_DIR = Path(__file__).parent / "fonts"
_FONT_SEARCH = [
    str(_FONT_DIR / "AlibabaPuHuiTi-Bold.ttf"),
    str(_FONT_DIR / "AlibabaPuHuiTi-Regular.ttf"),
    "/System/Library/Fonts/Supplemental/Menlo.ttc",
    "/System/Library/Fonts/Monaco.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "C:\\Windows\\Fonts\\consola.ttf",
]


class ClaudeUsageError(RuntimeError):
    """Raised when Claude usage cannot be loaded or rendered."""


@dataclass(frozen=True)
class UsageRow:
    label: str
    left_percent: float
    used_percent: float
    resets_text: str


def resolve_timezone(name: str | None):
    if not name:
        return datetime.now().astimezone().tzinfo or timezone.utc
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ClaudeUsageError(f"Unknown timezone: {name}") from exc


def _load_access_token_from_keychain() -> str:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ClaudeUsageError(
            "macOS `security` command not found. Claude usage fetch currently requires macOS Keychain."
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        suffix = f": {stderr}" if stderr else ""
        raise ClaudeUsageError(
            "Failed to read `Claude Code-credentials` from Keychain" + suffix
        )

    raw = result.stdout.strip()
    if not raw:
        raise ClaudeUsageError("Keychain item `Claude Code-credentials` was empty.")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ClaudeUsageError(f"Invalid Claude credential JSON: {exc}") from exc

    claude_oauth = payload.get("claudeAiOauth")
    if not isinstance(claude_oauth, dict):
        raise ClaudeUsageError("Missing `claudeAiOauth` in Claude credentials.")

    access_token = claude_oauth.get("accessToken")
    if not isinstance(access_token, str) or not access_token.strip():
        raise ClaudeUsageError("Missing `claudeAiOauth.accessToken` in Claude credentials.")
    return access_token.strip()


def fetch_claude_usage(*, timeout: float = 10.0) -> dict[str, Any]:
    access_token = _load_access_token_from_keychain()
    request = urllib.request.Request(
        API_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "anthropic-beta": API_BETA,
            "Accept": "application/json",
            "User-Agent": "bluetag-usage-claude",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace").strip()
        suffix = f": {details}" if details else ""
        raise ClaudeUsageError(f"Claude API returned HTTP {exc.code}{suffix}") from exc
    except urllib.error.URLError as exc:
        raise ClaudeUsageError(f"Request failed: {exc.reason}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ClaudeUsageError(f"Failed to parse API response as JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ClaudeUsageError("Expected a JSON object from Claude usage API.")
    return payload


def _parse_utilization(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return max(0.0, min(float(value), 100.0))
    return 0.0


def _format_reset_text(resets_at: Any, tzinfo) -> str:
    if not isinstance(resets_at, str) or not resets_at:
        return "resets unknown"

    iso_value = resets_at.replace("Z", "+00:00")
    try:
        reset_dt = datetime.fromisoformat(iso_value).astimezone(tzinfo)
    except ValueError:
        return "resets unknown"

    now_dt = datetime.now(tzinfo)
    time_text = reset_dt.strftime("%H:%M")
    if reset_dt.date() == now_dt.date():
        return f"resets {time_text}"
    if reset_dt.year == now_dt.year:
        return f"resets {time_text} on {reset_dt.day} {reset_dt.strftime('%b')}"
    return f"resets {time_text} on {reset_dt:%Y-%m-%d}"


def build_claude_rows(
    payload: dict[str, Any],
    tzinfo,
    *,
    include_sonnet: bool,
) -> list[UsageRow]:
    definitions = [
        ("five_hour", "5h session"),
        ("seven_day", "7d all models"),
    ]
    if include_sonnet:
        definitions.append(("seven_day_sonnet", "sonnet"))

    rows: list[UsageRow] = []
    for key, label in definitions:
        block = payload.get(key)
        if not isinstance(block, dict):
            continue
        used_percent = _parse_utilization(block.get("utilization"))
        rows.append(
            UsageRow(
                label=label,
                left_percent=max(0.0, min(100.0, 100.0 - used_percent)),
                used_percent=used_percent,
                resets_text=_format_reset_text(block.get("resets_at"), tzinfo),
            )
        )
    return rows


def _load_font(size: int, *, font_path: str | None = None) -> ImageFont.FreeTypeFont:
    if font_path:
        return ImageFont.truetype(font_path, size)
    for path in _FONT_SEARCH:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _new_crisp_canvas(
    width: int,
    height: int,
) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("1", (width, height), 1)
    draw = ImageDraw.Draw(image)
    draw.fontmode = "1"
    return image, draw


def _draw_small_progress_bar(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    percent: float,
) -> None:
    draw.rectangle((x, y, x + width, y + height), outline="black", width=1)
    inner_x0 = x + 2
    inner_y0 = y + 2
    inner_x1 = x + width - 1
    inner_y1 = y + height - 1
    inner_width = max(0, inner_x1 - inner_x0)
    fill_width = round(inner_width * max(0.0, min(100.0, percent)) / 100.0)
    if fill_width > 0:
        draw.rectangle(
            (inner_x0, inner_y0, inner_x0 + fill_width - 1, inner_y1),
            fill="black",
        )


def render_claude_2_13(payload: dict[str, Any], tzinfo, font_path: str | None = None) -> Image.Image:
    rows = build_claude_rows(payload, tzinfo, include_sonnet=False)
    image, draw = _new_crisp_canvas(WIDTH_2_13, HEIGHT_2_13)

    title_font = _load_font(13, font_path=font_path)
    label_font = _load_font(11, font_path=font_path)
    stat_font = _load_font(11, font_path=font_path)
    detail_font = _load_font(8, font_path=font_path)

    left_pad = 7
    right_pad = 7
    top_pad = 3
    bottom_pad = 4
    title_gap = 6
    gap = 9

    title_text = "claude code"
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]
    draw.text(
        ((WIDTH_2_13 - title_w) // 2, top_pad),
        title_text,
        fill=0,
        font=title_font,
    )

    rows_top = top_pad + title_h + title_gap
    row_count = max(1, len(rows))
    row_height = (
        HEIGHT_2_13 - rows_top - bottom_pad - gap * (row_count - 1)
    ) // row_count

    for index, row in enumerate(rows):
        row_top = rows_top + index * (row_height + gap)
        percent_text = f"{int(round(row.left_percent))}% left"

        label_bbox = draw.textbbox((0, 0), row.label, font=label_font)
        percent_bbox = draw.textbbox((0, 0), percent_text, font=stat_font)
        label_h = label_bbox[3] - label_bbox[1]
        percent_w = percent_bbox[2] - percent_bbox[0]

        draw.text((left_pad, row_top), row.label, fill=0, font=label_font)
        draw.text(
            (WIDTH_2_13 - right_pad - percent_w, row_top),
            percent_text,
            fill=0,
            font=stat_font,
        )

        bar_y = row_top + label_h + 3
        _draw_small_progress_bar(
            draw,
            x=left_pad,
            y=bar_y,
            width=WIDTH_2_13 - left_pad - right_pad - 1,
            height=12,
            percent=row.left_percent,
        )

        detail_bbox = draw.textbbox((0, 0), row.resets_text, font=detail_font)
        detail_w = detail_bbox[2] - detail_bbox[0]
        draw.text(
            (WIDTH_2_13 - right_pad - detail_w, bar_y + 16),
            row.resets_text,
            fill=0,
            font=detail_font,
        )

    return image.convert("RGB")


def _draw_large_progress_bar(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    left_percent: float,
    used_percent: float,
) -> None:
    bar_fill = "red" if used_percent >= 80.0 else "black"
    draw.rounded_rectangle((x, y, x + width, y + height), radius=8, outline="black", width=2)
    inner_x0 = x + 4
    inner_y0 = y + 4
    inner_x1 = x + width - 4
    inner_y1 = y + height - 4
    inner_width = max(0, inner_x1 - inner_x0)
    fill_width = round(inner_width * max(0.0, min(100.0, left_percent)) / 100.0)
    if fill_width > 0:
        draw.rounded_rectangle(
            (inner_x0, inner_y0, inner_x0 + fill_width - 1, inner_y1),
            radius=5,
            fill=bar_fill,
        )


def render_claude_3_7(payload: dict[str, Any], tzinfo, font_path: str | None = None) -> Image.Image:
    rows = build_claude_rows(payload, tzinfo, include_sonnet=True)
    image = Image.new("RGB", (WIDTH_3_7, HEIGHT_3_7), "white")
    draw = ImageDraw.Draw(image)

    header_h = 42
    draw.rectangle((0, 0, WIDTH_3_7, header_h), fill="black")

    title_font = _load_font(21, font_path=font_path)
    time_font = _load_font(14, font_path=font_path)
    section_font = _load_font(18, font_path=font_path)
    stat_font = _load_font(20, font_path=font_path)
    detail_font = _load_font(13, font_path=font_path)

    draw.text((14, 9), "CC USAGE", fill="white", font=title_font)
    draw.text(
        (WIDTH_3_7 - 78, 13),
        datetime.now(tzinfo).strftime("%H:%M"),
        fill="white",
        font=time_font,
    )

    top = header_h + 10
    segment_h = 58
    gap = 10
    labels = {
        "5h session": "SESSION",
        "7d all models": "ALL MODELS",
        "sonnet": "SONNET",
    }

    for index, row in enumerate(rows[:3]):
        y = top + index * (segment_h + gap)
        draw.rounded_rectangle(
            (10, y, WIDTH_3_7 - 10, y + segment_h),
            radius=10,
            outline="black",
            width=2,
        )
        header_label = labels.get(row.label, row.label.upper())
        draw.text((20, y + 8), header_label, fill="black", font=section_font)

        percent_text = f"{int(round(row.left_percent))}% left"
        percent_bbox = draw.textbbox((0, 0), percent_text, font=stat_font)
        percent_w = percent_bbox[2] - percent_bbox[0]
        draw.text(
            (WIDTH_3_7 - 20 - percent_w, y + 6),
            percent_text,
            fill="red" if row.used_percent >= 80.0 else "black",
            font=stat_font,
        )

        _draw_large_progress_bar(
            draw,
            x=20,
            y=y + 30,
            width=WIDTH_3_7 - 40,
            height=16,
            left_percent=row.left_percent,
            used_percent=row.used_percent,
        )
        draw.text((20, y + 47), row.resets_text, fill="black", font=detail_font)

    return image
