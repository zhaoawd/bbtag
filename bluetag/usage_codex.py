"""Codex usage fetching and rendering helpers."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image, ImageDraw, ImageFont

from bluetag.usage_layout_3_7 import (
    PanelRow,
    render_usage_panel_2_9,
    render_usage_panel_3_7,
    usage_color_for_percent,
)

DEFAULT_BASE_URL = "https://chatgpt.com/backend-api"
USAGE_PATH = "/wham/usage"
WIDTH_2_13 = 250
HEIGHT_2_13 = 122
WIDTH_2_9 = 296
HEIGHT_2_9 = 128
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
_MONO_FONT_SEARCH = [
    "/System/Library/Fonts/Supplemental/Menlo.ttc",
    "/System/Library/Fonts/Monaco.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "C:\\Windows\\Fonts\\consola.ttf",
]


class CodexUsageError(RuntimeError):
    """Raised when Codex usage cannot be loaded or rendered."""


@dataclass(frozen=True)
class CodexCredentials:
    access_token: str
    account_id: str | None = None


@dataclass(frozen=True)
class UsageRow:
    label: str
    left_percent: float
    used_percent: float
    resets_text: str


def codex_home_dir() -> Path:
    env_value = os.environ.get("CODEX_HOME", "").strip()
    if env_value:
        return Path(env_value).expanduser()
    return Path.home() / ".codex"


def get_auth_path(override: Path | None = None) -> Path:
    return (override or (codex_home_dir() / "auth.json")).expanduser()


def get_config_path(override: Path | None = None) -> Path:
    return (override or (codex_home_dir() / "config.toml")).expanduser()


def load_credentials(auth_path: Path | None = None) -> CodexCredentials:
    resolved_path = get_auth_path(auth_path)
    if not resolved_path.exists():
        raise CodexUsageError(
            f"Codex auth.json not found: {resolved_path}. Run `codex` and log in first."
        )

    try:
        data = json.loads(resolved_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CodexUsageError(f"Failed to read Codex credentials: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CodexUsageError(f"Invalid Codex credentials JSON: {exc}") from exc

    api_key = data.get("OPENAI_API_KEY")
    if isinstance(api_key, str) and api_key.strip():
        return CodexCredentials(access_token=api_key.strip())

    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        raise CodexUsageError("Codex auth.json exists but contains no tokens.")

    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise CodexUsageError("Missing access_token in Codex credentials.")

    account_id = tokens.get("account_id")
    if isinstance(account_id, str):
        account_id = account_id.strip() or None
    else:
        account_id = None

    return CodexCredentials(access_token=access_token.strip(), account_id=account_id)


def parse_chatgpt_base_url(config_text: str) -> str | None:
    for raw_line in config_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue

        key, value = line.split("=", 1)
        if key.strip() != "chatgpt_base_url":
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        value = value.strip()
        if value:
            return value
    return None


def normalize_base_url(url: str) -> str:
    trimmed = url.strip().rstrip("/")
    if not trimmed:
        return DEFAULT_BASE_URL

    if (
        trimmed.startswith("https://chatgpt.com")
        or trimmed.startswith("https://chat.openai.com")
    ) and "/backend-api" not in trimmed:
        trimmed = f"{trimmed}/backend-api"

    return trimmed


def is_allowed_base_url(url: str) -> bool:
    return (
        url.startswith("https://")
        or url.startswith("http://127.0.0.1")
        or url.startswith("http://localhost")
    )


def resolve_base_url(
    config_path: Path | None = None,
    override: str | None = None,
) -> str:
    if override:
        normalized = normalize_base_url(override)
        if not is_allowed_base_url(normalized):
            raise CodexUsageError(
                f"Insecure base URL rejected: {normalized}. "
                "Use HTTPS, localhost, or 127.0.0.1."
            )
        return normalized

    resolved_config_path = get_config_path(config_path)
    if resolved_config_path.exists():
        try:
            config_text = resolved_config_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CodexUsageError(f"Failed to read config.toml: {exc}") from exc

        base_url = parse_chatgpt_base_url(config_text)
        if base_url:
            normalized = normalize_base_url(base_url)
            if is_allowed_base_url(normalized):
                return normalized

    return DEFAULT_BASE_URL


def fetch_usage_json(
    base_url: str,
    credentials: CodexCredentials,
    timeout: float,
) -> dict[str, Any]:
    url = f"{base_url}{USAGE_PATH}"
    headers = {
        "Authorization": f"Bearer {credentials.access_token}",
        "User-Agent": "bluetag-usage-codex",
        "Accept": "application/json",
    }
    if credentials.account_id:
        headers["ChatGPT-Account-Id"] = credentials.account_id

    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise CodexUsageError(
                "Authentication failed with 401/403. Re-run `codex` to log in again."
            ) from exc
        details = exc.read().decode("utf-8", errors="replace").strip()
        suffix = f": {details}" if details else ""
        raise CodexUsageError(f"Codex API returned HTTP {exc.code}{suffix}") from exc
    except urllib.error.URLError as exc:
        raise CodexUsageError(f"Request failed: {exc.reason}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CodexUsageError(f"Failed to parse API response as JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise CodexUsageError("Expected a JSON object from /wham/usage.")
    return payload


def fetch_codex_usage(
    *,
    timeout: float = 30.0,
    auth_path: Path | None = None,
    config_path: Path | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    credentials = load_credentials(auth_path)
    resolved_base_url = resolve_base_url(config_path, base_url)
    return fetch_usage_json(resolved_base_url, credentials, timeout)


def resolve_timezone(name: str | None):
    if not name:
        return datetime.now().astimezone().tzinfo or timezone.utc
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise CodexUsageError(f"Unknown timezone: {name}") from exc


def epoch_to_iso(timestamp: Any) -> str | None:
    if not isinstance(timestamp, (int, float)):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def parse_used_percent(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return max(0.0, min(float(value), 100.0))
    return 0.0


def parse_window(window: Any) -> dict[str, Any]:
    if not isinstance(window, dict):
        return {"used_percent": 0.0}

    used_percent = parse_used_percent(
        window.get("used_percent", window.get("usage_percent"))
    )
    limit_window_seconds = window.get("limit_window_seconds")
    window_minutes = None
    if isinstance(limit_window_seconds, (int, float)):
        window_minutes = int(limit_window_seconds) // 60

    result: dict[str, Any] = {"used_percent": used_percent}
    if window_minutes is not None:
        result["window_minutes"] = window_minutes

    resets_at = epoch_to_iso(window.get("reset_at"))
    if resets_at:
        result["resets_at"] = resets_at

    return result


def maybe_parse_window(window: Any) -> dict[str, Any] | None:
    return parse_window(window) if isinstance(window, dict) else None


def extract_rate_limits(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if "usage" in payload and isinstance(payload["usage"], dict):
        usage = payload["usage"]
        primary = usage.get("primary")
        secondary = usage.get("secondary")
        if isinstance(primary, dict):
            return primary, secondary if isinstance(secondary, dict) else None

    rate_limit = payload.get("rate_limit")
    if isinstance(rate_limit, dict):
        primary = maybe_parse_window(rate_limit.get("primary_window")) or {
            "used_percent": 0.0
        }
        secondary = maybe_parse_window(rate_limit.get("secondary_window"))
        return primary, secondary

    rate_limits = payload.get("rate_limits")
    if isinstance(rate_limits, list) and rate_limits:
        primary = parse_window(rate_limits[0])
        secondary = parse_window(rate_limits[1]) if len(rate_limits) > 1 else None
        return primary, secondary

    used_percent = parse_used_percent(
        payload.get("used_percent", payload.get("usage_percent"))
    )
    return {"used_percent": used_percent}, None


def format_window_label(window_minutes: Any, fallback: str) -> str:
    if not isinstance(window_minutes, int) or window_minutes <= 0:
        return fallback
    if window_minutes == 300:
        return "5h"
    if window_minutes == 10080:
        return "7d"
    if window_minutes % 1440 == 0:
        return f"{window_minutes // 1440}d"
    if window_minutes % 60 == 0:
        return f"{window_minutes // 60}h"
    return f"{window_minutes}m"


def format_reset_text(resets_at: Any, tzinfo) -> str:
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


def _format_remaining_text(resets_at: Any, tzinfo) -> str:
    if not isinstance(resets_at, str) or not resets_at:
        return "?m"

    iso_value = resets_at.replace("Z", "+00:00")
    try:
        reset_dt = datetime.fromisoformat(iso_value).astimezone(tzinfo)
    except ValueError:
        return "?m"

    delta_seconds = max(0, int((reset_dt - datetime.now(tzinfo)).total_seconds()))
    total_minutes = delta_seconds // 60
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes} m"


def _format_reset_point_text(resets_at: Any, tzinfo) -> str:
    if not isinstance(resets_at, str) or not resets_at:
        return "--:--"

    iso_value = resets_at.replace("Z", "+00:00")
    try:
        reset_dt = datetime.fromisoformat(iso_value).astimezone(tzinfo)
    except ValueError:
        return "--:--"

    now_dt = datetime.now(tzinfo)
    if reset_dt.date() == now_dt.date():
        return reset_dt.strftime("%H:%M")
    return f"{reset_dt.month}/{reset_dt.day} {reset_dt:%H:%M}"


def _compact_window_label(label: str) -> str:
    normalized = label.strip().lower()
    if normalized.startswith("5h"):
        return "5h"
    if normalized.startswith("7d"):
        return "7d"
    return label


def build_codex_rows(payload: dict[str, Any], tzinfo) -> list[UsageRow]:
    primary, secondary = extract_rate_limits(payload)

    rows = [
        UsageRow(
            label=format_window_label(primary.get("window_minutes"), "5h"),
            left_percent=max(
                0.0, min(100.0, 100.0 - parse_used_percent(primary.get("used_percent")))
            ),
            used_percent=parse_used_percent(primary.get("used_percent")),
            resets_text=format_reset_text(primary.get("resets_at"), tzinfo),
        )
    ]

    if secondary:
        rows.append(
            UsageRow(
                label=format_window_label(secondary.get("window_minutes"), "7d"),
                left_percent=max(
                    0.0,
                    min(
                        100.0,
                        100.0 - parse_used_percent(secondary.get("used_percent")),
                    ),
                ),
                used_percent=parse_used_percent(secondary.get("used_percent")),
                resets_text=format_reset_text(secondary.get("resets_at"), tzinfo),
            )
        )

    return rows[:2]


def build_codex_refresh_rows(payload: dict[str, Any]) -> list[tuple[str, float]]:
    primary, secondary = extract_rate_limits(payload)

    rows = [
        (
            format_window_label(primary.get("window_minutes"), "5h"),
            parse_used_percent(primary.get("used_percent")),
        )
    ]

    if secondary:
        rows.append(
            (
                format_window_label(secondary.get("window_minutes"), "7d"),
                parse_used_percent(secondary.get("used_percent")),
            )
        )

    return rows[:2]


def build_codex_panel_rows(payload: dict[str, Any], tzinfo) -> list[PanelRow]:
    primary, secondary = extract_rate_limits(payload)

    row_specs: list[tuple[dict[str, Any], str]] = [
        (primary, format_window_label(primary.get("window_minutes"), "5h"))
    ]
    if secondary:
        row_specs.append(
            (
                secondary,
                format_window_label(secondary.get("window_minutes"), "7d"),
            )
        )

    rows: list[PanelRow] = []
    for window, label in row_specs[:2]:
        used_percent = parse_used_percent(window.get("used_percent"))
        compact_label = _compact_window_label(label)
        rows.append(
            PanelRow(
                label=compact_label,
                left_percent=max(0.0, min(100.0, 100.0 - used_percent)),
                used_percent=used_percent,
                remaining_text=_format_reset_point_text(window.get("resets_at"), tzinfo),
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


def _load_mono_font(
    size: int, *, font_path: str | None = None
) -> ImageFont.FreeTypeFont:
    if font_path:
        return ImageFont.truetype(font_path, size)
    for path in _MONO_FONT_SEARCH:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return _load_font(size, font_path=font_path)


def _new_crisp_canvas(
    width: int,
    height: int,
) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.fontmode = "1"
    return image, draw


def _draw_hardened_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
) -> None:
    x, y = position
    draw.text((x, y), text, fill=0, font=font)
    draw.text((x + 1, y), text, fill=0, font=font)


def _measure_tracked_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    tracking: int,
) -> int:
    total_width = 0
    for index, char in enumerate(text):
        char_bbox = draw.textbbox((0, 0), char, font=font)
        total_width += char_bbox[2] - char_bbox[0]
        if index < len(text) - 1:
            total_width += tracking
    return total_width


def _draw_tracked_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    tracking: int,
    fill: int | str = 0,
) -> None:
    x, y = position
    cursor_x = x
    for index, char in enumerate(text):
        draw.text((cursor_x, y), text=char, fill=fill, font=font)
        char_bbox = draw.textbbox((0, 0), char, font=font)
        cursor_x += char_bbox[2] - char_bbox[0]
        if index < len(text) - 1:
            cursor_x += tracking


def _draw_progress_bar(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    percent: float,
    fill: int | str = "black",
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
            fill=fill,
        )


def _render_rows_small(
    rows: list[UsageRow],
    *,
    title_text: str,
    font_path: str | None,
    width: int = WIDTH_2_13,
    height: int = HEIGHT_2_13,
    title_font_size: int = 13,
    label_font_size: int = 12,
    stat_font_size: int = 12,
    detail_font_size: int = 9,
    left_pad: int = 7,
    right_pad: int = 7,
    top_pad: int = 5,
    bottom_pad: int = 3,
    title_gap: int = 5,
    gap: int = 9,
    bar_height: int = 12,
    bar_gap: int = 3,
    detail_gap: int = 16,
    row_tops: list[int] | None = None,
) -> Image.Image:
    image, draw = _new_crisp_canvas(width, height)

    title_font = _load_font(title_font_size, font_path=font_path)
    label_font = _load_font(label_font_size, font_path=font_path)
    stat_font = _load_mono_font(stat_font_size, font_path=font_path)
    detail_font = _load_mono_font(detail_font_size, font_path=font_path)

    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]

    # 标题放在渲染图底部（变换后显示在物理屏幕顶部）
    title_y = height - bottom_pad - title_h
    draw.text(((width - title_w) // 2, title_y), title_text, fill=0, font=title_font)

    rows_top = top_pad
    row_count = max(1, len(rows))
    row_height = (title_y - title_gap - rows_top - gap * (row_count - 1)) // row_count

    for index, row in enumerate(rows):
        if row_tops is not None and index < len(row_tops):
            row_top = row_tops[index]
        else:
            row_top = rows_top + index * (row_height + gap)
        percent_text = f"{int(round(row.used_percent))}%"

        label_bbox = draw.textbbox((0, 0), row.label, font=label_font)
        label_h = label_bbox[3] - label_bbox[1]
        percent_w = _measure_tracked_text(
            draw,
            percent_text,
            font=stat_font,
            tracking=1,
        )
        usage_color = usage_color_for_percent(row.used_percent)

        draw.text((left_pad, row_top), row.label, fill=0, font=label_font)
        _draw_tracked_text(
            draw,
            (width - right_pad - percent_w, row_top),
            percent_text,
            font=stat_font,
            tracking=1,
            fill=usage_color,
        )

        bar_y = row_top + label_h + bar_gap
        _draw_progress_bar(
            draw,
            x=left_pad,
            y=bar_y,
            width=width - left_pad - right_pad - 1,
            height=bar_height,
            percent=row.used_percent,
            fill=usage_color,
        )

        detail_bbox = draw.textbbox((0, 0), row.resets_text, font=detail_font)
        detail_w = detail_bbox[2] - detail_bbox[0]
        _draw_hardened_text(
            draw,
            (width - right_pad - detail_w, bar_y + detail_gap),
            row.resets_text,
            font=detail_font,
        )

    return image.convert("RGB")


def _render_rows_large(
    rows: list[UsageRow],
    *,
    title_text: str,
    font_path: str | None,
) -> Image.Image:
    image = Image.new("RGB", (WIDTH_3_7, HEIGHT_3_7), "white")
    draw = ImageDraw.Draw(image)

    title_font = _load_font(24, font_path=font_path)
    label_font = _load_font(20, font_path=font_path)
    stat_font = _load_font(22, font_path=font_path)
    detail_font = _load_font(14, font_path=font_path)

    left_pad = 20
    right_pad = 20
    top_pad = 15
    bottom_pad = 15
    title_gap = 15
    gap = 25

    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]
    draw.text(
        ((WIDTH_3_7 - title_w) // 2, top_pad),
        title_text,
        fill="black",
        font=title_font,
    )

    rows_top = top_pad + title_h + title_gap
    row_count = max(1, len(rows))
    row_height = (
        HEIGHT_3_7 - rows_top - bottom_pad - gap * (row_count - 1)
    ) // row_count

    for index, row in enumerate(rows):
        row_top = rows_top + index * (row_height + gap)
        percent_text = f"{int(round(row.used_percent))}%"

        label_bbox = draw.textbbox((0, 0), row.label, font=label_font)
        percent_bbox = draw.textbbox((0, 0), percent_text, font=stat_font)
        label_h = label_bbox[3] - label_bbox[1]
        percent_w = percent_bbox[2] - percent_bbox[0]

        draw.text((left_pad, row_top), row.label, fill="black", font=label_font)
        draw.text(
            (WIDTH_3_7 - right_pad - percent_w, row_top - 2),
            percent_text,
            fill="black",
            font=stat_font,
        )

        bar_y = row_top + label_h + 8
        draw.rectangle(
            (left_pad, bar_y, WIDTH_3_7 - right_pad - 1, bar_y + 20),
            outline="black",
            width=2,
        )
        inner_x0 = left_pad + 3
        inner_y0 = bar_y + 3
        inner_x1 = WIDTH_3_7 - right_pad - 3
        inner_y1 = bar_y + 18
        fill_width = round(
            max(0, inner_x1 - inner_x0)
            * max(0.0, min(100.0, row.used_percent))
            / 100.0
        )
        if fill_width > 0:
            draw.rectangle(
                (inner_x0, inner_y0, inner_x0 + fill_width - 1, inner_y1),
                fill="black",
            )

        detail_bbox = draw.textbbox((0, 0), row.resets_text, font=detail_font)
        detail_w = detail_bbox[2] - detail_bbox[0]
        draw.text(
            (WIDTH_3_7 - right_pad - detail_w, bar_y + 28),
            row.resets_text,
            fill="black",
            font=detail_font,
        )

    return image


def render_codex_2_13(payload: dict[str, Any], tzinfo, font_path: str | None = None) -> Image.Image:
    return _render_rows_small(
        build_codex_rows(payload, tzinfo),
        title_text="codex",
        font_path=font_path,
    )


def render_codex_2_9(payload: dict[str, Any], tzinfo, font_path: str | None = None) -> Image.Image:
    return render_usage_panel_2_9(
        sections=[("Codex", build_codex_panel_rows(payload, tzinfo))],
        tzinfo=tzinfo,
        font_path=font_path,
    )


def render_codex_3_7(payload: dict[str, Any], tzinfo, font_path: str | None = None) -> Image.Image:
    return render_usage_panel_3_7(
        sections=[("OpenAI Codex", build_codex_panel_rows(payload, tzinfo))],
        tzinfo=tzinfo,
        font_path=font_path,
    )
