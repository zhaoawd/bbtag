# Usage 布局按屏幕尺寸彻底拆分设计

## 概述

当前 `2.9inch` 和 `3.7inch` 的 usage 内容编排与渲染共享在同一个模块中。最近一段时间的版式、字体、对齐、红色区域和数字字形调整，反复证明这种共享会让一个尺寸的视觉修正影响另一个尺寸，导致回归风险高、调试成本高、测试边界不清晰。

本次设计目标是按屏幕尺寸彻底拆分 usage 的布局和渲染实现。每个尺寸各自维护自己的字体选择、布局常量、绘制 helper、时间格式和像素级修正逻辑。允许少量代码重复，以换取后续调版的独立性和可维护性。

## 目标

- `2.9inch` 和 `3.7inch` 拥有完全独立的 usage 布局与渲染模块
- 修改某个尺寸的字体、坐标、间距、颜色或绘制逻辑时，不影响其他尺寸
- `usage_codex.py` 和 `usage_claude.py` 只保留 payload 解析和按尺寸分发渲染的职责
- 保持现有 CLI 和对外渲染函数签名稳定
- 保留现有像素级回归测试能力，并让测试按尺寸归属更清晰

## 非目标

- 本次不重做 usage 数据抓取逻辑
- 本次不改 BLE 推送或 loop 刷新机制
- 本次不强求 `2.13inch` 立即纳入同一轮拆分
- 本次不追求最大化消除重复代码

## 问题陈述

当前共享模块存在几个实际问题：

- 一个文件同时承载 `2.9inch` 和 `3.7inch` 的布局与绘制逻辑，文件名和职责不一致
- 字体加载、percent 绘制、reset 文案绘制、divider、bar 绘制等 helper 被多个尺寸复用，视觉修正会跨尺寸传播
- 回归测试虽然能发现问题，但失败时通常只能看到共享实现被破坏，难以快速界定责任边界
- 共享 helper 为了兼容多个尺寸，逐步积累条件分支，降低后续调版效率

## 方案选型

### 方案 A：按尺寸彻底拆分，允许少量重复（采用）

为每个尺寸建立独立布局模块，各自维护：

- 字体搜索顺序
- 标题与时间格式
- 行布局常量
- percent 数字绘制
- reset 文案绘制
- progress bar 绘制
- divider 和背景纹理
- 对齐修正和像素补偿

公共层仅保留真正稳定且不带尺寸含义的数据结构。

优点：

- 尺寸之间真正隔离
- 版式修正更直接
- 回归更容易定位
- 文件命名与职责一致

缺点：

- 会引入少量重复代码
- 初次迁移需要整理测试归属

### 方案 B：尺寸独立入口，共享底层 helper

每个尺寸有自己的入口函数，但底层字体、percent、bar、header helper 继续共享。

不采用原因：

- 共享 helper 仍会造成跨尺寸影响
- 只把耦合从顶层移动到底层，问题本质不变

### 方案 C：配置驱动单渲染器

继续保留一个渲染器，通过 layout config 区分尺寸。

不采用原因：

- 复杂度会继续累积在一个系统里
- 不符合“按尺寸彻底拆分”的目标

## 模块结构

建议最终结构如下：

```text
bluetag/
  usage_layout_common.py
  usage_layout_2_9.py
  usage_layout_3_7.py
  usage_codex.py
  usage_claude.py
```

### `usage_layout_common.py`

仅保留不带尺寸表现含义的公共内容，例如：

- `PanelRow`
- `ALERT_USED_PERCENT`

原则：

- 不放字体加载
- 不放坐标常量
- 不放 percent/reset 绘制
- 不放 bar/divider/background 绘制
- 不放 timestamp 格式化

### `usage_layout_2_9.py`

只负责 `2.9inch` usage 面板渲染，包括：

- `WIDTH_2_9`、`HEIGHT_2_9`
- 2.9 专用布局 dataclass
- 2.9 专用字体搜索和字体选择策略
- 2.9 专用 timestamp 格式
- 2.9 专用 column header / percent / reset / progress bar / divider / 背景点阵 helper
- `render_usage_panel_2_9(...)`

### `usage_layout_3_7.py`

只负责 `3.7inch` usage 面板渲染，包括：

- `WIDTH_3_7`、`HEIGHT_3_7`
- 3.7 专用布局常量
- 3.7 专用字体搜索和字体选择策略
- 3.7 专用 timestamp 格式
- 3.7 专用 row / percent / reset / progress bar / divider / header helper
- `render_usage_panel_3_7(...)`

## 对业务模块的职责调整

### `usage_codex.py`

保留：

- Codex 用量数据抓取
- payload 解析
- `build_codex_rows(...)`
- `build_codex_panel_rows(...)`
- `build_codex_refresh_rows(...)`

调整为：

- `render_codex_2_9(...)` 只调用 `usage_layout_2_9.render_usage_panel_2_9`
- `render_codex_3_7(...)` 只调用 `usage_layout_3_7.render_usage_panel_3_7`

不再持有尺寸布局 helper。

### `usage_claude.py`

保留：

- Claude 用量数据抓取
- payload 解析
- `build_claude_rows(...)`
- `build_claude_panel_rows(...)`
- `build_claude_refresh_rows(...)`

调整为：

- `render_claude_2_9(...)` 只调用 `usage_layout_2_9.render_usage_panel_2_9`
- `render_claude_3_7(...)` 只调用 `usage_layout_3_7.render_usage_panel_3_7`

## API 设计

对外接口保持稳定：

```python
def render_usage_panel_2_9(
    *,
    sections: list[tuple[str, list[PanelRow]]],
    tzinfo,
    font_path: str | None = None,
    title_text: str = "Token Usage",
) -> Image.Image


def render_usage_panel_3_7(
    *,
    sections: list[tuple[str, list[PanelRow]]],
    tzinfo,
    font_path: str | None = None,
    title_text: str = "Token Usage",
) -> Image.Image
```

这样 CLI 和 provider 模块无需感知内部拆分。

## 迁移步骤

建议按两阶段迁移，降低重构风险。

### 第一阶段：建立新模块并平移实现

1. 新建 `usage_layout_common.py`，只迁移 `PanelRow` 和真正稳定的常量
2. 新建 `usage_layout_2_9.py`，把当前 `2.9inch` 相关布局与渲染实现整体迁入
3. 新建 `usage_layout_3_7.py`，把当前 `3.7inch` 相关布局与渲染实现整体迁入
4. `usage_codex.py` 和 `usage_claude.py` 改为分别 import 新模块

这一阶段目标是先完成物理隔离，不在迁移时顺手重设计视觉风格。

### 第二阶段：清理旧共享模块与测试归属

1. 删除旧的多尺寸共享布局实现
2. 如果仍保留中间文件，确保文件名和职责一致
3. 将测试按尺寸重新归类，避免测试继续隐式依赖旧共享模块

## 测试策略

### 保留现有回归测试

保留当前像素级和布局级测试，包括：

- 2.9 字体、对齐、空白间隙、红色污染防护
- 3.7 字体、布局、红色污染防护
- Codex 和 Claude 两个 provider 在不同尺寸上的渲染结果

### 新增边界测试

新增针对“职责隔离”的测试：

- `render_codex_2_9()` 只依赖 `usage_layout_2_9`
- `render_codex_3_7()` 只依赖 `usage_layout_3_7`
- `render_claude_2_9()` 只依赖 `usage_layout_2_9`
- `render_claude_3_7()` 只依赖 `usage_layout_3_7`

### 测试组织原则

- 2.9 的像素回归测试集中验证 2.9 模块
- 3.7 的像素回归测试集中验证 3.7 模块
- provider 测试聚焦数据转换和入口分发，不承担底层多尺寸布局细节验证

## 风险与缓解

### 风险 1：迁移过程中丢失现有细节修正

例如 `2.9` 上某些对齐或字形修正被遗漏。

缓解：

- 第一阶段以“平移实现”为主，不顺手重写
- 依赖现有像素回归测试及时发现偏差

### 风险 2：重复代码后续再次漂移

不同尺寸模块中会存在相似 helper。

缓解：

- 接受有限重复，优先隔离
- 只有当某段逻辑经过多个尺寸长期验证都稳定时，才考虑回收到 common

### 风险 3：文件移动导致 import 和测试破裂

缓解：

- 保持对外 render API 名称不变
- 先替换 provider 内部 import，再删旧模块

## 完成标准

满足以下条件视为本次拆分完成：

1. `2.9inch` 与 `3.7inch` 不再共享任何字体、布局、percent/reset 绘制、bar 绘制、divider、timestamp 格式逻辑
2. `usage_codex.py` 与 `usage_claude.py` 仅保留数据解析和按尺寸分发
3. 改动任一尺寸模块的视觉细节，不需要修改另一个尺寸模块
4. 现有 usage 渲染相关测试全部通过
5. 文件命名与职责一致，不再存在一个承载多尺寸实现的误导性模块名

## 实施建议

实现阶段优先顺序建议如下：

1. 建立 `usage_layout_common.py`
2. 迁出 `2.9inch`
3. 迁出 `3.7inch`
4. 调整 provider import
5. 清理旧模块与测试

原因：

- `2.9inch` 最近改动最多、回归最频繁，先隔离收益最大
- `3.7inch` 逻辑更稳定，后迁移风险可控
