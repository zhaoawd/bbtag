"""
图像处理模块 — 量化、2bpp 编解码、双色屏图层处理

无外部 BLE 依赖，可在任何平台使用。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from bluetag.screens import get_screen_profile

WIDTH, HEIGHT = 240, 416
PIXELS = WIDTH * HEIGHT
BPP2_SIZE = PIXELS // 4  # 24960 bytes

# 4色调色板 (RGB) — 按 2bpp 值索引
# 00=黑 01=白 10=黄 11=红
PALETTE = [
    (0, 0, 0),
    (255, 255, 255),
    (255, 255, 0),
    (255, 0, 0),
]


def _ensure_image(source: Image.Image | str | Path) -> Image.Image:
    if isinstance(source, Image.Image):
        return source.copy()
    return Image.open(source)


def _nearest_color(r: int, g: int, b: int) -> int:
    """返回最近的调色板索引 (0-3)。"""
    best = 0
    best_dist = float("inf")
    for i, (pr, pg, pb) in enumerate(PALETTE):
        dist = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if dist < best_dist:
            best_dist = dist
            best = i
    return best


def quantize(
    img: Image.Image,
    flip: bool = True,
    size: tuple[int, int] = (WIDTH, HEIGHT),
) -> list[int]:
    """
    将图像量化为 4 色索引数组。

    Args:
        img: PIL Image (任意尺寸/模式)
        flip: 水平翻转
        size: 目标尺寸

    Returns:
        list[int], 长度=pixels, 值 0-3
    """
    width, height = size
    img = img.convert("RGB").resize((width, height), Image.LANCZOS)
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    pixels = img.getdata()
    return [_nearest_color(r, g, b) for r, g, b in pixels]


def quantize_for_screen(
    img: Image.Image,
    screen: str = "3.7inch",
    flip: bool | None = None,
) -> list[int]:
    """按屏幕尺寸量化图像。"""
    profile = get_screen_profile(screen)
    effective_flip = profile.mirror if flip is None else flip
    return quantize(img, flip=effective_flip, size=profile.size)


def pack_2bpp(indices: list[int] | bytes) -> bytes:
    """
    将 4 色索引数组打包为 2bpp 字节流 (MSB first, 每字节 4 像素)。

    Args:
        indices: 长度=PIXELS, 值 0-3

    Returns:
        bytes, 长度 24960
    """
    assert len(indices) == PIXELS
    out = bytearray(PIXELS // 4)
    for i in range(0, PIXELS, 4):
        out[i // 4] = (indices[i] << 6) | (indices[i + 1] << 4) | (indices[i + 2] << 2) | indices[i + 3]
    return bytes(out)


def unpack_2bpp(data: bytes) -> list[int]:
    """
    将 2bpp 字节流解包为 4 色索引数组。

    Args:
        data: 24960 bytes

    Returns:
        list[int], 长度=PIXELS, 值 0-3
    """
    out = []
    for b in data:
        out.append((b >> 6) & 3)
        out.append((b >> 4) & 3)
        out.append((b >> 2) & 3)
        out.append(b & 3)
    return out


def indices_to_image(
    indices: list[int],
    size: tuple[int, int] = (WIDTH, HEIGHT),
) -> Image.Image:
    """
    将 4 色索引数组转为 RGB PIL Image。

    Args:
        indices: 长度=pixels, 值 0-3
        size: 输出尺寸

    Returns:
        PIL Image
    """
    width, height = size
    img = Image.new("RGB", (width, height))
    img.putdata([PALETTE[i] for i in indices])
    return img


def process_bicolor_image(
    source: Image.Image | str | Path,
    screen: str,
    *,
    threshold: int = 128,
    dither: bool = False,
    rotate: int = 0,
    mirror: bool = True,
    swap_wh: bool = False,
    detect_red: bool = True,
) -> tuple[list[list[int]], list[list[int]], Image.Image]:
    """
    将图像处理为双色电子墨水屏的黑层/红层。

    Returns:
        (black_layer, red_layer, preview_image)
        每层为 height x width 的二维列表，值 0 或 1
    """
    profile = get_screen_profile(screen)
    img = _ensure_image(source).convert("RGB")

    width, height = profile.size
    if swap_wh:
        width, height = height, width

    if rotate:
        img = img.rotate(rotate, expand=True)

    img.thumbnail((width, height), Image.Resampling.LANCZOS)
    if mirror:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

    canvas = Image.new("RGB", (width, height), "white")
    x_offset = (width - img.width) // 2
    y_offset = (height - img.height) // 2
    canvas.paste(img, (x_offset, y_offset))

    gray = canvas.convert("L")
    if dither:
        gray = gray.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")

    gray_pixels = list(gray.getdata())
    black_layer = [[0] * width for _ in range(height)]
    red_layer = [[0] * width for _ in range(height)]

    for row in range(height):
        for col in range(width):
            idx = row * width + col
            black_layer[row][col] = 1 if gray_pixels[idx] >= threshold else 0

    if detect_red:
        rgb_pixels = list(canvas.getdata())
        for row in range(height):
            for col in range(width):
                idx = row * width + col
                r, g, b = rgb_pixels[idx]
                if r > 150 and g < 100 and b < 100:
                    red_layer[row][col] = 1
                    black_layer[row][col] = 0

    return black_layer, red_layer, bicolor_layers_to_image(black_layer, red_layer)


def layer_to_bytes_rowwise(layer: list[list[int]]) -> bytes:
    """Pack a layer row by row, 8 horizontal pixels per byte."""
    height = len(layer)
    width = len(layer[0]) if height else 0
    bytes_per_row = (width + 7) // 8
    data = bytearray()

    for row in range(height):
        for byte_idx in range(bytes_per_row):
            start_col = byte_idx * 8
            byte_val = 0
            for bit_idx in range(8):
                col = start_col + (7 - bit_idx)
                if col < width and layer[row][col]:
                    byte_val |= 1 << bit_idx
            data.append(byte_val)

    return bytes(data)


def layer_to_bytes_columnwise(layer: list[list[int]]) -> bytes:
    """Pack a layer column by column, 8 vertical pixels per byte."""
    height = len(layer)
    width = len(layer[0]) if height else 0
    bytes_per_column = (height + 7) // 8
    data = bytearray()

    for col in range(width):
        for byte_idx in range(bytes_per_column):
            start_row = byte_idx * 8
            byte_val = 0
            for bit_idx in range(8):
                row = start_row + bit_idx
                if row < height and layer[row][col]:
                    byte_val |= 1 << bit_idx
            data.append(byte_val)

    return bytes(data)


def layer_to_bytes(layer: list[list[int]], encoding: str = "row") -> bytes:
    """Convert image layer to transmission bytes."""
    if encoding == "row":
        return layer_to_bytes_rowwise(layer)
    if encoding == "column":
        return layer_to_bytes_columnwise(layer)
    raise ValueError(f"Unsupported encoding: {encoding}")


def bicolor_layers_to_image(
    black_layer: list[list[int]],
    red_layer: list[list[int]],
) -> Image.Image:
    """Convert black/red binary layers into an RGB preview image."""
    height = len(black_layer)
    width = len(black_layer[0]) if height else 0
    img = Image.new("RGB", (width, height), "white")
    pixels = []
    for row in range(height):
        for col in range(width):
            if red_layer[row][col] == 1:
                pixels.append((255, 0, 0))
            elif black_layer[row][col] == 0:
                pixels.append((0, 0, 0))
            else:
                pixels.append((255, 255, 255))
    img.putdata(pixels)
    return img
