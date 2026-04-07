from __future__ import annotations

import unittest
from unittest.mock import patch

from bluetag.transfer import (
    LAYER_ROW_BYTES,
    _compute_chunk_size,
    _send_layer,
    send_bicolor_image,
)


class ComputeChunkSizeTests(unittest.TestCase):
    def test_2_13inch_returns_16(self) -> None:
        self.assertEqual(_compute_chunk_size(4000), 16)

    def test_2_9inch_rounds_up_to_32(self) -> None:
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


class _FakeSession:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.flush_count = 0

    async def write(self, data: bytes, response: bool = False) -> None:
        self.writes.append(data)

    async def flush(self) -> bool:
        self.flush_count += 1
        return True


class TransferTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_layer_skips_all_when_data_identical(self) -> None:
        session = _FakeSession()

        async def fake_sleep(_: float) -> None:
            pass

        data = bytes(32)
        with patch("bluetag.transfer.asyncio.sleep", fake_sleep):
            ok = await _send_layer(
                session,
                data,
                layer_type=0x13,
                layer_name="黑层",
                delay_ms=0,
                flush_every=0,
                on_progress=None,
                prev_data=data,
            )

        self.assertTrue(ok)
        start = bytes([0x13, 0, 0, 0, 0])
        end = bytes([0x13, 0xFF, 0xFF, 0xFF, 0xFF])
        data_writes = [w for w in session.writes if w not in (start, end)]
        self.assertEqual(data_writes, [])

    async def test_send_layer_sends_changed_chunk_only(self) -> None:
        session = _FakeSession()

        async def fake_sleep(_: float) -> None:
            pass

        prev_data = bytes(32)
        new_data = bytes([0xFF] * 16) + bytes(16)
        with patch("bluetag.transfer.asyncio.sleep", fake_sleep):
            await _send_layer(
                session,
                new_data,
                layer_type=0x13,
                layer_name="黑层",
                delay_ms=0,
                flush_every=0,
                on_progress=None,
                prev_data=prev_data,
            )

        start = bytes([0x13, 0, 0, 0, 0])
        end = bytes([0x13, 0xFF, 0xFF, 0xFF, 0xFF])
        data_writes = [w for w in session.writes if w not in (start, end)]
        self.assertGreaterEqual(len(data_writes), 1)
        self.assertEqual(data_writes[0][3:], bytes([0xFF] * 16))


class SendBicolorDiffTests(unittest.IsolatedAsyncioTestCase):
    async def test_identical_prev_data_sends_no_data_packets(self) -> None:
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
                settle_ms=0,
                flush_every=0,
                prev_black_data=data,
                prev_red_data=data,
            )

        self.assertTrue(ok)
        start_b = bytes([0x13, 0, 0, 0, 0])
        end_b = bytes([0x13, 0xFF, 0xFF, 0xFF, 0xFF])
        start_r = bytes([0x12, 0, 0, 0, 0])
        end_r = bytes([0x12, 0xFF, 0xFF, 0xFF, 0xFF])
        self.assertEqual(session.writes, [start_b, end_b, start_r, end_r])


if __name__ == "__main__":
    unittest.main()
