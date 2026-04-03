# Usage Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `bluetag loop` command that alternates Codex and Claude Code usage screens on supported devices, while extracting reusable Codex usage logic into library modules.

**Architecture:** Move usage-fetch/render code out of example scripts into `bluetag.usage_codex` and `bluetag.usage_claude`, then let the CLI compose those modules with the existing BLE push pipeline. Keep the loop runtime thin by testing one-cycle behavior in isolation and reusing the current screen transport helpers.

**Tech Stack:** Python 3.10+, argparse, asyncio, Pillow, urllib.request, subprocess, unittest/mock

---

### Task 1: Add failing tests for usage parsing and loop orchestration

**Files:**
- Create: `tests/test_usage_codex.py`
- Create: `tests/test_usage_claude.py`
- Create: `tests/test_cli_loop.py`

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run test to verify it fails**
  Run: `uv run python -m unittest discover -s tests -v`
  Expected: FAIL because the new usage modules / loop helpers do not exist yet
- [ ] **Step 3: Commit**

### Task 2: Extract reusable Codex usage module

**Files:**
- Create: `bluetag/usage_codex.py`
- Modify: `examples/push_codex_usage.py`
- Modify: `examples/push_codex_usage_3.7.py`

- [ ] **Step 1: Implement shared Codex credential loading, usage fetch, row building, and 2.13/3.7 renderers**
- [ ] **Step 2: Update example scripts to import the new module while preserving current CLI behavior**
- [ ] **Step 3: Run targeted tests**
  Run: `uv run python -m unittest tests.test_usage_codex -v`
  Expected: PASS
- [ ] **Step 4: Commit**

### Task 3: Add Claude usage module

**Files:**
- Create: `bluetag/usage_claude.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Implement macOS Keychain token loading, Anthropic usage fetch, normalization, and 2.13/3.7 renderers**
- [ ] **Step 2: Ensure non-macOS or missing token cases raise clear runtime errors**
- [ ] **Step 3: Run targeted tests**
  Run: `uv run python -m unittest tests.test_usage_claude -v`
  Expected: PASS
- [ ] **Step 4: Commit**

### Task 4: Add loop command and verify end-to-end orchestration

**Files:**
- Modify: `bluetag/cli.py`
- Modify: `README.md`

- [ ] **Step 1: Implement one-cycle loop helper, CLI parser wiring, and infinite alternating runtime with graceful Ctrl+C handling**
- [ ] **Step 2: Reuse existing BLE target selection and push helpers for both screen sizes**
- [ ] **Step 3: Run targeted tests**
  Run: `uv run python -m unittest tests.test_cli_loop -v`
  Expected: PASS
- [ ] **Step 4: Run full test suite**
  Run: `uv run python -m unittest discover -s tests -v`
  Expected: PASS
- [ ] **Step 5: Commit**
