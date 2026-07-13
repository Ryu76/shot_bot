"""Cost-aware, research-only equal-weight portfolio backtest."""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

@dataclass(frozen=True)
class PortfolioResult:
    equity: pd.Series
    metrics: dict[str, float]

def backtest_equal_weight_top_k(scores: pd.DataFrame, prices: pd.DataFrame, *, initial_capital: float, top_k: int, transaction_cost_bps: float) -> PortfolioResult:
    required_scores = {"date", "ticker", "score"}
    required_prices = {"date", "ticker", "open"}
    if initial_capital <= 0 or top_k < 1 or transaction_cost_bps < 0:
        raise ValueError("invalid portfolio parameters")
    if required_scores - set(scores) or required_prices - set(prices):
        raise ValueError("missing required score or price columns")
    scores, prices = scores.copy(), prices.copy()
    scores["date"], prices["date"] = pd.to_datetime(scores["date"]), pd.to_datetime(prices["date"])
    price_dates = pd.DatetimeIndex(sorted(prices["date"].unique()))
    signal_dates = pd.DatetimeIndex(sorted(scores["date"].unique()))
    equity = initial_capital
    curve = [(signal_dates[0], equity)]
    cost = transaction_cost_bps / 10_000
    rebalances = 0
    for signal_date, next_signal in zip(signal_dates[:-1], signal_dates[1:]):
        entries = price_dates[price_dates > signal_date]
        exits = price_dates[price_dates > next_signal]
        if not len(entries) or not len(exits):
            continue
        entry_date, exit_date = entries[0], exits[0]
        picks = scores[scores.date.eq(signal_date)].nlargest(top_k, "score").ticker.tolist()
        entry = prices[(prices.date.eq(entry_date)) & prices.ticker.isin(picks)].set_index("ticker").open
        exit_ = prices[(prices.date.eq(exit_date)) & prices.ticker.isin(picks)].set_index("ticker").open
        common = entry.index.intersection(exit_.index)
        if common.empty:
            continue
        gross = (exit_.loc[common] / entry.loc[common]).mean()
        equity *= (1 - cost) * gross * (1 - cost)
        curve.append((exit_date, equity))
        rebalances += 1
    series = pd.Series(dict(curve)).sort_index()
    mdd = ((series / series.cummax()) - 1).min() * 100
    metrics = {"total_return_pct": (series.iloc[-1] / initial_capital - 1) * 100, "max_drawdown_pct": float(mdd), "rebalance_count": rebalances}
    return PortfolioResult(series, metrics)
