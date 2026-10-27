"""Selected-stock trade planning, rebalancing, and guarded order submission."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from typing import Any, Literal, Protocol

from hantoo_api import load_dotenv


Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class TradeAction:
    """One limit-order instruction produced from signals and current holdings."""

    side: Side
    ticker: str
    quantity: int
    limit_price: float
    reason: str
    exchange: str = "NASD"


class OrderClient(Protocol):
    """The small part of :class:`hantoo_api.HantooClient` needed here."""

    paper: bool

    def order(self, **body: Any) -> dict[str, Any]: ...


_ORDER_TR_IDS = {
    False: {
        "buy": {"NASD": "TTTT1002U", "NYSE": "TTTT1002U", "AMEX": "TTTT1002U", "TKSE": "TTTS0308U", "SHAA": "TTTS0202U", "SZAA": "TTTS0305U", "SEHK": "TTTS1002U", "HASE": "TTTS0311U", "VNSE": "TTTS0311U"},
        "sell": {"NASD": "TTTT1006U", "NYSE": "TTTT1006U", "AMEX": "TTTT1006U", "TKSE": "TTTS0307U", "SHAA": "TTTS1005U", "SZAA": "TTTS0304U", "SEHK": "TTTS1001U", "HASE": "TTTS0310U", "VNSE": "TTTS0310U"},
    },
    True: {
        "buy": {"NASD": "VTTT1002U", "NYSE": "VTTT1002U", "AMEX": "VTTT1002U", "TKSE": "VTTS0308U", "SHAA": "VTTS0202U", "SZAA": "VTTS0305U", "SEHK": "VTTS1002U", "HASE": "VTTS0311U", "VNSE": "VTTS0311U"},
        "sell": {"NASD": "VTTT1001U", "NYSE": "VTTT1001U", "AMEX": "VTTT1001U", "TKSE": "VTTS0307U", "SHAA": "VTTS1005U", "SZAA": "VTTS0304U", "SEHK": "VTTS1001U", "HASE": "VTTS0310U", "VNSE": "VTTS0310U"},
    },
}


def evaluate_trade_actions(
    selected: list[dict[str, Any]],
    prices: dict[str, float],
    holdings: dict[str, int | float],
    state: dict[str, Any],
    *,
    max_positions: int = 50,
) -> tuple[list[TradeAction], dict[str, Any]]:
    """Create idempotent buy/sell actions for the selected universe.

    Each selected item requires ``ticker`` and ``target_qty``. Optional fields
    are ``entry_price``, ``entry_direction`` (``at_or_below`` by default),
    ``stop_price``, and ``exchange``. Existing positions absent from the new
    selection are sold during a rebalance. The returned state must be saved
    until account holdings reflect the submitted orders.
    """
    if not 1 <= max_positions <= 50:
        raise ValueError("max_positions must be between 1 and 50")

    normalized_holdings = {
        ticker.upper(): int(quantity)
        for ticker, quantity in holdings.items()
        if int(quantity) > 0
    }
    selected_by_ticker: dict[str, dict[str, Any]] = {}
    for item in selected:
        ticker = str(item["ticker"]).upper()
        if ticker in selected_by_ticker:
            raise ValueError(f"duplicate selected ticker: {ticker}")
        if len(selected_by_ticker) == max_positions:
            break
        target_qty = int(item["target_qty"])
        if target_qty < 1:
            raise ValueError(f"target_qty must be positive: {ticker}")
        selected_by_ticker[ticker] = {**item, "ticker": ticker, "target_qty": target_qty}

    next_state = dict(state)
    actions: list[TradeAction] = []
    active_keys: set[str] = set()

    def add_action(side: Side, ticker: str, quantity: int, price: float, reason: str, exchange: str = "NASD") -> None:
        key = f"{ticker}:{side}:{reason}"
        active_keys.add(key)
        if quantity > 0 and price > 0 and not next_state.get(key):
            actions.append(TradeAction(side, ticker, quantity, price, reason, exchange.upper()))
            next_state[key] = True

    # Stop loss always takes priority over a rebalance increase or hold.
    stopped: set[str] = set()
    for ticker, item in selected_by_ticker.items():
        price = float(prices.get(ticker, 0))
        stop_price = float(item.get("stop_price", 0))
        quantity = normalized_holdings.get(ticker, 0)
        if quantity and stop_price > 0 and 0 < price <= stop_price:
            add_action("sell", ticker, quantity, price, "stop_loss", str(item.get("exchange", "NASD")))
            stopped.add(ticker)

    # Stocks that have dropped out of the top-50 universe are sold.
    for ticker, quantity in normalized_holdings.items():
        if ticker not in selected_by_ticker:
            price = float(prices.get(ticker, 0))
            add_action("sell", ticker, quantity, price, "rebalance_exit")

    for ticker, item in selected_by_ticker.items():
        if ticker in stopped:
            continue
        price = float(prices.get(ticker, 0))
        if price <= 0:
            continue
        target_qty = item["target_qty"]
        current_qty = normalized_holdings.get(ticker, 0)
        exchange = str(item.get("exchange", "NASD"))
        if current_qty > target_qty:
            add_action("sell", ticker, current_qty - target_qty, price, "rebalance_reduce", exchange)
            continue
        if current_qty >= target_qty:
            continue
        entry_price = float(item.get("entry_price", 0))
        direction = item.get("entry_direction", "at_or_below")
        entry_allowed = entry_price <= 0 or (price <= entry_price if direction == "at_or_below" else price >= entry_price)
        if entry_allowed:
            reason = "entry" if current_qty == 0 else "rebalance_increase"
            add_action("buy", ticker, target_qty - current_qty, price, reason, exchange)

    # Clear stale idempotency flags once the triggering condition no longer exists.
    for key in list(next_state):
        if key.count(":") == 2 and key not in active_keys:
            next_state.pop(key)
    return actions, next_state


def execute_trade_actions(
    actions: list[TradeAction],
    client: OrderClient,
    *,
    account_no: str | None = None,
    account_product_code: str | None = None,
    dry_run: bool = True,
    confirm_live: bool = False,
    dotenv_path: str = ".env",
) -> list[dict[str, Any]]:
    """Submit limit orders through Hantoo, or return their payloads in dry-run.

    Live orders require both ``dry_run=False`` and ``confirm_live=True``.
    This deliberately prevents an alert/rebalance loop from sending a live
    order merely because credentials were present.
    """
    load_dotenv(dotenv_path)
    account_no = account_no or os.getenv("HANTOO_ACCOUNT_NO", "").strip()
    account_product_code = account_product_code or os.getenv("HANTOO_ACCOUNT_PRODUCT_CODE", "01").strip()
    if len(account_no) != 8 or not account_no.isdigit():
        raise ValueError("account_no must be the first eight digits of the account")
    if len(account_product_code) != 2 or not account_product_code.isdigit():
        raise ValueError("account_product_code must contain two digits")
    paper = bool(getattr(client, "paper", False))
    if not dry_run and not paper and not confirm_live:
        raise ValueError("live order submission requires confirm_live=True")

    results: list[dict[str, Any]] = []
    for action in actions:
        try:
            tr_id = _ORDER_TR_IDS[paper][action.side][action.exchange]
        except KeyError as error:
            raise ValueError(f"unsupported exchange for order: {action.exchange}") from error
        body = {
            "tr_id": tr_id,
            "CANO": account_no,
            "ACNT_PRDT_CD": account_product_code,
            "OVRS_EXCG_CD": action.exchange,
            "PDNO": action.ticker,
            "ORD_QTY": str(action.quantity),
            "OVRS_ORD_UNPR": str(action.limit_price),
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": "00",  # limit order; no implicit market orders
        }
        if action.side == "sell":
            body["SLL_TYPE"] = "00"
        if dry_run:
            results.append({"status": "dry_run", "action": asdict(action), "order": body})
        else:
            results.append({"status": "submitted", "action": asdict(action), "response": client.order(**body)})
    return results


def evaluate_price_alerts(
    watchlist: list[dict[str, Any]], prices: dict[str, float], state: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Backward-compatible adapter returning buy actions for a legacy watchlist.

    New code should call :func:`evaluate_trade_actions` with actual holdings so
    sell and rebalance actions can be calculated correctly.
    """
    selected = [{**item, "target_qty": item.get("target_qty", item.get("quantity", 1))} for item in watchlist]
    actions, next_state = evaluate_trade_actions(selected, prices, {}, state)
    return [asdict(action) for action in actions], next_state
