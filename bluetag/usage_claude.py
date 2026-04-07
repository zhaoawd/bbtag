"""Claude Code usage fetching and rendering helpers."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image, ImageDraw, ImageFont

API_URL = "https://api.anthropic.com/api/oauth/usage"
API_BETA = "oauth-2025-04-20"
TOKEN_URL = "https://api.anthropic.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
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


class ClaudeUsageError(RuntimeError):
    """Raised when Claude usage cannot be loaded or rendered."""


@dataclass(frozen=True)
class UsageRow:
    label: str
    left_percent: float
    used_percent: float
    resets_text: str


@dataclass(frozen=True)
class ClaudeOAuthCredentials:
    access_token: str
    refresh_token: str | None
    expires_at_ms: int | None
    raw_payload: dict[str, Any]


def resolve_timezone(name: str | None):
    if not name:
        return datetime.now().astimezone().tzinfo or timezone.utc
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ClaudeUsageError(f"Unknown timezone: {name}") from exc


def _load_credentials_from_keychain() -> ClaudeOAuthCredentials:
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
    refresh_token = claude_oauth.get("refreshToken")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        refresh_token = None
    else:
        refresh_token = refresh_token.strip()

    expires_at_ms = claude_oauth.get("expiresAt")
    if not isinstance(expires_at_ms, int):
        expires_at_ms = None

    return ClaudeOAuthCredentials(
        access_token=access_token.strip(),
        refresh_token=refresh_token,
        expires_at_ms=expires_at_ms,
        raw_payload=payload,
    )


def _save_credentials_to_keychain(credentials: ClaudeOAuthCredentials) -> None:
    raw = json.dumps(credentials.raw_payload, separators=(",", ":"))
    account = os.environ.get("USER", "claude-code")
    result = subprocess.run(
        [
            "security",
            "add-generic-password",
            "-U",
            "-a",
            account,
            "-s",
            "Claude Code-credentials",
            "-w",
            raw,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        suffix = f": {stderr}" if stderr else ""
        raise ClaudeUsageError(
            "Refreshed Claude token but failed to save updated credentials" + suffix
        )


def _request_json(request: urllib.request.Request, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ClaudeUsageError(f"Failed to parse API response as JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ClaudeUsageError("Expected a JSON object from Claude usage API.")
    return payload


def _is_token_expired_error(exc: urllib.error.HTTPError) -> bool:
    if exc.code != 401:
        return False
    try:
        details = exc.read().decode("utf-8", errors="replace").strip()
        if not details:
            return False
        payload = json.loads(details)
    except (OSError, json.JSONDecodeError):
        return False
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    error_details = error.get("details")
    if not isinstance(error_details, dict):
        return False
    return error_details.get("error_code") == "token_expired"


def _refresh_access_token(
    credentials: ClaudeOAuthCredentials,
    *,
    timeout: float,
) -> ClaudeOAuthCredentials:
    if not credentials.refresh_token:
        raise ClaudeUsageError("Claude access token expired and no refresh token is available.")

    payload = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": credentials.refresh_token,
            "client_id": CLIENT_ID,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "bluetag-usage-claude",
        },
        data=payload,
        method="POST",
    )
    try:
        token_payload = _request_json(request, timeout)
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace").strip()
        suffix = f": {details}" if details else ""
        raise ClaudeUsageError(
            f"Claude OAuth refresh failed with HTTP {exc.code}{suffix}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ClaudeUsageError(f"Claude OAuth refresh request failed: {exc.reason}") from exc

    access_token = token_payload.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise ClaudeUsageError("Claude OAuth refresh response did not include access_token.")

    refresh_token = token_payload.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        refresh_token = credentials.refresh_token
    else:
        refresh_token = refresh_token.strip()

    expires_in = token_payload.get("expires_in")
    expires_at_ms = credentials.expires_at_ms
    if isinstance(expires_in, (int, float)):
        expires_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000 + expires_in * 1000)

    updated_payload = json.loads(json.dumps(credentials.raw_payload))
    claude_oauth = updated_payload.setdefault("claudeAiOauth", {})
    if not isinstance(claude_oauth, dict):
        raise ClaudeUsageError("Claude credentials JSON has invalid `claudeAiOauth` structure.")
    claude_oauth["accessToken"] = access_token.strip()
    if refresh_token:
        claude_oauth["refreshToken"] = refresh_token
    if expires_at_ms is not None:
        claude_oauth["expiresAt"] = expires_at_ms

    refreshed = ClaudeOAuthCredentials(
        access_token=access_token.strip(),
        refresh_token=refresh_token,
        expires_at_ms=expires_at_ms,
        raw_payload=updated_payload,
    )
    _save_credentials_to_keychain(refreshed)
    return refreshed


def fetch_claude_usage(*, timeout: float = 10.0) -> dict[str, Any]:
    credentials = _load_credentials_from_keychain()

    def build_usage_request(access_token: str) -> urllib.request.Request:
        return urllib.request.Request(
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
        return _request_json(build_usage_request(credentials.access_token), timeout)
    except urllib.error.HTTPError as exc:
        if not _is_token_expired_error(exc):
            details = exc.read().decode("utf-8", errors="replace").strip()
            suffix = f": {details}" if details else ""
            raise ClaudeUsageError(f"Claude API returned HTTP {exc.code}{suffix}") from exc
    except urllib.error.URLError as exc:
        raise ClaudeUsageError(f"Request failed: {exc.reason}") from exc

    refreshed = _refresh_access_token(credentials, timeout=timeout)
    try:
        return _request_json(build_usage_request(refreshed.access_token), timeout)
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace").strip()
        suffix = f": {details}" if details else ""
        raise ClaudeUsageError(
            f"Claude API returned HTTP {exc.code} after token refresh{suffix}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ClaudeUsageError(f"Request failed after token refresh: {exc.reason}") from exc


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


def build_claude_refresh_rows(
    payload: dict[str, Any],
    *,
    include_sonnet: bool,
) -> list[tuple[str, float]]:
    return [
        (row.label, row.left_percent)
        for row in build_claude_rows(payload, timezone.utc, include_sonnet=include_sonnet)
    ]


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


def _render_claude_small(
    payload: dict[str, Any],
    tzinfo,
    font_path: str | None = None,
    *,
    width: int = WIDTH_2_13,
    height: int = HEIGHT_2_13,
    title_font_size: int = 13,
    label_font_size: int = 11,
    stat_font_size: int = 11,
    detail_font_size: int = 8,
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
    rows = build_claude_rows(payload, tzinfo, include_sonnet=False)
    image, draw = _new_crisp_canvas(width, height)

    title_font = _load_font(title_font_size, font_path=font_path)
    label_font = _load_font(label_font_size, font_path=font_path)
    stat_font = _load_font(stat_font_size, font_path=font_path)
    detail_font = _load_font(detail_font_size, font_path=font_path)

    title_text = "claude code"
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]

    title_y = height - bottom_pad - title_h
    draw.text(
        ((width - title_w) // 2, title_y),
        title_text,
        fill=0,
        font=title_font,
    )

    rows_top = top_pad
    row_count = max(1, len(rows))
    row_height = (
        title_y - title_gap - rows_top - gap * (row_count - 1)
    ) // row_count

    for index, row in enumerate(rows):
        if row_tops is not None and index < len(row_tops):
            row_top = row_tops[index]
        else:
            row_top = rows_top + index * (row_height + gap)
        percent_text = f"{int(round(row.left_percent))}% left"

        label_bbox = draw.textbbox((0, 0), row.label, font=label_font)
        percent_bbox = draw.textbbox((0, 0), percent_text, font=stat_font)
        label_h = label_bbox[3] - label_bbox[1]
        percent_w = percent_bbox[2] - percent_bbox[0]

        draw.text((left_pad, row_top), row.label, fill=0, font=label_font)
        draw.text(
            (width - right_pad - percent_w, row_top),
            percent_text,
            fill=0,
            font=stat_font,
        )

        bar_y = row_top + label_h + bar_gap
        _draw_small_progress_bar(
            draw,
            x=left_pad,
            y=bar_y,
            width=width - left_pad - right_pad - 1,
            height=bar_height,
            percent=row.left_percent,
        )

        detail_bbox = draw.textbbox((0, 0), row.resets_text, font=detail_font)
        detail_w = detail_bbox[2] - detail_bbox[0]
        draw.text(
            (width - right_pad - detail_w, bar_y + detail_gap),
            row.resets_text,
            fill=0,
            font=detail_font,
        )

    return image.convert("RGB")


def render_claude_2_13(payload: dict[str, Any], tzinfo, font_path: str | None = None) -> Image.Image:
    return _render_claude_small(payload, tzinfo, font_path)


def render_claude_2_9(payload: dict[str, Any], tzinfo, font_path: str | None = None) -> Image.Image:
    return _render_claude_small(
        payload,
        tzinfo,
        font_path,
        width=WIDTH_2_9,
        height=HEIGHT_2_9,
        title_font_size=13,
        label_font_size=13,
        stat_font_size=13,
        detail_font_size=12,
        left_pad=12,
        right_pad=12,
        top_pad=5,
        bottom_pad=14,
        title_gap=3,
        gap=4,
        bar_height=11,
        bar_gap=5,
        detail_gap=14,
        row_tops=[4, 50],
    )


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
    row_map = {row.label: row for row in rows}
    rows = [
        row_map.get(
            "5h session",
            UsageRow(
                label="5h session",
                left_percent=0.0,
                used_percent=100.0,
                resets_text="resets unknown",
            ),
        ),
        row_map.get(
            "7d all models",
            UsageRow(
                label="7d all models",
                left_percent=0.0,
                used_percent=100.0,
                resets_text="resets unknown",
            ),
        ),
        row_map.get(
            "sonnet",
            UsageRow(
                label="sonnet",
                left_percent=0.0,
                used_percent=100.0,
                resets_text="resets unknown",
            ),
        ),
    ]
    image = Image.new("RGB", (WIDTH_3_7, HEIGHT_3_7), "white")
    draw = ImageDraw.Draw(image)

    header_h = 42
    draw.rectangle((0, 0, WIDTH_3_7, header_h), fill="black")

    title_font = _load_font(21, font_path=font_path)
    time_font = _load_font(14, font_path=font_path)
    section_font = _load_font(15, font_path=font_path)
    stat_font = _load_font(18, font_path=font_path)
    detail_font = _load_font(11, font_path=font_path)

    draw.text((14, 9), "CC USAGE", fill="white", font=title_font)
    time_text = datetime.now(tzinfo).strftime("%H:%M")
    time_bbox = draw.textbbox((0, 0), time_text, font=time_font)
    time_w = time_bbox[2] - time_bbox[0]
    draw.text((WIDTH_3_7 - 14 - time_w, 13), time_text, fill="white", font=time_font)

    top = header_h + 8
    segment_h = 54
    gap = 6
    outer_left = 14
    outer_right = 14
    labels = {
        "5h session": "SESSION",
        "7d all models": "ALL MODELS",
        "sonnet": "SONNET",
    }

    for index, row in enumerate(rows[:3]):
        y = top + index * (segment_h + gap)
        draw.rounded_rectangle(
            (outer_left, y, WIDTH_3_7 - outer_right, y + segment_h),
            radius=9,
            outline="black",
            width=2,
        )
        header_label = labels.get(row.label, row.label.upper())
        draw.text((24, y + 7), header_label, fill="black", font=section_font)

        percent_text = f"{int(round(row.left_percent))}% left"
        percent_bbox = draw.textbbox((0, 0), percent_text, font=stat_font)
        percent_w = percent_bbox[2] - percent_bbox[0]
        draw.text(
            (WIDTH_3_7 - 24 - percent_w, y + 5),
            percent_text,
            fill="red" if row.used_percent >= 80.0 else "black",
            font=stat_font,
        )

        _draw_large_progress_bar(
            draw,
            x=24,
            y=y + 24,
            width=WIDTH_3_7 - 48,
            height=12,
            left_percent=row.left_percent,
            used_percent=row.used_percent,
        )
        draw.text((24, y + 36), row.resets_text, fill="black", font=detail_font)

    return image
