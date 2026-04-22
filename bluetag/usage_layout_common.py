"""Shared usage layout data contracts."""

from __future__ import annotations

from dataclasses import dataclass

ALERT_USED_PERCENT = 80.0


@dataclass(frozen=True)
class PanelRow:
    label: str
    left_percent: float
    used_percent: float
    remaining_text: str
