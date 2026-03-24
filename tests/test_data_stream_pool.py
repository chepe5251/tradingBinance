from __future__ import annotations

import threading
import unittest

import pytest

from data_stream import MarketDataStream


class _DummySession:
    def mount(self, *_args, **_kwargs) -> None:
        return None


class _KlineClient:
    def __init__(self) -> None:
        self.session = _DummySession()

    def futures_klines(self, symbol: str, interval: str, limit: int = 3) -> list[list[str | int]]:
        base = 100.0 if symbol == "BTCUSDT" else 200.0
        return [
            [
                1_700_000_000_000 + i * 60_000,
                f"{base + i:.4f}",
                f"{base + i + 1:.4f}",
                f"{base + i - 1:.4f}",
                f"{base + i + 0.5:.4f}",
                "100.0",
                1_700_000_000_000 + (i + 1) * 60_000 - 1,
            ]
            for i in range(limit)
        ]


@pytest.mark.unit
class DataStreamPoolTests(unittest.TestCase):
    def test_refresh_uses_fixed_pool_instance(self) -> None:
        stream = MarketDataStream(
            client=_KlineClient(),
            symbols=["BTCUSDT", "ETHUSDT"],
            main_interval="15m",
            main_limit=10,
            extra_intervals={"1h": 10},
            max_workers=2,
        )

        stream._refresh_all()  # noqa: SLF001
        first_pool = stream._pool  # noqa: SLF001
        assert first_pool is not None

        stream._refresh_all()  # noqa: SLF001
        assert stream._pool is first_pool  # noqa: SLF001

        poll_threads = [
            thread for thread in threading.enumerate() if thread.name.startswith("md-poll")
        ]
        assert len(poll_threads) <= 2

        stream.stop()

