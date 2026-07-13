"""Read-only price-trigger alerts; this module never creates or sends orders."""
from __future__ import annotations
from typing import Any


def evaluate_price_alerts(watchlist: list[dict[str, Any]], prices: dict[str, float], state: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Emit one alert per threshold crossing and rearm after moving away."""
    next_state = dict(state)
    alerts: list[dict[str, Any]] = []
    for item in watchlist:
        ticker = item["ticker"].upper()
        price = prices.get(ticker)
        if price is None or price <= 0:
            continue
        entry = float(item.get("entry_price", 0))
        stop = float(item.get("stop_price", 0))
        direction = item.get("entry_direction", "at_or_below")
        entry_hit = entry > 0 and (price <= entry if direction == "at_or_below" else price >= entry)
        stop_hit = stop > 0 and price <= stop
        keys = {"entry": f"{ticker}:entry", "stop": f"{ticker}:stop"}
        if not entry_hit:
            next_state.pop(keys["entry"], None)
        if not stop_hit:
            next_state.pop(keys["stop"], None)
        if stop_hit and not next_state.get(keys["stop"]):
            alerts.append({"kind": "stop", "ticker": ticker, "price": price, "threshold": stop})
            next_state[keys["stop"]] = True
        elif entry_hit and not next_state.get(keys["entry"]):
            alerts.append({"kind": "entry", "ticker": ticker, "price": price, "threshold": entry})
            next_state[keys["entry"]] = True
    return alerts, next_state
