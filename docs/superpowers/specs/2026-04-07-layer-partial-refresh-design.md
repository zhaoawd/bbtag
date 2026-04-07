# Layer 局部刷新与提速设计

**日期**：2026-04-07  
**适用屏幕**：2.13inch / 2.9inch（layer 传输协议）

---

## 背景

当前 `loop` 命令每次刷新均发送完整图像（2.9 寸约 57 秒/次）。
项目已有基于阈值的「是否刷新」判断（`_refresh_reason`），但刷新时仍传输全量数据。

目标：在现有策略基础上增加字节级 diff，只通过 BLE 发送有变化的 portrait 行，配合周期性全刷防残影。

---

## 设计

### 1. chunk 行对齐（`transfer.py`）

增加常量 `LAYER_ROW_BYTES = 16`（128像素/行 ÷ 8位 = 16字节）。

修改 `_compute_chunk_size(data_len)` 使返回值为 `LAYER_ROW_BYTES` 的整数倍：

```
min_bytes = ceil(data_len / 255)
rows_needed = ceil(min_bytes / LAYER_ROW_BYTES)
chunk_size = max(1, rows_needed) * LAYER_ROW_BYTES
```

结果：
- 2.9 寸（4736 bytes）：chunk=32，148包 < 256 ✓，每包对应 2 个 portrait 行
- 2.13 寸（4000 bytes）：chunk=16，250包 < 256 ✓，每包对应 1 个 portrait 行

### 2. 字节级 diff 发送（`transfer.py`）

`_send_layer` 增加参数 `prev_data: bytes | None = None`。

逐 chunk 比较：若 `prev_data[offset:offset+chunk_size] == chunk`，则跳过本包写入，但 `packet_index` 仍递增（固件使用 index 定位，跳过的位置保留屏幕原有数据）。

`send_bicolor_image` 同步增加 `prev_black_data: bytes | None = None` 和 `prev_red_data: bytes | None = None`，透传至 `_send_layer`。

### 3. 循环状态扩展（`cli.py`）

`_run_loop_cycle` 增加两个状态字典（随 `refresh_states` 同进同出）：

- `prev_layer_bytes: dict[str, tuple[bytes, bytes]]`  
  key = source name，value = (last_black_data, last_red_data)

- `push_counts: dict[str, int]`  
  key = source name，记录连续局部刷次数

决策逻辑（在现有 `_refresh_reason` 判断后）：

```
if push_counts[source] >= full_refresh_every:
    force_full = True，重置计数
else:
    force_full = False

push_image(image, prev_data=(None if force_full else prev_layer_bytes[source]))
```

成功推送后更新 `prev_layer_bytes[source]` 和 `push_counts[source]`。

`_push_layer_image` 增加 `prev_black_data / prev_red_data` 参数并传给 `send_bicolor_image`。

### 4. CLI 参数

`loop` 子命令增加 `--full-refresh-every N`（默认 5），控制每 N 次局部刷后强制全刷一次。

---

## 数据流

```
_run_loop_cycle
  ├─ fetch() + _refresh_reason()  ← 现有：决定是否刷新
  └─ 刷新时
       ├─ push_count >= N → 全刷（prev_data=None），重置计数
       └─ 否则 → 传 prev_layer_bytes → _send_layer 按 chunk diff 发送
```

---

## 不在范围内

- 硬件局部刷新（固件不支持）
- `push` / `text` 子命令的 diff 优化（单次推送，无历史状态）
- delay_ms 调参（可后续独立实验）
