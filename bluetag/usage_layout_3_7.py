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


def _format_timestamp(tzinfo) -> str:
    now_dt = datetime.now(tzinfo)
    hour_text = now_dt.strftime("%I").lstrip("0") or "0"
    return f"{now_dt.strftime('%b')} {now_dt.day} {hour_text}:{now_dt:%M %p}"


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
) -> None:
    for row_index, y in enumerate(range(y0 + 2, y1, 4)):
        start = x0 + 2 + (2 if row_index % 2 else 0)
        for x in range(start, x1, 4):
            draw.point((x, y), fill="black")


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
    percent_right = 312
    time_right = 404
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
        PANEL_BAR_INNER_WIDTH * max(0.0, min(100.0, row.left_percent)) / 100.0
    )
    if fill_width > 0:
        draw.rectangle(
            (
                inner_x0,
                inner_y0,
                inner_x0 + fill_width - 1,
                inner_y1,
            ),
            fill="black",
        )

    percent_text = f"{int(round(row.used_percent))}%"
    percent_bbox = draw.textbbox((0, 0), percent_text, font=value_font)
    percent_w = percent_bbox[2] - percent_bbox[0]
    _draw_hardened_text(
        draw,
        (percent_right - percent_w, y),
        percent_text,
        font=value_font,
    )

    detail_bbox = draw.textbbox((0, 0), row.remaining_text, font=detail_font)
    detail_w = detail_bbox[2] - detail_bbox[0]
    draw.text(
        (time_right - detail_w, y),
        row.remaining_text,
        fill="black",
        font=detail_font,
    )


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
    section_font = _load_bold_font(15, font_path=font_path)
    label_font = _load_bold_font(14, font_path=font_path)
    value_font = _load_bold_font(13, font_path=font_path)
    detail_font = _load_bold_font(12, font_path=font_path)
    column_font = _load_bold_font(11, font_path=font_path)

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

    _draw_hardened_text(draw, (274, 35), "used", font=column_font)

    for index, ((section_title, rows), section_top) in enumerate(
        zip(sections[: len(section_tops)], section_tops)
    ):
        _draw_hardened_text(draw, (12, section_top), section_title, font=section_font)
        row_y = section_top + 23
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

    title_font = _load_bold_font(12, font_path=font_path)
    time_font = _load_mono_font(9, font_path=font_path)
    section_font = _load_bold_font(9, font_path=font_path)
    label_font = _load_bold_font(9, font_path=font_path)
    value_font = _load_bold_font(8, font_path=font_path)
    column_font = _load_bold_font(8, font_path=font_path)

    _draw_hardened_text(draw, (8, 5), title_text, font=title_font)
    timestamp_text = _format_timestamp(tzinfo)
    timestamp_bbox = draw.textbbox((0, 0), timestamp_text, font=time_font)
    timestamp_w = timestamp_bbox[2] - timestamp_bbox[0]
    draw.text(
        (WIDTH_2_9 - 10 - timestamp_w, 7),
        timestamp_text,
        fill="black",
        font=time_font,
    )
    draw.line((8, 20, WIDTH_2_9 - 8, 20), fill="black", width=1)

    section_tops = [26, 74]
    label_x = 8
    bar_x = 34
    percent_right = 219
    time_right = WIDTH_2_9 - 8
    row_gap = 14

    _draw_hardened_text(draw, (188, 21), "used", font=column_font)

    for index, ((section_title, rows), section_top) in enumerate(
        zip(sections[: len(section_tops)], section_tops)
    ):
        _draw_hardened_text(draw, (8, section_top), section_title, font=section_font)
        row_y = section_top + 12
        for row in rows[:2]:
            _draw_hardened_text(draw, (label_x, row_y), row.label, font=label_font)

            bar_y = row_y + 1
            bar_x1 = bar_x + PANEL_BAR_WIDTH_2_9 - 1
            bar_y1 = bar_y + PANEL_BAR_HEIGHT_2_9 - 1
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
                PANEL_BAR_INNER_WIDTH_2_9 * max(0.0, min(100.0, row.left_percent)) / 100.0
            )
            if fill_width > 0:
                draw.rectangle(
                    (
                        inner_x0,
                        inner_y0,
                        inner_x0 + fill_width - 1,
                        inner_y1,
                    ),
                    fill="black",
                )

            percent_text = f"{int(round(row.used_percent))}%"
            percent_bbox = draw.textbbox((0, 0), percent_text, font=value_font)
            percent_w = percent_bbox[2] - percent_bbox[0]
            _draw_hardened_text(
                draw,
                (percent_right - percent_w, row_y),
                percent_text,
                font=value_font,
            )

            detail_bbox = draw.textbbox((0, 0), row.remaining_text, font=value_font)
            detail_w = detail_bbox[2] - detail_bbox[0]
            _draw_hardened_text(
                draw,
                (time_right - detail_w, row_y),
                row.remaining_text,
                font=value_font,
            )
            row_y += row_gap

        if index < min(len(sections), len(section_tops)) - 1:
            _draw_dashed_divider(
                draw,
                y=68,
                left=8,
                right=WIDTH_2_9 - 8,
            )

    return image
