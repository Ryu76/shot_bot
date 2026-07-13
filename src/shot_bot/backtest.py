"""Daily-bar exit rules with conservative ordering assumptions.

Daily OHLC data cannot establish the intraday high/low sequence. This module
therefore gives protective stops priority and only activates a new trailing
stop on the following bar.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DailyBar:
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class ExitDecision:
    reason: str | None
    price: float | None


def _gap_aware_stop_fill(open_price: float, stop_price: float) -> float:
    return min(open_price, stop_price)


def evaluate_exit(
    bar: DailyBar,
    *,
    stop_price: float,
    take_profit: float,
    trailing_stop: float | None,
) -> ExitDecision:
    """Evaluate a long position using only information known for this bar.

    Existing protective stops take precedence over profit targets. A target hit
    does not cause a newly calculated trailing stop to trigger on the same bar.
    """
    if min(bar.open, bar.high, bar.low, bar.close, stop_price, take_profit) <= 0:
        raise ValueError("prices must be positive")
    active_stop = max(stop_price, trailing_stop) if trailing_stop is not None else stop_price
    if bar.open <= active_stop:
        return ExitDecision("stop", _gap_aware_stop_fill(bar.open, active_stop))
    if bar.open >= take_profit:
        return ExitDecision("take_profit", bar.open)
    if bar.low <= active_stop:
        return ExitDecision("stop", _gap_aware_stop_fill(bar.open, active_stop))
    if bar.high >= take_profit:
        return ExitDecision("take_profit", take_profit)
    return ExitDecision(None, None)
