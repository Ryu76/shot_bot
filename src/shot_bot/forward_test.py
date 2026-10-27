"""One-week forward test using live quotes and virtual fills only.

This module never calls a trading/order API. It reads the selected universe on
every cycle, records the live quotes it received, and applies resulting trade
actions to a local virtual cash/holdings ledger.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from alerts import TradeAction, evaluate_trade_actions
from hantoo_api import HantooClient


_QUOTE_EXCHANGES = {"NASD": "NAS", "NYSE": "NYS", "AMEX": "AMS"}


@dataclass
class ForwardTestState:
    started_at: str
    ends_at: str
    initial_cash: float
    cash: float
    holdings: dict[str, int] = field(default_factory=dict)
    last_prices: dict[str, float] = field(default_factory=dict)
    action_state: dict[str, Any] = field(default_factory=dict)
    cycles: int = 0

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ForwardTestState":
        return cls(**value)


class ForwardTest:
    """Persisted virtual portfolio for a bounded forward-test period."""

    def __init__(self, directory: str | Path, *, initial_cash: float, duration_days: int = 7, fee_bps: float = 0.0):
        if initial_cash <= 0 or duration_days < 1 or fee_bps < 0:
            raise ValueError("initial_cash and duration_days must be positive; fee_bps cannot be negative")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.state_path = self.directory / "state.json"
        self.events_path = self.directory / "events.jsonl"
        self.fee_rate = fee_bps / 10_000
        if self.state_path.exists():
            self.state = ForwardTestState.from_dict(json.loads(self.state_path.read_text(encoding="utf-8")))
        else:
            now = datetime.now(timezone.utc)
            self.state = ForwardTestState(
                started_at=now.isoformat(),
                ends_at=(now + timedelta(days=duration_days)).isoformat(),
                initial_cash=initial_cash,
                cash=initial_cash,
            )
            self._save_state()

    @property
    def is_finished(self) -> bool:
        return datetime.now(timezone.utc) >= datetime.fromisoformat(self.state.ends_at)

    def record_cycle(
        self,
        selected: list[dict[str, Any]],
        prices: dict[str, float],
        *,
        quote_errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Apply a single virtual-fill cycle and append an auditable event."""
        if self.is_finished:
            raise RuntimeError("forward-test period has ended")
        actions, action_state = evaluate_trade_actions(selected, prices, self.state.holdings, self.state.action_state)
        self.state.last_prices.update(prices)
        fills: list[dict[str, Any]] = []
        for action in actions:
            fill = self._virtual_fill(action)
            if fill is None:
                # A non-filled action must be eligible again on the next quote.
                action_state.pop(f"{action.ticker}:{action.side}:{action.reason}", None)
                continue
            fills.append(fill)
            if fill["quantity"] != action.quantity:
                action_state.pop(f"{action.ticker}:{action.side}:{action.reason}", None)
        self.state.action_state = action_state
        self.state.cycles += 1
        equity = self.state.cash + sum(
            quantity * self.state.last_prices.get(ticker, 0)
            for ticker, quantity in self.state.holdings.items()
        )
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cycle": self.state.cycles,
            "quotes": prices,
            "quote_errors": quote_errors or {},
            "actions": [asdict(action) for action in actions],
            "fills": fills,
            "cash": self.state.cash,
            "holdings": self.state.holdings,
            "marked_equity": equity,
        }
        with self.events_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        self._save_state()
        return event

    def _virtual_fill(self, action: TradeAction) -> dict[str, Any] | None:
        if action.side == "buy":
            unit_cost = action.limit_price * (1 + self.fee_rate)
            quantity = min(action.quantity, int(self.state.cash // unit_cost))
            if quantity < 1:
                return None
            total = quantity * unit_cost
            self.state.cash -= total
            self.state.holdings[action.ticker] = self.state.holdings.get(action.ticker, 0) + quantity
        else:
            quantity = min(action.quantity, self.state.holdings.get(action.ticker, 0))
            if quantity < 1:
                return None
            total = quantity * action.limit_price * (1 - self.fee_rate)
            self.state.cash += total
            remaining = self.state.holdings[action.ticker] - quantity
            if remaining:
                self.state.holdings[action.ticker] = remaining
            else:
                self.state.holdings.pop(action.ticker)
        return {"side": action.side, "ticker": action.ticker, "quantity": quantity, "price": action.limit_price, "reason": action.reason, "notional": total}

    def _save_state(self) -> None:
        self.state_path.write_text(json.dumps(asdict(self.state), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def load_selected(path: str | Path) -> list[dict[str, Any]]:
    """Read a selected-universe JSON array (up to 50 stocks)."""
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("selected file must contain a JSON array")
    return value


def fetch_live_prices(client: HantooClient, selected: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, str]]:
    """Fetch current prices from the documented overseas current-price API."""
    prices: dict[str, float] = {}
    errors: dict[str, str] = {}
    for item in selected[:50]:
        ticker = str(item["ticker"]).upper()
        exchange = str(item.get("quote_exchange") or _QUOTE_EXCHANGES.get(str(item.get("exchange", "NASD")).upper(), "")).upper()
        if not exchange:
            errors[ticker] = "set quote_exchange for this exchange"
            continue
        try:
            response = client.price(AUTH="", EXCD=exchange, SYMB=ticker)
            price = float(response["output"]["last"])
            if price <= 0:
                raise ValueError("non-positive last price")
            prices[ticker] = price
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            errors[ticker] = str(error)
    return prices, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Record live quotes and virtual fills; never sends orders.")
    parser.add_argument("--selected", required=True, help="JSON file containing the current selected universe")
    parser.add_argument("--directory", default=".forward_test", help="local state and event output directory")
    parser.add_argument("--initial-cash", required=True, type=float)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--fee-bps", type=float, default=0.0)
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--once", action="store_true", help="run one cycle only")
    args = parser.parse_args()
    if args.interval_seconds < 1:
        parser.error("--interval-seconds must be positive")

    test = ForwardTest(args.directory, initial_cash=args.initial_cash, duration_days=args.days, fee_bps=args.fee_bps)
    client = HantooClient.from_env()
    while not test.is_finished:
        selected = load_selected(args.selected)  # reload permits scheduled rebalancing
        prices, errors = fetch_live_prices(client, selected)
        event = test.record_cycle(selected, prices, quote_errors=errors)
        print(json.dumps({"cycle": event["cycle"], "fills": event["fills"], "marked_equity": event["marked_equity"]}, ensure_ascii=False))
        if args.once:
            return
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
