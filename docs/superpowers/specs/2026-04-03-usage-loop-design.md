# Usage Loop: Codex / Claude Code 交替刷新设计

## 概述

新增 `bluetag loop` CLI 子命令，定时交替获取 Codex 和 Claude Code 的用量数据，渲染并推送到电子墨水价签。支持 2.13 寸和 3.7 寸两种屏幕尺寸。

## 模块结构

新增两个模块到 `bluetag/` 包中：

```
bluetag/
  usage_codex.py    — Codex 用量获取 + 渲染（从 examples/ 提取）
  usage_claude.py   — Claude Code 用量获取 + 渲染（新增）
```

### `usage_codex.py`

从 `examples/push_codex_usage.py` 和 `push_codex_usage_3.7.py` 中提取核心逻辑：

- `fetch_codex_usage(timeout=30.0) -> dict` — 凭证加载（~/.codex/auth.json）+ API 请求（chatgpt.com/backend-api/wham/usage）
- `render_codex_2_13(payload, tzinfo, font_path=None) -> Image` — 2.13 寸渲染（250x122）
- `render_codex_3_7(payload, tzinfo, font_path=None) -> Image` — 3.7 寸渲染（416x240）

### `usage_claude.py`

参照 cc-usage-elink 实现：

- `fetch_claude_usage(timeout=10.0) -> dict` — 从 macOS Keychain 读 token，请求 API
- `render_claude_2_13(payload, tzinfo, font_path=None) -> Image` — 2.13 寸渲染（250x122）
- `render_claude_3_7(payload, tzinfo, font_path=None) -> Image` — 3.7 寸渲染（416x240）

`examples/` 下的现有脚本保留，改为 import 这些模块。

## Claude Code 用量获取

### Token 获取

从 macOS Keychain 读取 `Claude Code-credentials`，解析 JSON 取 `claudeAiOauth.accessToken`：

```python
subprocess.run(
    ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
    capture_output=True, text=True,
).stdout.strip()
# 解析: json.loads(raw)["claudeAiOauth"]["accessToken"]
```

### API 请求

```
GET https://api.anthropic.com/api/oauth/usage
Headers:
  Authorization: Bearer {token}
  anthropic-beta: oauth-2025-04-20
```

### 返回数据结构

```json
{
  "five_hour": { "utilization": 45.2, "resets_at": "2026-04-03T18:00:00Z" },
  "seven_day": { "utilization": 12.0, "resets_at": "2026-04-07T00:00:00Z" },
  "seven_day_sonnet": { "utilization": 8.5, "resets_at": "2026-04-07T00:00:00Z" }
}
```

三个维度：5 小时会话限额、7 天全模型限额、7 天 Sonnet 限额。

## Claude Code 渲染布局

### 2.13 寸（250x122）

风格与现有 Codex 2.13 寸一致（标题 + 进度条行）：

- 标题：`claude code`
- 2 行（屏幕空间有限，省略 Sonnet）：
  - `5h session` — 进度条 + 剩余百分比 + 重置时间
  - `7d all models` — 进度条 + 剩余百分比 + 重置时间

### 3.7 寸（416x240，横屏）

风格与 cc-usage-elink 类似（黑色 header + 三段式布局）：

- 标题栏：`CC USAGE` + 当前时间
- 三段：
  - `SESSION` — 5h 限额进度条
  - `ALL MODELS` — 7d 限额进度条
  - `SONNET` — 7d Sonnet 限额进度条
- 用量 >= 80% 时进度条变红色标记

## `loop` 子命令设计

### 命令格式

```
bluetag loop --screen 2.13inch [--interval 90] [--device xxx] [--address xxx] [--timezone Asia/Shanghai] [--font xxx]
```

### 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--screen` | 屏幕尺寸，`2.13inch` 或 `3.7inch` | 必选 |
| `--interval` | 刷新间隔秒数 | 90 |
| `--device` / `-d` | 设备名 | 无（使用缓存） |
| `--address` / `-a` | 设备 BLE 地址 | 无 |
| `--timezone` | 时区 | 系统本地 |
| `--font` | 自定义字体路径 | 无 |

### 运行行为

1. 启动时扫描/连接设备（或使用缓存设备）
2. 进入无限循环：
   - 获取 Codex 用量 → 渲染对应尺寸图片 → 推送到屏幕
   - 等待 interval 秒
   - 获取 Claude Code 用量 → 渲染对应尺寸图片 → 推送到屏幕
   - 等待 interval 秒
   - 循环...
3. Ctrl+C 优雅退出

### 容错

- 单次获取用量失败：打印错误，跳过本轮，继续下一轮
- 单次推送失败：打印错误，跳过本轮，继续下一轮
- 循环不会因单次失败而中断

## 对现有代码的影响

- `examples/push_codex_usage.py` 和 `push_codex_usage_3.7.py`：改为 import `bluetag.usage_codex` 模块，简化代码
- `bluetag/cli.py`：新增 `loop` 子命令
- 不影响 Kimi usage 脚本（暂不纳入 loop）
