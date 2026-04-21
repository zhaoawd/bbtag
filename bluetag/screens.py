"""Screen profiles and CLI-facing screen helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScreenProfile:
    """Static configuration for a supported BlueTag screen."""

    name: str
    aliases: tuple[str, ...]
    width: int
    height: int
    device_prefix: str
    cache_file: str
    transport: str
    default_interval_ms: int
    mirror: bool = True
    rotate: int = 0
    swap_wh: bool = False
    detect_red: bool = True
    flush_every: int = 0
    settle_ms: int = 0
    encoding: str = "row"
    initial_repeat_packets: int = 1
    supports_partial_diff: bool = True
    red_offset_x: int = 0
    red_offset_y: int = 0

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def cache_path(self) -> Path:
        return Path(self.cache_file)


SCREEN_PROFILES: dict[str, ScreenProfile] = {
    "3.7inch": ScreenProfile(
        name="3.7inch",
        aliases=("3.7", "3.7inch"),
        width=240,
        height=416,
        device_prefix="EPD-",
        cache_file=".device.3.7inch",
        transport="frame",
        default_interval_ms=50,
        mirror=True,
    ),
    "2.13inch": ScreenProfile(
        name="2.13inch",
        aliases=("2.13", "2.13inch"),
        width=250,
        height=122,
        device_prefix="EDP-",
        cache_file=".device.2.13inch",
        transport="layer",
        default_interval_ms=100,
        mirror=True,
        rotate=90,
        swap_wh=True,
        detect_red=True,
        flush_every=0,
        settle_ms=1500,
        encoding="row",
        initial_repeat_packets=1,
        supports_partial_diff=True,
    ),
    "2.9inch": ScreenProfile(
        name="2.9inch",
        aliases=("2.9", "2.9inch"),
        width=296,
        height=128,
        device_prefix="EDP-",
        cache_file=".device.2.9inch",
        transport="layer",
        default_interval_ms=70,
        mirror=True,
        rotate=90,
        swap_wh=True,
        detect_red=True,
        flush_every=0,
        settle_ms=1500,
        encoding="row",
        initial_repeat_packets=4,
        supports_partial_diff=False,
        red_offset_y=-8,
    ),
}

_ALIAS_TO_SCREEN = {
    alias.lower(): profile
    for profile in SCREEN_PROFILES.values()
    for alias in profile.aliases
}


def get_screen_profile(screen: str | None) -> ScreenProfile:
    """Resolve user input into a supported screen profile."""
    if screen is None:
        return SCREEN_PROFILES["3.7inch"]

    key = screen.strip().lower()
    try:
        return _ALIAS_TO_SCREEN[key]
    except KeyError as exc:
        choices = ", ".join(
            sorted({profile.name for profile in SCREEN_PROFILES.values()})
        )
        raise ValueError(f"不支持的屏幕尺寸 '{screen}'，可选: {choices}") from exc


def screen_choices() -> tuple[str, ...]:
    """Primary screen names for argparse choices/help text."""
    return tuple(SCREEN_PROFILES)
