# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

BluETag (bbtag) — BT370R 蓝签电子墨水标签 BLE 图像推送库。通过 BLE 向电子墨水屏推送图像/文字，支持三种屏幕尺寸 (3.7inch / 2.13inch / 2.9inch)。

## Commands

```bash
# 安装依赖 (macOS 需要 lzo)
LZO_DIR="$(brew --prefix lzo)" uv sync

# 运行所有测试 (unittest, 无 pytest)
uv run python -m unittest discover -s tests -v

# 运行单个测试文件
uv run python -m unittest tests/test_usage_codex.py

# 运行单个测试用例
uv run python -m unittest tests.test_usage_codex.CodexUsageTests.test_build_codex_rows_from_rate_limit_payload

# CLI 入口
uv run bluetag <subcommand>   # scan / push / text / loop / decode
```

## Architecture

两种传输协议由 `ScreenProfile.transport` 字段决定：

- **frame** (3.7inch): `image.py` 量化为 4 色 2bpp → `protocol.py` LZO 压缩 + 帧组装 + 分包 → `ble.py` 发送
- **layer** (2.13inch / 2.9inch): `image.py` 分离黑/红双层 → `transfer.py` 按层发送协议 → `ble.py` BleSession 写入

关键数据流：
1. `image.py` — 图像量化 (`quantize`)、2bpp 编解码、双色层分离 (`process_bicolor_image`)
2. `protocol.py` — 3.7 寸帧协议：LZO 压缩、校验和、MAC header、BLE 分包
3. `transfer.py` — 2.13/2.9 寸层协议：黑层 (0x13) + 红层 (0x12) 逐包发送
4. `ble.py` — BLE 扫描/连接/发送 (基于 bleak)，提供 `push()` 和 `BleSession`
5. `screens.py` — `ScreenProfile` dataclass 定义每种屏幕的尺寸、设备前缀、传输方式等参数
6. `text.py` — 文字自动排版渲染，根据屏幕尺寸自适应字号
7. `usage_codex.py` / `usage_claude.py` — 获取 Codex/Claude Code usage 数据，组装面板行数据，并按屏幕尺寸分发到对应 renderer
8. `usage_layout_common.py` / `usage_layout_2_9.py` / `usage_layout_3_7.py` — usage 面板共享数据结构，以及 2.9/3.7 各自独立的编排与渲染实现
9. `cli.py` — argparse CLI，`loop` 子命令交替推送 usage 面板，含变化阈值检测避免无意义刷新

设备名前缀区分屏幕类型：`EPD-` = 3.7 寸，`EDP-` = 2.13/2.9 寸。设备信息按屏幕缓存到已安装 `bluetag` 包目录下的 `.device.<screen>` 文件。

## Conventions

- Python >=3.10, 使用 `uv` 管理依赖
- 测试框架为 `unittest` (不使用 pytest)
- BLE 操作全部 async (asyncio)
- 项目语言为中文（注释、CLI 输出、文档）
