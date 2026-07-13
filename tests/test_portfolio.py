import pandas as pd
import pytest

from shot_bot.portfolio import backtest_equal_weight_top_k


def test_stop_loss_uses_daily_low_and_gap_aware_fill():
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"]),
            "ticker": ["AAA"] * 3,
            "open": [100.0, 100.0, 105.0],
            "high": [101.0, 102.0, 106.0],
            "low": [99.0, 94.0, 104.0],
        }
    )
    scores = pd.DataFrame({"date": pd.to_datetime(["2025-01-02", "2025-01-03"]), "ticker": ["AAA", "AAA"], "score": [1.0, 1.0]})
    result = backtest_equal_weight_top_k(scores, prices, initial_capital=1_000, top_k=1, transaction_cost_bps=0, stop_loss_pct=0.05)
    assert result.metrics["total_return_pct"] == pytest.approx(-5.0)
    assert result.rebalances.iloc[0]["stop_exits"] == 1

    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"] * 2),
            "ticker": ["AAA"] * 3 + ["BBB"] * 3,
            "open": [100.0, 100.0, 110.0, 100.0, 100.0, 90.0],
        }
    )
    scores = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-02", "2025-01-03", "2025-01-03"]),
            "ticker": ["AAA", "BBB", "AAA", "BBB"],
            "score": [0.9, 0.1, 0.8, 0.2],
        }
    )

    result = backtest_equal_weight_top_k(
        scores, prices, initial_capital=1_000.0, top_k=1, transaction_cost_bps=10
    )

    assert result.equity.iloc[0] == 1_000.0
    assert result.equity.iloc[-1] < 1_100.0  # gross +10% is reduced by entry/exit costs
    assert result.metrics["rebalance_count"] == 1
    assert result.metrics["total_return_pct"] > 0
    assert result.rebalances.iloc[0]["tickers"] == "AAA"
