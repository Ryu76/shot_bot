"""Generate portfolio, QQQ benchmark, monthly and rebalance reports from snapshots."""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
import yfinance as yf
from shot_bot.portfolio import backtest_equal_weight_top_k

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scores", required=True)
    p.add_argument("--prices", required=True)
    p.add_argument("--capital", type=float, default=500_000)
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--cost-bps", type=float, default=10)
    p.add_argument("--output-dir", default="reports")
    a = p.parse_args()
    scores, prices = pd.read_csv(a.scores), pd.read_csv(a.prices)
    result = backtest_equal_weight_top_k(scores, prices, initial_capital=a.capital, top_k=a.top_k, transaction_cost_bps=a.cost_bps)
    qqq = yf.download("QQQ", start=str(result.equity.index.min().date()), end=str((result.equity.index.max() + pd.Timedelta(days=3)).date()), auto_adjust=False, progress=False)
    if isinstance(qqq.columns, pd.MultiIndex): qqq.columns = qqq.columns.get_level_values(0)
    qqq.index = pd.to_datetime(qqq.index)
    qqq_open = qqq["Open"].reindex(result.equity.index, method="bfill")
    qqq_equity = a.capital * qqq_open / qqq_open.iloc[0]
    report = pd.DataFrame({"portfolio": result.equity, "qqq": qqq_equity})
    monthly = report.resample("ME").last().pct_change(fill_method=None).mul(100).dropna()
    monthly.columns = ["portfolio_return_pct", "qqq_return_pct"]
    out = Path(a.output_dir); out.mkdir(parents=True, exist_ok=True)
    report.to_csv(out / "equity_vs_qqq.csv")
    monthly.to_csv(out / "monthly_returns.csv")
    result.rebalances.to_csv(out / "rebalances.csv", index=False)
    print("PORTFOLIO", result.metrics)
    print("QQQ_TOTAL_RETURN_PCT", (qqq_equity.iloc[-1] / a.capital - 1) * 100)
    print("MONTHLY\n", monthly.to_string())
    print("REBALANCES\n", result.rebalances.to_string(index=False))
if __name__ == "__main__": main()
