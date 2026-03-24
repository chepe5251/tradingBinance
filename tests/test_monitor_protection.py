from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from monitor_protection import ensure_monitor_protections


@pytest.mark.unit
def test_monitor_protection_returns_none_when_position_not_visible() -> None:
    monitor = SimpleNamespace(
        executor=SimpleNamespace(
            paper=False,
            has_open_position=MagicMock(return_value=False),
        ),
        trades_logger=MagicMock(),
        symbol="BTCUSDT",
        side="BUY",
        client_id_prefix="cid",
        trace_id="trace-1",
        _ops_call=MagicMock(),  # noqa: SLF001
    )
    trade_state = {"tp": 110.0, "sl": 90.0, "qty": 1.0}

    with patch("monitor_protection.time.time", side_effect=[0.0, 9.0]):
        refs = ensure_monitor_protections(monitor, trade_state)

    assert refs is None
    monitor._ops_call.assert_any_call(  # noqa: SLF001
        "record_protection_result",
        symbol="BTCUSDT",
        ok=False,
        stage="position_closed_no_protection",
        trace_id="trace-1",
    )

