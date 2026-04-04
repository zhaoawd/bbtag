# Usage Loop Flicker Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce e-ink flashing in `bluetag loop` by skipping full-screen refreshes when usage values and visible bar widths have not meaningfully changed.

**Architecture:** Keep the existing BLE push pipeline intact and add refresh gating above it. Provider modules expose stable per-row usage summaries, and `bluetag.cli` converts those summaries into comparable refresh state so the loop only renders and pushes when value integers or bar-fill pixels change.

**Tech Stack:** Python 3.10+, argparse, asyncio, dataclasses, Pillow, unittest

---

### Task 1: Add failing tests for refresh gating

**Files:**
- Modify: `tests/test_cli_loop.py`
- Modify: `tests/test_usage_codex.py`
- Modify: `tests/test_usage_claude.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_run_loop_cycle_skips_push_when_refresh_state_is_unchanged():
    ...

def test_run_loop_cycle_pushes_when_bar_width_changes():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_cli_loop tests.test_usage_codex tests.test_usage_claude -v`
Expected: FAIL because refresh-row builders and loop gating do not exist yet

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli_loop.py tests/test_usage_codex.py tests/test_usage_claude.py
git commit -m "test: cover usage loop refresh gating"
```

### Task 2: Add provider refresh-row builders

**Files:**
- Modify: `bluetag/usage_codex.py`
- Modify: `bluetag/usage_claude.py`
- Test: `tests/test_usage_codex.py`
- Test: `tests/test_usage_claude.py`

- [ ] **Step 1: Implement Codex refresh-row builder**

```python
@dataclass(frozen=True)
class RefreshRowData:
    label: str
    left_percent: float


def build_codex_refresh_rows(payload: dict[str, Any]) -> list[RefreshRowData]:
    return [
        RefreshRowData(label=row.label, left_percent=row.left_percent)
        for row in build_codex_rows(payload, timezone.utc)
    ]
```

- [ ] **Step 2: Implement Claude refresh-row builder**

```python
def build_claude_refresh_rows(
    payload: dict[str, Any],
    *,
    include_sonnet: bool,
) -> list[RefreshRowData]:
    ...
```

- [ ] **Step 3: Run targeted tests**

Run: `uv run python -m unittest tests.test_usage_codex tests.test_usage_claude -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add bluetag/usage_codex.py bluetag/usage_claude.py tests/test_usage_codex.py tests/test_usage_claude.py
git commit -m "feat: expose usage refresh row builders"
```

### Task 3: Implement loop refresh gating

**Files:**
- Modify: `bluetag/cli.py`
- Test: `tests/test_cli_loop.py`

- [ ] **Step 1: Add refresh-state dataclasses and bar-fill width calculation**

```python
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
```

- [ ] **Step 2: Extend `UsageLoopSource` with a refresh-row builder**

```python
class UsageLoopSource:
    ...
    refresh_rows: Callable[..., list]
```

- [ ] **Step 3: Update `_run_loop_cycle` to skip render/push when refresh state is unchanged**

```python
if previous_state == current_state:
    print(f"skip {source.name} refresh: no meaningful value change")
    await sleep(interval_seconds)
    continue
```

- [ ] **Step 4: Update cached state only after a successful push**

```python
if ok:
    states[source.name] = current_state
```

- [ ] **Step 5: Run targeted tests**

Run: `uv run python -m unittest tests.test_cli_loop -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add bluetag/cli.py tests/test_cli_loop.py
git commit -m "feat: gate usage loop refreshes by value changes"
```

### Task 4: Verify and document final behavior

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a short note that `loop` now skips redundant refreshes to reduce flashing**
- [ ] **Step 2: Run full test suite**

Run: `uv run python -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 3: Verify CLI help still works**

Run: `uv run bluetag loop --help`
Expected: exits 0 and shows existing arguments

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: describe usage loop refresh gating"
```
