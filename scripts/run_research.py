"""Research-only walk-forward ranking runner. It never sends broker orders."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import yfinance as yf
from shot_bot.research import build_feature_frame, expanding_walk_forward_scores
from shot_bot.signals import select_top_k
from shot_bot.snapshot import save_snapshot

FEATURES = ["ret_1d", "ma_ratio_5", "rsi_14", "atr_pct", "dollar_volume_20d"]

def download(tickers: list[str], period: str) -> pd.DataFrame:
    pieces = []
    for ticker in tickers:
        raw = yf.download(ticker, period=period, auto_adjust=False, progress=False)
        if raw.empty:
            print(f"skip {ticker}: no data")
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.rename(columns=str.lower).reset_index().rename(columns={"Date": "date", "Datetime": "date"})
        raw.columns = [str(c).lower() for c in raw.columns]
        needed = ["date", "open", "high", "low", "close", "volume"]
        if not set(needed).issubset(raw.columns):
            print(f"skip {ticker}: missing OHLCV")
            continue
        raw = raw[needed].dropna()
        raw["ticker"] = ticker
        pieces.append(raw)
    if not pieces:
        raise RuntimeError("no price data downloaded")
    return pd.concat(pieces, ignore_index=True)

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tickers", default="AAPL,MSFT,NVDA,AMZN,META,GOOGL")
    p.add_argument("--period", default="2y")
    p.add_argument("--horizon", type=int, default=5)
    p.add_argument("--min-train-dates", type=int, default=120)
    p.add_argument("--rebalance-every", type=int, default=10)
    p.add_argument("--snapshot-dir", default="data/snapshots")
    p.add_argument("--report-dir", default="reports")
    args = p.parse_args()
    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()]
    prices = download(tickers, args.period)
    snapshot_dir, report_dir = Path(args.snapshot_dir), Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    data_path, metadata_path = save_snapshot(prices, snapshot_dir, name=f"prices_{run_id}")
    features = build_feature_frame(prices, horizon_days=args.horizon)
    scored = expanding_walk_forward_scores(features, feature_columns=FEATURES, min_train_dates=args.min_train_dates, rebalance_every=args.rebalance_every, horizon_days=args.horizon)
    score_path, score_metadata = save_snapshot(scored, snapshot_dir, name=f"walkforward_scores_{run_id}")
    latest = scored[scored["date"] == scored["date"].max()] if not scored.empty else scored
    candidates = select_top_k(latest, top_k=3, min_dollar_volume=1_000_000, rsi_max=70) if not latest.empty else latest
    candidates.to_csv(report_dir / "latest_candidates.csv", index=False)
    print(f"prices={data_path} metadata={metadata_path}")
    print(f"scores={score_path} metadata={score_metadata}")
    print(candidates[["date", "ticker", "score", "rsi_14", "dollar_volume_20d"]].to_string(index=False))

if __name__ == "__main__":
    main()
