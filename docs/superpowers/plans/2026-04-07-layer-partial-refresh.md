# Layer 局部刷新与提速 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 layer 传输协议（2.13inch / 2.9inch）增加字节级 diff，只发送有变化的 portrait 行，配合周期性全刷防残影。

**Architecture:** `transfer.py` 的 `_send_layer` 增加 `prev_data` 参数，逐 chunk 比较跳过未变化包；chunk 大小改为 `LAYER_ROW_BYTES`（16字节）整数倍确保行对齐且总包数 < 256；`_run_loop_cycle` 增加 `prev_layer_bytes` / `push_counts` / `full_refresh_every` 参数，`push_image` callable 新增 `source_name` 首参，让 `cmd_loop._push` 闭包负责在推送成功后更新字节缓存。

**Tech Stack:** Python 3.10+, asyncio, numpy, unittest.IsolatedAsyncioTestCase

---

## 文件变更一览

| 文件 | 变更内容 |
|------|---------|
| `bluetag/transfer.py` | 添加 `LAYER_ROW_BYTES`；改写 `_compute_chunk_size`（行对齐）；`_send_layer` 加 `prev_data`；`send_bicolor_image` 加 `prev_black_data/prev_red_data` |
| `bluetag/cli.py` | `_push_layer_image` / `_push_rendered_image` 加 prev 参数；`_run_loop_cycle` 加 `prev_layer_bytes` / `push_counts` / `full_refresh_every`，`push_image` 改为 4 参；`cmd_loop` 更新闭包和循环状态；加 `--full-refresh-every` CLI 参数 |
| `tests/test_transfer.py` | 加 `_compute_chunk_size` 测试；加 diff 跳过测试 |
| `tests/test_cli_loop.py` | 9 处 `push_image` 签名改为 `(source_name, image, prev_black=None, prev_red=None)`；加 diff 和计数测试 |

---

## Task 1：行对齐 `_compute_chunk_size`

**Files:**
- Modify: `bluetag/transfer.py`
- Modify: `tests/test_transfer.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_transfer.py` 顶部增加导入，并在 `TransferTests` 之前添加：

```python
from bluetag.transfer import _compute_chunk_size, LAYER_ROW_BYTES


class ComputeChunkSizeTests(unittest.TestCase):
    def test_2_13inch_returns_16(self) -> None:
        # 4000 bytes: ceil(4000/255)=16 → 1 row → 16
        self.assertEqual(_compute_chunk_size(4000), 16)

    def test_2_9inch_rounds_up_to_32(self) -> None:
        # 4736 bytes: ceil(4736/255)=19 → 2 rows → 32
        self.assertEqual(_compute_chunk_size(4736), 32)

    def test_result_is_multiple_of_row_bytes(self) -> None:
        for size in [4000, 4736, 1000, 8000]:
            result = _compute_chunk_size(size)
            self.assertEqual(result % LAYER_ROW_BYTES, 0, f"size={size}")

    def test_total_packets_under_256(self) -> None:
        for size in [4000, 4736]:
            chunk = _compute_chunk_size(size)
            packets = (size + chunk - 1) // chunk
            self.assertLess(packets, 256, f"size={size}, chunk={chunk}")
```

- [ ] **Step 2: 确认测试失败**

```bash
uv run python -m unittest tests.test_transfer.ComputeChunkSizeTests -v
```

预期：`ImportError: cannot import name 'LAYER_ROW_BYTES'`

- [ ] **Step 3: 实现**

在 `bluetag/transfer.py` 的 `LAYER_PAYLOAD_SIZE = 16` 下方添加常量，并替换 `_compute_chunk_size` 函数：

```python
LAYER_PAYLOAD_SIZE = 16
LAYER_ROW_BYTES = 16  # 128 pixels per portrait row ÷ 8 bits


def _compute_chunk_size(data_len: int) -> int:
    """chunk 大小为 LAYER_ROW_BYTES 的整数倍，且总包数 < 256。"""
    min_bytes = (data_len + 254) // 255
    rows_needed = (min_bytes + LAYER_ROW_BYTES - 1) // LAYER_ROW_BYTES
    return max(1, rows_needed) * LAYER_ROW_BYTES
```

- [ ] **Step 4: 确认全部测试通过**

```bash
uv run python -m unittest tests.test_transfer -v
```

预期：全部 PASS（`_compute_chunk_size(16)=16`，原有 4 writes 测试不变）

- [ ] **Step 5: Commit**

```bash
git add bluetag/transfer.py tests/test_transfer.py
git commit -m "feat: row-aligned chunk size, total packets < 256"
```

---

## Task 2：`_send_layer` 字节级 diff

**Files:**
- Modify: `bluetag/transfer.py`
- Modify: `tests/test_transfer.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_transfer.py` 的 `TransferTests` 内追加两个测试方法：

```python
    async def test_send_layer_skips_all_when_data_identical(self) -> None:
        """prev_data 与 data 相同时，不发送任何数据包（只有 START 和 END）。"""
        session = _FakeSession()

        async def fake_sleep(_: float) -> None:
            pass

        data = bytes(32)  # 32 bytes = 1 chunk for this data size
        with patch("bluetag.transfer.asyncio.sleep", fake_sleep):
            ok = await _send_layer(
                session,
                data,
                layer_type=0x13,
                layer_name="黑层",
                delay_ms=0,
                start_delay_ms=0,
                flush_every=0,
                on_progress=None,
                prev_data=data,
            )

        self.assertTrue(ok)
        START = bytes([0x13, 0, 0, 0, 0])
        END   = bytes([0x13, 0xFF, 0xFF, 0xFF, 0xFF])
        data_writes = [w for w in session.writes if w not in (START, END)]
        self.assertEqual(data_writes, [])

    async def test_send_layer_sends_changed_chunk_only(self) -> None:
        """只有第一个 chunk 变化时，仅发送该 chunk 的数据包。"""
        session = _FakeSession()

        async def fake_sleep(_: float) -> None:
            pass

        prev_data = bytes(32)
        # 前 16 字节不同，后 16 字节相同；chunk_size(32)=32，即 1 个 chunk 全发
        new_data = bytes([0xFF] * 16) + bytes(16)
        with patch("bluetag.transfer.asyncio.sleep", fake_sleep):
            await _send_layer(
                session,
                new_data,
                layer_type=0x13,
                layer_name="黑层",
                delay_ms=0,
                start_delay_ms=0,
                flush_every=0,
                on_progress=None,
                prev_data=prev_data,
            )

        START = bytes([0x13, 0, 0, 0, 0])
        END   = bytes([0x13, 0xFF, 0xFF, 0xFF, 0xFF])
        data_writes = [w for w in session.writes if w not in (START, END)]
        # 至少 1 个数据包（含首包重发最多 2 个）
        self.assertGreaterEqual(len(data_writes), 1)
        # 数据包包含变化的字节
        self.assertIn(bytes([0xFF] * 16), data_writes[0][3:])
```

- [ ] **Step 2: 确认测试失败**

```bash
uv run python -m unittest tests.test_transfer.TransferTests.test_send_layer_skips_all_when_data_identical -v
```

预期：`TypeError: _send_layer() got an unexpected keyword argument 'prev_data'`

- [ ] **Step 3: 实现**

在 `bluetag/transfer.py` 的 `_send_layer` 函数签名增加 `prev_data: bytes | None = None`：

```python
async def _send_layer(
    session: BleSession,
    data: bytes,
    *,
    layer_type: int,
    layer_name: str,
    delay_ms: int,
    start_delay_ms: int,
    flush_every: int,
    on_progress: ProgressCallback | None,
    prev_data: bytes | None = None,
) -> bool:
```

在 `while` 循环内，`chunk = data[offset : offset + chunk_size]` 之后，`packet = ...` 之前插入：

```python
            if prev_data is not None and prev_data[offset : offset + chunk_size] == chunk:
                offset += chunk_size
                packet_index += 1
                continue
```

- [ ] **Step 4: 确认全部测试通过**

```bash
uv run python -m unittest tests.test_transfer -v
```

预期：全部 PASS

- [ ] **Step 5: Commit**

```bash
git add bluetag/transfer.py tests/test_transfer.py
git commit -m "feat: skip unchanged chunks in _send_layer"
```

---

## Task 3：`send_bicolor_image` 透传 diff 参数

**Files:**
- Modify: `bluetag/transfer.py`
- Modify: `tests/test_transfer.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_transfer.py` 末尾添加：

```python
from bluetag.transfer import send_bicolor_image


class SendBicolorDiffTests(unittest.IsolatedAsyncioTestCase):
    async def test_identical_prev_data_sends_no_data_packets(self) -> None:
        """black 和 red 均与 prev 相同时，只发 4 个控制包（START+END×2）。"""
        session = _FakeSession()

        async def fake_sleep(_: float) -> None:
            pass

        data = bytes(32)
        with patch("bluetag.transfer.asyncio.sleep", fake_sleep):
            ok = await send_bicolor_image(
                session,
                black_data=data,
                red_data=data,
                delay_ms=0,
                start_delay_ms=0,
                settle_ms=0,
                flush_every=0,
                prev_black_data=data,
                prev_red_data=data,
            )

        self.assertTrue(ok)
        START_B = bytes([0x13, 0, 0, 0, 0])
        END_B   = bytes([0x13, 0xFF, 0xFF, 0xFF, 0xFF])
        START_R = bytes([0x12, 0, 0, 0, 0])
        END_R   = bytes([0x12, 0xFF, 0xFF, 0xFF, 0xFF])
        self.assertEqual(session.writes, [START_B, END_B, START_R, END_R])
```

- [ ] **Step 2: 确认测试失败**

```bash
uv run python -m unittest tests.test_transfer.SendBicolorDiffTests -v
```

预期：`TypeError: send_bicolor_image() got an unexpected keyword argument 'prev_black_data'`

- [ ] **Step 3: 实现**

将 `bluetag/transfer.py` 中 `send_bicolor_image` 整体替换为：

```python
async def send_bicolor_image(
    session: BleSession,
    black_data: bytes,
    red_data: bytes,
    *,
    delay_ms: int,
    start_delay_ms: int,
    settle_ms: int,
    flush_every: int = 0,
    on_progress: ProgressCallback | None = None,
    prev_black_data: bytes | None = None,
    prev_red_data: bytes | None = None,
) -> bool:
    """Send black and red layers using the small-screen legacy format."""
    if not await _send_layer(
        session,
        black_data,
        layer_type=BLACK_TYPE,
        layer_name="黑层",
        delay_ms=delay_ms,
        start_delay_ms=start_delay_ms,
        flush_every=flush_every,
        on_progress=on_progress,
        prev_data=prev_black_data,
    ):
        return False

    await asyncio.sleep(0.1)

    if not await _send_layer(
        session,
        red_data,
        layer_type=RED_TYPE,
        layer_name="红层",
        delay_ms=delay_ms,
        start_delay_ms=start_delay_ms,
        flush_every=flush_every,
        on_progress=on_progress,
        prev_data=prev_red_data,
    ):
        return False

    if settle_ms > 0:
        await asyncio.sleep(settle_ms / 1000.0)

    return True
```

- [ ] **Step 4: 确认全部测试通过**

```bash
uv run python -m unittest tests.test_transfer -v
```

预期：全部 PASS

- [ ] **Step 5: Commit**

```bash
git add bluetag/transfer.py tests/test_transfer.py
git commit -m "feat: send_bicolor_image accepts prev layer bytes for diff"
```

---

## Task 4：`cli.py` push 链路透传 diff 参数

**Files:**
- Modify: `bluetag/cli.py`

- [ ] **Step 1: 修改 `_push_layer_image`**

将函数替换为（增加 `prev_black_data` / `prev_red_data` 参数）：

```python
async def _push_layer_image(
    profile: ScreenProfile,
    target: dict,
    black_data: bytes,
    red_data: bytes,
    interval_ms: int,
    prev_black_data: bytes | None = None,
    prev_red_data: bytes | None = None,
) -> bool:
    from bluetag.ble import connect_session

    session = await connect_session(
        target.get("_ble_device") or target["address"],
        timeout=20.0,
        connect_retries=DEFAULT_CONNECT_RETRIES,
    )
    if not session:
        return False

    try:
        print(
            f"连接 {target['name']} [{profile.name}], "
            f"黑层 {len(black_data)} bytes, 红层 {len(red_data)} bytes"
        )
        return await send_bicolor_image(
            session,
            black_data,
            red_data,
            delay_ms=interval_ms,
            start_delay_ms=profile.layer_start_delay_ms,
            settle_ms=profile.settle_ms,
            flush_every=profile.flush_every,
            on_progress=_layer_progress,
            prev_black_data=prev_black_data,
            prev_red_data=prev_red_data,
        )
    finally:
        await session.close()
```

- [ ] **Step 2: 修改 `_push_rendered_image`**

将函数替换为：

```python
async def _push_rendered_image(
    profile: ScreenProfile,
    target: dict,
    image: Image.Image,
    prev_black_data: bytes | None = None,
    prev_red_data: bytes | None = None,
) -> bool:
    interval_ms = profile.default_interval_ms
    if profile.transport == "frame":
        _preview, data_2bpp = _build_frame_preview_and_payload(image, profile)
        return await _push_frame_image(profile, target, data_2bpp, interval_ms)

    _preview, black_data, red_data = _build_layer_preview_and_payload(image, profile)
    return await _push_layer_image(
        profile, target, black_data, red_data, interval_ms,
        prev_black_data=prev_black_data,
        prev_red_data=prev_red_data,
    )
```

- [ ] **Step 3: 确认全部测试通过**

```bash
uv run python -m unittest discover -s tests -v
```

预期：全部 PASS（新参数有默认值，现有调用不受影响）

- [ ] **Step 4: Commit**

```bash
git add bluetag/cli.py
git commit -m "feat: thread prev layer bytes through _push_layer_image and _push_rendered_image"
```

---

## Task 5：`_run_loop_cycle` 状态追踪 + `cmd_loop` 集成

**Files:**
- Modify: `bluetag/cli.py`
- Modify: `tests/test_cli_loop.py`

`push_image` callable 签名改为 `(source_name: str, image: Image.Image, prev_black: bytes | None, prev_red: bytes | None) -> bool`，让闭包知道当前 source 以便更新缓存。

- [ ] **Step 1: 批量更新 `test_cli_loop.py` 中 9 处 `push_image` 签名**

将文件中所有：
```python
        async def push_image(image):
```
替换为：
```python
        async def push_image(source_name, image, prev_black=None, prev_red=None):
```

```bash
sed -i '' 's/async def push_image(image):/async def push_image(source_name, image, prev_black=None, prev_red=None):/g' tests/test_cli_loop.py
```

- [ ] **Step 2: 确认现有测试仍通过**

```bash
uv run python -m unittest tests.test_cli_loop -v
```

预期：全部 PASS

- [ ] **Step 3: 写新行为的失败测试**

在 `tests/test_cli_loop.py` 末尾添加：

```python
class CliLoopDiffTests(unittest.TestCase):
    def _make_source(self, name: str, left_percent: float = 50.0) -> "UsageLoopSource":
        def fetch(*, timeout: float):
            return {"left": left_percent}

        def refresh_rows(payload):
            return [(name, payload["left"])]

        def render(payload, tzinfo, *, font_path=None):
            return f"image:{name}"

        return UsageLoopSource(
            name=name,
            timeout=5.0,
            fetch=fetch,
            refresh_rows=refresh_rows,
            bar_inner_width=100,
            render=render,
        )

    def test_first_push_receives_none_prev_bytes(self) -> None:
        """第一次推送时 prev_black / prev_red 均为 None。"""
        received: list[tuple] = []

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            received.append((source_name, prev_black, prev_red))
            return True

        prev_layer_bytes: dict = {}
        push_counts: dict = {}

        asyncio.run(
            _run_loop_cycle(
                sources=[self._make_source("codex")],
                screen_name="2.9inch",
                tzinfo=None,
                font_path=None,
                push_image=push_image,
                interval_seconds=0,
                sleep=lambda _: asyncio.sleep(0),
                prev_layer_bytes=prev_layer_bytes,
                push_counts=push_counts,
                full_refresh_every=5,
            )
        )

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], "codex")
        self.assertIsNone(received[0][1])
        self.assertIsNone(received[0][2])

    def test_push_counts_increment_on_success(self) -> None:
        push_counts: dict = {}

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            return True

        asyncio.run(
            _run_loop_cycle(
                sources=[self._make_source("codex")],
                screen_name="2.9inch",
                tzinfo=None,
                font_path=None,
                push_image=push_image,
                interval_seconds=0,
                sleep=lambda _: asyncio.sleep(0),
                prev_layer_bytes={},
                push_counts=push_counts,
                full_refresh_every=5,
            )
        )

        self.assertEqual(push_counts.get("codex"), 1)

    def test_full_refresh_when_count_reaches_threshold(self) -> None:
        """count 达到 full_refresh_every 时传 None 并重置计数。"""
        received: list[tuple] = []
        push_counts = {"codex": 5}
        prev_layer_bytes = {"codex": (b"old_black", b"old_red")}

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            received.append((prev_black, prev_red))
            return True

        asyncio.run(
            _run_loop_cycle(
                sources=[self._make_source("codex", left_percent=49.0)],
                screen_name="2.9inch",
                tzinfo=None,
                font_path=None,
                push_image=push_image,
                interval_seconds=0,
                sleep=lambda _: asyncio.sleep(0),
                prev_layer_bytes=prev_layer_bytes,
                push_counts=push_counts,
                full_refresh_every=5,
            )
        )

        self.assertEqual(len(received), 1)
        self.assertIsNone(received[0][0])   # 全刷，prev=None
        self.assertEqual(push_counts["codex"], 0)  # 重置

    def test_count_not_updated_on_failed_push(self) -> None:
        push_counts: dict = {}

        async def push_image(source_name, image, prev_black=None, prev_red=None):
            return False  # 推送失败

        asyncio.run(
            _run_loop_cycle(
                sources=[self._make_source("codex")],
                screen_name="2.9inch",
                tzinfo=None,
                font_path=None,
                push_image=push_image,
                interval_seconds=0,
                sleep=lambda _: asyncio.sleep(0),
                prev_layer_bytes={},
                push_counts=push_counts,
                full_refresh_every=5,
            )
        )

        self.assertEqual(push_counts.get("codex", 0), 0)
```

- [ ] **Step 4: 确认测试失败**

```bash
uv run python -m unittest tests.test_cli_loop.CliLoopDiffTests -v
```

预期：`TypeError: _run_loop_cycle() got an unexpected keyword argument 'prev_layer_bytes'`

- [ ] **Step 5: 修改 `_run_loop_cycle`**

将函数签名和内部逻辑替换为：

```python
async def _run_loop_cycle(
    *,
    sources: Sequence[UsageLoopSource],
    screen_name: str,
    tzinfo,
    font_path: str | None,
    push_image: Callable[..., Awaitable[bool]],
    interval_seconds: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    refresh_states: dict[str, UsageRefreshState] | None = None,
    prev_layer_bytes: dict[str, tuple[bytes, bytes]] | None = None,
    push_counts: dict[str, int] | None = None,
    full_refresh_every: int = 5,
) -> dict[str, UsageRefreshState]:
    states = {} if refresh_states is None else dict(refresh_states)
    layer_bytes = prev_layer_bytes if prev_layer_bytes is not None else {}
    counts = push_counts if push_counts is not None else {}

    for source in sources:
        try:
            payload = source.fetch(timeout=source.timeout)
            current_state = _build_refresh_state(
                source_name=source.name,
                screen_name=screen_name,
                rows=source.refresh_rows(payload),
                bar_inner_width=source.bar_inner_width,
            )
        except Exception as exc:
            print(f"❌ {source.name} usage failed: {exc}", file=sys.stderr)
            await sleep(interval_seconds)
            continue

        previous = states.get(source.name)
        reason = _refresh_reason(previous, current_state)
        if reason is None:
            print(f"skip {source.name} refresh: no meaningful value change")
            await sleep(interval_seconds)
            continue

        current_count = counts.get(source.name, 0)
        force_full = current_count >= full_refresh_every

        if force_full or source.name not in layer_bytes:
            prev_black, prev_red = None, None
        else:
            prev_black, prev_red = layer_bytes[source.name]

        try:
            image = source.render(payload, tzinfo, font_path=font_path)
            ok = await push_image(source.name, image, prev_black, prev_red)
        except Exception as exc:
            print(f"❌ {source.name} push failed: {exc}", file=sys.stderr)
            ok = False

        if ok:
            states[source.name] = current_state
            counts[source.name] = 0 if force_full else current_count + 1
            print(f"push {source.name} refresh: {reason}{' (full)' if force_full else ''}")
        else:
            print(f"❌ {source.name} push failed", file=sys.stderr)
        await sleep(interval_seconds)

    return states
```

- [ ] **Step 6: 确认全部测试通过**

```bash
uv run python -m unittest discover -s tests -v
```

预期：全部 PASS

- [ ] **Step 7: Commit**

```bash
git add bluetag/cli.py tests/test_cli_loop.py
git commit -m "feat: _run_loop_cycle tracks prev layer bytes and push counts for partial refresh"
```

---

## Task 6：`cmd_loop` 集成 + `--full-refresh-every` CLI 参数

**Files:**
- Modify: `bluetag/cli.py`

- [ ] **Step 1: 修改 `cmd_loop` 中的 `_loop` 函数**

将 `_loop` 内部替换为：

```python
    async def _loop():
        target = await _find_target(args, profile)
        if not target:
            print("❌ 未找到设备")
            return

        print(
            f"开始循环刷新 {profile.name} 设备 {target['name']} ({target['address']}), "
            f"间隔 {args.interval}s, 每 {args.full_refresh_every} 次局部刷后全刷一次"
        )

        prev_layer_bytes: dict[str, tuple[bytes, bytes]] = {}
        push_counts: dict[str, int] = {}

        async def _push(
            source_name: str,
            image: Image.Image,
            prev_black: bytes | None,
            prev_red: bytes | None,
        ) -> bool:
            if profile.transport == "frame":
                return await _push_rendered_image(profile, target, image)
            # layer 协议：自行计算字节以便缓存
            _preview, black_data, red_data = _build_layer_preview_and_payload(image, profile)
            ok = await _push_layer_image(
                profile, target, black_data, red_data, profile.default_interval_ms,
                prev_black_data=prev_black,
                prev_red_data=prev_red,
            )
            if ok:
                prev_layer_bytes[source_name] = (black_data, red_data)
            return ok

        refresh_states: dict[str, UsageRefreshState] = {}
        while True:
            refresh_states = await _run_loop_cycle(
                sources=sources,
                screen_name=profile.name,
                tzinfo=tzinfo,
                font_path=args.font,
                push_image=_push,
                interval_seconds=float(args.interval),
                refresh_states=refresh_states,
                prev_layer_bytes=prev_layer_bytes,
                push_counts=push_counts,
                full_refresh_every=args.full_refresh_every,
            )
```

- [ ] **Step 2: 为 `loop` 子命令增加 `--full-refresh-every` 参数**

在 `main()` 的 `loop_p.add_argument("--font", ...)` 之后添加：

```python
    loop_p.add_argument(
        "--full-refresh-every",
        type=int,
        default=5,
        dest="full_refresh_every",
        help="每 N 次局部刷后强制全刷一次，防止残影（默认 5）",
    )
```

- [ ] **Step 3: 确认全部测试通过**

```bash
uv run python -m unittest discover -s tests -v
```

预期：全部 PASS

- [ ] **Step 4: 手动验证 CLI 参数注册**

```bash
uv run bluetag loop --help | grep full-refresh
```

预期输出包含：`--full-refresh-every`

- [ ] **Step 5: Commit**

```bash
git add bluetag/cli.py
git commit -m "feat: cmd_loop integrates partial refresh with --full-refresh-every option"
```

---

## 自查

- **Task 1** 覆盖 spec §1（chunk 行对齐）✓  
- **Task 2** 覆盖 spec §2（`_send_layer` diff）✓  
- **Task 3** 覆盖 spec §2（`send_bicolor_image` 透传）✓  
- **Task 4** 覆盖 spec §3（push 链路透传）✓  
- **Task 5** 覆盖 spec §3（`_run_loop_cycle` 状态追踪）✓  
- **Task 6** 覆盖 spec §3（`cmd_loop` 集成）+ spec §4（`--full-refresh-every`）✓  
- frame transport 路径无 diff（spec 明确不在范围内）✓  
- `push`/`text` 子命令不受影响（新参数均有默认值）✓
