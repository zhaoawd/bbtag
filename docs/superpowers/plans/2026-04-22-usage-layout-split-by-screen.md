# Usage Layout Split By Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 usage 布局与渲染按 `2.9inch` 和 `3.7inch` 彻底拆成独立模块，避免一个尺寸的视觉调整影响另一个尺寸。

**Architecture:** 新增 `usage_layout_common.py` 只保留稳定数据结构；把现有共享实现按尺寸平移到 `usage_layout_2_9.py` 和 `usage_layout_3_7.py`；`usage_codex.py` 和 `usage_claude.py` 只保留数据转换和按尺寸分发。迁移以“先物理隔离，再清理旧共享文件”为原则，不在平移阶段重设计视觉风格。

**Tech Stack:** Python 3.10+, PIL/Pillow, unittest, uv

---

### Task 1: 建立公共数据层

**Files:**
- Create: `bluetag/usage_layout_common.py`
- Modify: `tests/test_usage_codex.py`
- Test: `tests/test_usage_codex.py`

- [ ] **Step 1: Write the failing test**

```python
from bluetag.usage_layout_common import ALERT_USED_PERCENT, PanelRow

def test_usage_layout_common_exports_panel_row_and_alert_threshold(self) -> None:
    row = PanelRow("5h", 78.0, 22.0, "15:22")
    self.assertEqual(row.label, "5h")
    self.assertEqual(ALERT_USED_PERCENT, 80.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_usage_codex.CodexUsageTests.test_usage_layout_common_exports_panel_row_and_alert_threshold -v`
Expected: FAIL with `ModuleNotFoundError` or missing import from `bluetag.usage_layout_common`

- [ ] **Step 3: Write minimal implementation**

Create `bluetag/usage_layout_common.py` with:

```python
from dataclasses import dataclass

ALERT_USED_PERCENT = 80.0

@dataclass(frozen=True)
class PanelRow:
    label: str
    left_percent: float
    used_percent: float
    remaining_text: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_usage_codex.CodexUsageTests.test_usage_layout_common_exports_panel_row_and_alert_threshold -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bluetag/usage_layout_common.py tests/test_usage_codex.py
git commit -m "refactor: add shared usage layout data module"
```

### Task 2: 先拆出 2.9 寸独立布局模块

**Files:**
- Create: `bluetag/usage_layout_2_9.py`
- Modify: `bluetag/usage_codex.py`
- Modify: `bluetag/usage_claude.py`
- Modify: `tests/test_usage_codex.py`
- Modify: `tests/test_usage_claude.py`
- Test: `tests/test_usage_codex.py`
- Test: `tests/test_usage_claude.py`

- [ ] **Step 1: Write the failing test**

Add import-routing tests:

```python
from unittest.mock import patch
from bluetag.usage_codex import render_codex_2_9
from bluetag.usage_claude import render_claude_2_9

def test_render_codex_2_9_uses_split_2_9_layout_module(self) -> None:
    payload = {"rate_limit": {}}
    with patch("bluetag.usage_codex.render_usage_panel_2_9", return_value="ok") as mock_render:
        result = render_codex_2_9(payload, ZoneInfo("UTC"))
    self.assertEqual(result, "ok")
    mock_render.assert_called_once()

def test_render_claude_2_9_uses_split_2_9_layout_module(self) -> None:
    payload = {}
    with patch("bluetag.usage_claude.render_usage_panel_2_9", return_value="ok") as mock_render:
        result = render_claude_2_9(payload, ZoneInfo("UTC"))
    self.assertEqual(result, "ok")
    mock_render.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_usage_codex tests.test_usage_claude -v`
Expected: FAIL because `bluetag.usage_codex` / `bluetag.usage_claude` 尚未引用新的 `bluetag.usage_layout_2_9`

- [ ] **Step 3: Write minimal implementation**

Create `bluetag/usage_layout_2_9.py` and move these items from the current shared file into it:

- `WIDTH_2_9`, `HEIGHT_2_9`
- `PANEL_BAR_WIDTH_2_9`, `PANEL_BAR_HEIGHT_2_9`, `PANEL_BAR_INNER_WIDTH_2_9`
- `UsagePanel2_9Layout`
- `_load_font`, `_load_bold_font`, `_load_mono_font`, `_load_usage_value_font`, `_load_usage_reset_font`
- `_format_timestamp_2_9`
- `_draw_dashed_divider`, `_draw_dotted_background`, `_draw_percent_text`, `_compute_fill_width`
- `_build_usage_panel_2_9_layout`
- `render_usage_panel_2_9`

Update imports so:

```python
# bluetag/usage_codex.py
from bluetag.usage_layout_2_9 import render_usage_panel_2_9

# bluetag/usage_claude.py
from bluetag.usage_layout_2_9 import render_usage_panel_2_9
```

Keep existing behavior identical while moving code.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_usage_codex tests.test_usage_claude -v`
Expected: PASS for new routing tests and existing 2.9 rendering tests

- [ ] **Step 5: Commit**

```bash
git add bluetag/usage_layout_2_9.py bluetag/usage_codex.py bluetag/usage_claude.py tests/test_usage_codex.py tests/test_usage_claude.py
git commit -m "refactor: split 2.9 usage layout module"
```

### Task 3: 再拆出 3.7 寸独立布局模块

**Files:**
- Create: `bluetag/usage_layout_3_7.py`
- Modify: `bluetag/usage_codex.py`
- Modify: `bluetag/usage_claude.py`
- Modify: `tests/test_usage_codex.py`
- Modify: `tests/test_usage_claude.py`
- Test: `tests/test_usage_codex.py`
- Test: `tests/test_usage_claude.py`

- [ ] **Step 1: Write the failing test**

Add import-routing tests:

```python
def test_render_codex_3_7_uses_split_3_7_layout_module(self) -> None:
    payload = {"rate_limit": {}}
    with patch("bluetag.usage_codex.render_usage_panel_3_7", return_value="ok") as mock_render:
        result = render_codex_3_7(payload, ZoneInfo("UTC"))
    self.assertEqual(result, "ok")
    mock_render.assert_called_once()

def test_render_claude_3_7_uses_split_3_7_layout_module(self) -> None:
    payload = {}
    with patch("bluetag.usage_claude.render_usage_panel_3_7", return_value="ok") as mock_render:
        result = render_claude_3_7(payload, ZoneInfo("UTC"))
    self.assertEqual(result, "ok")
    mock_render.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_usage_codex tests.test_usage_claude -v`
Expected: FAIL because `bluetag.usage_codex` / `bluetag.usage_claude` 仍未完全切换到新的 3.7 模块

- [ ] **Step 3: Write minimal implementation**

Create `bluetag/usage_layout_3_7.py` and move these items into it:

- `WIDTH_3_7`, `HEIGHT_3_7`
- `PANEL_BAR_WIDTH`, `PANEL_BAR_HEIGHT`, `PANEL_BAR_INNER_WIDTH`
- `usage_color_for_percent`
- `_format_timestamp`
- `_draw_progress_row`
- `_draw_column_headers`
- `render_usage_panel_3_7`

Also move any 3.7-only helper that is no longer needed by `2.9`.

Update imports so:

```python
# bluetag/usage_codex.py
from bluetag.usage_layout_3_7 import render_usage_panel_3_7

# bluetag/usage_claude.py
from bluetag.usage_layout_3_7 import render_usage_panel_3_7
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_usage_codex tests.test_usage_claude -v`
Expected: PASS for new routing tests and existing 3.7 rendering tests

- [ ] **Step 5: Commit**

```bash
git add bluetag/usage_layout_3_7.py bluetag/usage_codex.py bluetag/usage_claude.py tests/test_usage_codex.py tests/test_usage_claude.py
git commit -m "refactor: split 3.7 usage layout module"
```

### Task 4: 清理旧共享文件并收窄公共层

**Files:**
- Modify: `bluetag/usage_layout_common.py`
- Delete: `bluetag/usage_layout_legacy.py` or the temporary shared file if introduced
- Modify: `tests/test_usage_codex.py`
- Modify: `tests/test_usage_claude.py`
- Test: `tests/test_usage_codex.py`
- Test: `tests/test_usage_claude.py`

- [ ] **Step 1: Write the failing test**

Add a boundary test asserting the common module only exports stable shared symbols:

```python
import bluetag.usage_layout_common as common

def test_usage_layout_common_only_hosts_shared_data_contract(self) -> None:
    self.assertTrue(hasattr(common, "PanelRow"))
    self.assertFalse(hasattr(common, "render_usage_panel_2_9"))
    self.assertFalse(hasattr(common, "render_usage_panel_3_7"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_usage_codex.CodexUsageTests.test_usage_layout_common_only_hosts_shared_data_contract -v`
Expected: FAIL if common module still carries rendering helpers

- [ ] **Step 3: Write minimal implementation**

Ensure:

- `bluetag/usage_layout_common.py` only contains shared data structures/constants
- no renderer remains in a misleading shared module
- imports across `usage_codex.py`, `usage_claude.py`, `usage_layout_2_9.py`, `usage_layout_3_7.py` are direct and size-specific

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_usage_codex tests.test_usage_claude -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bluetag/usage_layout_common.py bluetag/usage_layout_2_9.py bluetag/usage_layout_3_7.py bluetag/usage_codex.py bluetag/usage_claude.py tests/test_usage_codex.py tests/test_usage_claude.py
git commit -m "refactor: isolate usage renderers by screen size"
```

### Task 5: 全量验证与文档对齐

**Files:**
- Modify: `README.md` (only if module/file descriptions mention old shared layout)
- Test: `tests/test_usage_codex.py`
- Test: `tests/test_usage_claude.py`
- Test: `tests/test_cli_loop.py`
- Test: `tests/test_packaging.py`

- [ ] **Step 1: Write the failing test**

If `README.md` or test docs still reference the old shared renderer path, add or update a packaging/doc assertion such as:

```python
self.assertIn("usage_layout_2_9.py", readme)
self.assertIn("usage_layout_3_7.py", readme)
```

Only add this if documentation is intended to describe internal module layout.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_packaging -v`
Expected: FAIL only if documentation assertions were added and docs are stale

- [ ] **Step 3: Write minimal implementation**

Update only the necessary documentation or comments. Then run the verification commands:

```bash
uv run python -m unittest tests.test_usage_codex tests.test_usage_claude -v
uv run python -m unittest tests.test_cli_loop tests.test_packaging -v
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest discover -s tests -v`
Expected: PASS, 0 failures, 0 errors

- [ ] **Step 5: Commit**

```bash
git add README.md tests
git commit -m "test: verify usage layout split by screen"
```
