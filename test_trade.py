"""Utility script to validate order placement credentials and permissions.

This script intentionally places a small market order in the configured
environment. Keep it out of automated execution paths.
"""
from __future__ import annotations

import os

from binance import Client

from config import load_env


def main() -> None:
    """Submit a minimal futures market order after exchange rule validation."""
    load_env()
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError("Missing BINANCE_API_KEY or BINANCE_API_SECRET in .env")

    testnet = os.getenv("BINANCE_TESTNET", "true").lower() in {"1", "true", "yes"}
    client = Client(api_key, api_secret, testnet=testnet)
    if testnet:
        client.FUTURES_URL = "https://testnet.binancefuture.com/fapi"

    symbol = "BTCUSDT"
    side = "BUY"

    # $1 notional => qty in BTC (rounded to lot size)
    price = float(client.futures_mark_price(symbol=symbol)["markPrice"])
    notional = 1.0
    qty_raw = notional / price

    info = client.futures_exchange_info()
    step_size = None
    min_qty = None
    min_notional = None
    for s in info["symbols"]:
        if s["symbol"] == symbol:
            for f in s["filters"]:
                if f["filterType"] == "LOT_SIZE":
                    step_size = float(f["stepSize"])
                    min_qty = float(f["minQty"])
                if f["filterType"] == "MIN_NOTIONAL":
                    min_notional = float(f["notional"])
                    break
    if not step_size:
        raise RuntimeError("LOT_SIZE not found for symbol")

    precision = max(0, len(str(step_size).split(".")[1].rstrip("0")))

    # Ensure notional meets minimum before rounding.
    if min_notional is not None and notional < min_notional:
        notional = float(min_notional) * 1.1
        qty_raw = notional / price

    qty = float(round(qty_raw - (qty_raw % step_size), precision))
    if min_qty is not None and qty < min_qty:
        qty = min_qty

    if qty <= 0:
        raise RuntimeError("Calculated quantity is zero. Increase notional.")

    if min_notional is not None and (qty * price) < min_notional:
        # Bump by step size until the order satisfies min notional.
        while (qty * price) < min_notional:
            qty = float(round(qty + step_size, precision))

    order = client.futures_create_order(
        symbol=symbol,
        side=side,
        type="MARKET",
        quantity=qty,
    )
    print(order)


if __name__ == "__main__":
    main()
