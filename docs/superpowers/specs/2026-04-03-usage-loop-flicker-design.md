# Usage Loop Flicker Reduction 设计

## 概述

当前 `bluetag loop` 在每个轮次都会执行完整链路：

1. 拉取 usage 数据
2. 重新渲染整张图
3. 推送整屏内容到电子墨水屏

这会导致电子墨水屏频繁整屏刷新，闪烁明显。第一阶段优化目标不是引入底层局部刷新协议，而是在应用层减少“没有有效视觉变化时的整屏刷新次数”，重点关注数值和进度比例变化。

## 目标

- 显著减少 `bluetag loop` 的无意义整屏刷新
- 优先以“数值变化”和“进度条比例变化”为刷新依据
- 不要求顶部时间、重置时间文案实时驱动刷新
- 不修改现有 BLE 协议和底层传输格式
- 保持现有 `Codex` / `Claude Code` 双 source 交替逻辑

## 非目标

- 不实现硬件层真正的 partial refresh / partial update
- 不改造 `2.13inch` 或 `3.7inch` 的底层协议
- 不引入新的设备固件假设
- 不把 Kimi usage 纳入本次优化范围

## 方案选型

### 方案 A：刷新判定门控（推荐）

在 `loop` 调度层新增“是否值得刷新”的判定逻辑。每轮先抓取 usage，再从 payload 提取稳定摘要，与上一次成功推送的摘要比较。只有关键状态变化时，才执行渲染和推送。

优点：

- 风险最低
- 不依赖设备局刷能力
- 能立刻减少闪烁
- 代码改动集中在 CLI loop 和 usage 模块接口

缺点：

- 不是严格意义上的局部刷新
- 当文案变化但数值未变时，不会更新屏幕

### 方案 B：直接比较新旧渲染图

每轮都渲染，但推送前比较新旧位图差异，差异低于阈值则跳过。

缺点：

- 仍需要渲染整图
- 容易被时间文案和排版细节触发无意义变化
- 阈值难调

### 方案 C：混合摘要 + 位图判定

先看结构化摘要，再看关键区域像素差异。

缺点：

- 第一版过度设计
- 实现和测试复杂度更高

最终采用方案 A。

## 架构设计

### 模块职责

#### `bluetag/cli.py`

负责：

- 在 `loop` 运行时为每个 source 保存“最后一次成功推送的摘要状态”
- 在抓取 payload 后执行刷新判定
- 仅在需要刷新时调用渲染和推送
- 推送成功后更新状态缓存

不负责：

- 理解不同 provider 的原始 payload 结构细节

#### `bluetag/usage_codex.py`

新增一个稳定摘要提取接口，用于把 Codex payload 转成可比较的判定行数据。

#### `bluetag/usage_claude.py`

新增一个稳定摘要提取接口，用于把 Claude payload 转成可比较的判定行数据。

## 数据模型

新增轻量判定模型，建议放在 `bluetag/cli.py`：

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

说明：

- `label` 用于保证比较时行语义稳定
- `left_percent_int` 表示整数百分比变化
- `bar_fill_px` 表示实际视觉宽度变化
- 不包含顶部当前时间
- 不包含 `resets_text`

## 刷新判定规则

### 强制刷新条件

- 当前 source 没有历史成功推送状态
- 行数量变化
- 行 label 顺序变化

### 普通刷新条件

只要任意一行满足以下任一条件，即允许刷新：

- `left_percent_int` 变化
- `bar_fill_px` 变化

### 不触发刷新条件

以下变化不应触发刷新：

- 顶部当前时间变化
- `resets_text` 文案变化
- 仅浮点小数变化但整数百分比与 bar 像素都不变

## Bar 像素计算

为了让判定与真实视觉一致，每个 usage 模块需要提供与其当前渲染逻辑一致的 bar fill 像素计算方式。

建议 provider 模块新增函数：

```python
def build_codex_refresh_rows(payload: dict[str, Any], screen: str) -> list[UsageRefreshRowData]
def build_claude_refresh_rows(payload: dict[str, Any], screen: str) -> list[UsageRefreshRowData]
```

返回值至少应包含：

- `label`
- `left_percent`

`cli.py` 再根据屏幕尺寸和布局常量把 `left_percent` 转为：

- `left_percent_int = int(round(left_percent))`
- `bar_fill_px = ...`

这样可以避免把 CLI 绑定到 provider payload 结构，但保留对布局的集中控制。

## 数据流

新的单轮 source 处理流程：

1. `fetch payload`
2. `provider.build_*_refresh_rows(payload, screen)`
3. `cli` 将 row 数据转换为 `UsageRefreshState`
4. 比较当前状态与该 source 上次成功推送状态
5. 如果无需刷新：
   - 输出 skip 日志
   - 不渲染
   - 不推送
6. 如果需要刷新：
   - 调用现有 render 函数
   - 调用现有 push 流程
   - 仅在 push 成功后写入新的状态

## 错误处理

### 抓取失败

- 打印错误
- 保留旧状态
- 不清空缓存
- 进入下一个 source 或下一轮

### 渲染失败

- 打印错误
- 保留旧状态
- 不更新缓存

### 推送失败

- 打印错误
- 保留旧状态
- 不更新缓存

原因：状态缓存表示“屏幕上最后一次成功显示的内容”，不是“最近一次尝试渲染的内容”。

## 日志行为

新增明确日志，便于确认优化是否生效：

- `skip codex refresh: no meaningful value change`
- `skip claude refresh: no meaningful value change`
- `push codex refresh: first frame`
- `push claude refresh: percent changed`
- `push codex refresh: bar width changed`

日志原因不需要极细，但要足够判断是否因为门控生效而减少闪烁。

## 测试策略

新增测试覆盖以下场景：

1. 首次无历史状态时，必须推送
2. 整数百分比和 bar 像素都没变时，跳过推送
3. 整数百分比变化时，执行推送
4. 整数百分比没变但 bar 像素变化时，执行推送
5. 仅 `resets_text` 变化时，跳过推送
6. 推送失败时，不更新缓存状态
7. Codex 和 Claude 各自维护独立状态，互不污染

## 落地步骤

1. 在 `usage_codex.py` / `usage_claude.py` 暴露 refresh row 构造接口
2. 在 `cli.py` 增加 refresh state 数据结构与比较逻辑
3. 调整 `loop` 单轮执行流程，先判定再渲染推送
4. 为 skip / push 原因补日志
5. 补单元测试并验证

## 兼容性影响

- CLI 参数不变
- 默认行为改变为“有意义变化才刷新”
- 用户会看到时间文案可能不持续变化，但数值与比例变化仍会及时刷新
- 闪烁频率应明显下降

## 成功标准

- `loop` 在 usage 数值基本不变时，多轮运行不再持续整屏刷新
- 当剩余百分比或进度条宽度发生变化时，仍能正常刷新
- 现有 CLI 和测试仍可通过
