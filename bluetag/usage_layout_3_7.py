"""Shared 3.7-inch usage panel layout helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH_3_7 = 416
HEIGHT_3_7 = 240
PANEL_BAR_WIDTH = 214
PANEL_BAR_HEIGHT = 18
PANEL_BAR_INNER_WIDTH = PANEL_BAR_WIDTH - 4
WIDTH_2_9 = 296
HEIGHT_2_9 = 128
PANEL_BAR_WIDTH_2_9 = 156
PANEL_BAR_HEIGHT_2_9 = 10
PANEL_BAR_INNER_WIDTH_2_9 = PANEL_BAR_WIDTH_2_9 - 4
ALERT_USED_PERCENT = 80.0

_FONT_DIR = Path(__file__).parent / "fonts"
_MONO_FONT_SEARCH = [
    "/System/Library/Fonts/Supplemental/Menlo.ttc",
    "/System/Library/Fonts/Monaco.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "C:\\Windows\\Fonts\\consola.ttf",
]
_BOLD_FONT_SEARCH = [
    str(_FONT_DIR / "AlibabaPuHuiTi-Bold.ttf"),
    str(_FONT_DIR / "AlibabaPuHuiTi-Regular.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Menlo.ttc",
    "/System/Library/Fonts/Monaco.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "C:\\Windows\\Fonts\\consolab.ttf",
    "C:\\Windows\\Fonts\\consola.ttf",
]
_REGULAR_FONT_SEARCH = [
    str(_FONT_DIR / "AlibabaPuHuiTi-Regular.ttf"),
    str(_FONT_DIR / "AlibabaPuHuiTi-Bold.ttf"),
    *_MONO_FONT_SEARCH,
]


@dataclass(frozen=True)
class PanelRow:
    label: str
    left_percent: float
    used_percent: float
    remaining_text: str


@dataclass(frozen=True)
class UsagePanel2_9Layout:
    title_font_size: int
    body_font_size: int
    title_x: int
    title_y: int
    title_right: int
    timestamp_x: int
    timestamp_y: int
    divider_y: int
    section_tops: tuple[int, int]
    label_x: int
    bar_x: int
    bar_width: int
    bar_right: int
    percent_right: int
    time_right: int
    row_gap: int
    section_title_gap: int


def usage_color_for_percent(used_percent: float) -> str:
    return "red" if used_percent >= ALERT_USED_PERCENT else "black"


def _load_font(size: int, *, font_path: str | None = None) -> ImageFont.FreeTypeFont:
    if font_path:
        return ImageFont.truetype(font_path, size)
    for path in _REGULAR_FONT_SEARCH:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _load_bold_font(
    size: int, *, font_path: str | None = None
) -> ImageFont.FreeTypeFont:
    if font_path:
        return ImageFont.truetype(font_path, size)
    for path in _BOLD_FONT_SEARCH:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return _load_font(size, font_path=font_path)


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


def _draw_hardened_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
) -> None:
    x, y = position
    draw.text((x, y), text, fill="black", font=font)
    draw.text((x + 1, y), text, fill="black", font=font)


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
    fill: str = "black",
) -> None:
    x, y = position
    cursor_x = x
    for index, char in enumerate(text):
        draw.text((cursor_x, y), char, fill=fill, font=font)
        char_bbox = draw.textbbox((0, 0), char, font=font)
        cursor_x += char_bbox[2] - char_bbox[0]
        if index < len(text) - 1:
            cursor_x += tracking


def _format_timestamp(tzinfo) -> str:
    now_dt = datetime.now(tzinfo)
    hour_text = now_dt.strftime("%I").lstrip("0") or "0"
    return f"{now_dt.strftime('%b')} {now_dt.day} {hour_text}:{now_dt:%M %p}"


def _format_timestamp_2_9(now_dt: datetime) -> str:
    return f"{now_dt.month}/{now_dt.day} {now_dt:%H:%M}"


def _draw_dashed_divider(
    draw: ImageDraw.ImageDraw,
    *,
    y: int,
    left: int,
    right: int,
) -> None:
    x = left
    while x < right:
        dash_right = min(x + 6, right)
        draw.line((x, y, dash_right, y), fill="black", width=1)
        x += 11


def _draw_dotted_background(
    draw: ImageDraw.ImageDraw,
    *,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    x_step: int = 4,
    y_step: int = 4,
    stagger: int = 2,
) -> None:
    for row_index, y in enumerate(range(y0 + 2, y1, y_step)):
        start = x0 + 2 + (stagger if row_index % 2 else 0)
        for x in range(start, x1, x_step):
            draw.point((x, y), fill="black")


def _draw_percent_text(
    draw: ImageDraw.ImageDraw,
    *,
    right: int,
    y: int,
    used_percent: float,
    font: ImageFont.FreeTypeFont,
    fill: str,
    number_tracking: int = 0,
    percent_gap: int = 2,
) -> None:
    number_text = str(int(round(used_percent)))
    percent_text = "%"
    number_w = _measure_tracked_text(
        draw,
        number_text,
        font=font,
        tracking=number_tracking,
    )
    percent_bbox = draw.textbbox((0, 0), percent_text, font=font)
    percent_w = percent_bbox[2] - percent_bbox[0]
    total_w = number_w + percent_gap + percent_w
    start_x = right - total_w
    _draw_tracked_text(
        draw,
        (start_x, y),
        number_text,
        font=font,
        tracking=number_tracking,
        fill=fill,
    )
    draw.text(
        (start_x + number_w + percent_gap, y),
        percent_text,
        fill=fill,
        font=font,
    )


def _fit_2_9_title_font_size(
    draw: ImageDraw.ImageDraw,
    *,
    title_text: str,
    timestamp_text: str,
    font_path: str | None,
    title_x: int,
    timestamp_right: int,
    min_gap: int,
) -> tuple[int, int, int]:
    timestamp_font = _load_font(9, font_path=font_path)
    timestamp_bbox = draw.textbbox((0, 0), timestamp_text, font=timestamp_font)
    timestamp_w = timestamp_bbox[2] - timestamp_bbox[0]
    timestamp_x = timestamp_right - timestamp_w

    for size in range(11, 8, -1):
        title_font = _load_bold_font(size, font_path=font_path)
        title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
        title_w = title_bbox[2] - title_bbox[0]
        title_right = title_x + title_w
        if timestamp_x - title_right >= min_gap:
            return size, title_right, timestamp_x

    fallback_font = _load_bold_font(9, font_path=font_path)
    fallback_bbox = draw.textbbox((0, 0), title_text, font=fallback_font)
    fallback_w = fallback_bbox[2] - fallback_bbox[0]
    return 9, title_x + fallback_w, timestamp_x


def _build_usage_panel_2_9_layout(
    *,
    title_text: str,
    timestamp_text: str,
    font_path: str | None,
) -> UsagePanel2_9Layout:
    image = Image.new("RGB", (WIDTH_2_9, HEIGHT_2_9), "white")
    draw = ImageDraw.Draw(image)

    title_x = 8
    timestamp_right = WIDTH_2_9 - 15
    time_right = WIDTH_2_9 - 14
    title_font_size, title_right, timestamp_x = _fit_2_9_title_font_size(
        draw,
        title_text=title_text,
        timestamp_text=timestamp_text,
        font_path=font_path,
        title_x=title_x,
        timestamp_right=timestamp_right,
        min_gap=14,
    )
    bar_x = 36
    bar_width = 148
    return UsagePanel2_9Layout(
        title_font_size=title_font_size,
        body_font_size=10,
        title_x=title_x,
        title_y=6,
        title_right=title_right,
        timestamp_x=timestamp_x,
        timestamp_y=7,
        divider_y=70,
        section_tops=(27, 79),
        label_x=8,
        bar_x=bar_x,
        bar_width=bar_width,
        bar_right=bar_x + bar_width - 1,
        percent_right=219,
        time_right=time_right,
        row_gap=15,
        section_title_gap=13,
    )


def _draw_progress_row(
    draw: ImageDraw.ImageDraw,
    *,
    row: PanelRow,
    y: int,
    label_font: ImageFont.FreeTypeFont,
    value_font: ImageFont.FreeTypeFont,
    detail_font: ImageFont.FreeTypeFont,
) -> None:
    left = 14
    label_x = left
    bar_x = 46
    percent_right = 311
    time_right = 403
    bar_y = y + 1
    bar_x1 = bar_x + PANEL_BAR_WIDTH - 1
    bar_y1 = bar_y + PANEL_BAR_HEIGHT - 1

    _draw_hardened_text(draw, (label_x, y), row.label, font=label_font)
    draw.rectangle((bar_x, bar_y, bar_x1, bar_y1), outline="black", width=1)

    inner_x0 = bar_x + 2
    inner_y0 = bar_y + 2
    inner_x1 = bar_x1 - 2
    inner_y1 = bar_y1 - 2
    _draw_dotted_background(
        draw,
        x0=inner_x0,
        y0=inner_y0,
        x1=inner_x1,
        y1=inner_y1,
    )

    fill_width = round(
        PANEL_BAR_INNER_WIDTH * max(0.0, min(100.0, row.used_percent)) / 100.0
    )
    usage_color = usage_color_for_percent(row.used_percent)
    if fill_width > 0:
        draw.rectangle(
            (
                inner_x0,
                inner_y0,
                inner_x0 + fill_width - 1,
                inner_y1,
            ),
            fill=usage_color,
        )

    _draw_percent_text(
        draw,
        right=percent_right,
        y=y,
        used_percent=row.used_percent,
        font=value_font,
        number_tracking=1,
        fill=usage_color,
    )

    detail_bbox = draw.textbbox((0, 0), row.remaining_text, font=detail_font)
    detail_w = detail_bbox[2] - detail_bbox[0]
    draw.text(
        (time_right - detail_w, y),
        row.remaining_text,
        fill="black",
        font=detail_font,
    )


def _draw_column_headers(
    draw: ImageDraw.ImageDraw,
    *,
    used_right: int,
    reset_right: int,
    y: int,
    font: ImageFont.FreeTypeFont,
) -> None:
    used_text = "used"
    used_bbox = draw.textbbox((0, 0), used_text, font=font)
    used_w = used_bbox[2] - used_bbox[0]
    draw.text((used_right - used_w, y), used_text, fill="black", font=font)

    reset_text = "reset"
    reset_bbox = draw.textbbox((0, 0), reset_text, font=font)
    reset_w = reset_bbox[2] - reset_bbox[0]
    draw.text((reset_right - reset_w, y), reset_text, fill="black", font=font)


def render_usage_panel_3_7(
    *,
    sections: list[tuple[str, list[PanelRow]]],
    tzinfo,
    font_path: str | None = None,
    title_text: str = "Token Usage",
) -> Image.Image:
    image = Image.new("RGB", (WIDTH_3_7, HEIGHT_3_7), "white")
    draw = ImageDraw.Draw(image)
    draw.fontmode = "1"

    title_font = _load_bold_font(18, font_path=font_path)
    time_font = _load_mono_font(14, font_path=font_path)
    section_font = _load_font(15, font_path=font_path)
    label_font = _load_font(14, font_path=font_path)
    value_font = _load_mono_font(14, font_path=font_path)
    detail_font = _load_mono_font(12, font_path=font_path)
    column_font = _load_font(13, font_path=font_path)

    _draw_hardened_text(draw, (12, 8), title_text, font=title_font)
    timestamp_text = _format_timestamp(tzinfo)
    timestamp_bbox = draw.textbbox((0, 0), timestamp_text, font=time_font)
    timestamp_w = timestamp_bbox[2] - timestamp_bbox[0]
    draw.text(
        (WIDTH_3_7 - 16 - timestamp_w, 10),
        timestamp_text,
        fill="black",
        font=time_font,
    )
    draw.line((12, 31, WIDTH_3_7 - 12, 31), fill="black", width=1)

    if len(sections) <= 1:
        section_tops = [50]
        row_gap = 34
    else:
        section_tops = [42, 128]
        row_gap = 28

    _draw_column_headers(
        draw,
        used_right=311,
        reset_right=403,
        y=40,
        font=column_font,
    )

    for index, ((section_title, rows), section_top) in enumerate(
        zip(sections[: len(section_tops)], section_tops)
    ):
        _draw_hardened_text(draw, (12, section_top), section_title, font=section_font)
        row_y = section_top + 20
        for row in rows[:2]:
            _draw_progress_row(
                draw,
                row=row,
                y=row_y,
                label_font=label_font,
                value_font=value_font,
                detail_font=detail_font,
            )
            row_y += row_gap
        if index < min(len(sections), len(section_tops)) - 1:
            _draw_dashed_divider(
                draw,
                y=118,
                left=12,
                right=WIDTH_3_7 - 12,
            )

    return image


def render_usage_panel_2_9(
    *,
    sections: list[tuple[str, list[PanelRow]]],
    tzinfo,
    font_path: str | None = None,
    title_text: str = "Token Usage",
) -> Image.Image:
    image = Image.new("RGB", (WIDTH_2_9, HEIGHT_2_9), "white")
    draw = ImageDraw.Draw(image)
    draw.fontmode = "1"

    timestamp_text = _format_timestamp_2_9(datetime.now(tzinfo))
    layout = _build_usage_panel_2_9_layout(
        title_text=title_text,
        timestamp_text=timestamp_text,
        font_path=font_path,
    )

    title_font = _load_bold_font(layout.title_font_size, font_path=font_path)
    time_font = _load_font(layout.body_font_size, font_path=font_path)
    section_font = _load_bold_font(layout.body_font_size, font_path=font_path)
    label_font = _load_font(layout.body_font_size, font_path=font_path)
    value_font = _load_mono_font(layout.body_font_size, font_path=font_path)
    detail_font = _load_font(layout.body_font_size, font_path=font_path)
    column_font = _load_font(layout.body_font_size, font_path=font_path)

    draw.text(
        (layout.title_x, layout.title_y),
        title_text,
        fill="black",
        font=title_font,
    )
    draw.text(
        (layout.timestamp_x, layout.timestamp_y),
        timestamp_text,
        fill="black",
        font=time_font,
    )
    draw.line((8, 21, WIDTH_2_9 - 8, 21), fill="black", width=1)

    _draw_column_headers(
        draw,
        used_right=layout.percent_right,
        reset_right=layout.time_right,
        y=24,
        font=column_font,
    )

    for index, ((section_title, rows), section_top) in enumerate(
        zip(sections[: len(layout.section_tops)], layout.section_tops)
    ):
        draw.text((layout.label_x, section_top), section_title, fill="black", font=section_font)
        row_y = section_top + layout.section_title_gap
        for row in rows[:2]:
            draw.text((layout.label_x, row_y), row.label, fill="black", font=label_font)

            bar_y = row_y + 1
            bar_x1 = layout.bar_right
            bar_y1 = bar_y + PANEL_BAR_HEIGHT_2_9 - 1
            draw.rectangle((layout.bar_x, bar_y, bar_x1, bar_y1), outline="black", width=1)

            inner_x0 = layout.bar_x + 2
            inner_y0 = bar_y + 2
            inner_x1 = bar_x1 - 2
            inner_y1 = bar_y1 - 2
            _draw_dotted_background(
                draw,
                x0=inner_x0,
                y0=inner_y0,
                x1=inner_x1,
                y1=inner_y1,
                x_step=6,
                y_step=5,
                stagger=3,
            )
            fill_width = round(
                (layout.bar_width - 4) * max(0.0, min(100.0, row.used_percent)) / 100.0
            )
            usage_color = usage_color_for_percent(row.used_percent)
            if fill_width > 0:
                draw.rectangle(
                    (
                        inner_x0,
                        inner_y0,
                        inner_x0 + fill_width - 1,
                        inner_y1,
                    ),
                    fill=usage_color,
                )

            _draw_percent_text(
                draw,
                right=layout.percent_right,
                y=row_y,
                used_percent=row.used_percent,
                font=value_font,
                number_tracking=0,
                fill=usage_color,
            )

            detail_bbox = draw.textbbox((0, 0), row.remaining_text, font=detail_font)
            detail_w = detail_bbox[2] - detail_bbox[0]
            draw.text(
                (layout.time_right - detail_w, row_y),
                row.remaining_text,
                fill="black",
                font=detail_font,
            )
            row_y += layout.row_gap

        if index < min(len(sections), len(layout.section_tops)) - 1:
            _draw_dashed_divider(
                draw,
                y=layout.divider_y,
                left=8,
                right=WIDTH_2_9 - 8,
            )

    return image
