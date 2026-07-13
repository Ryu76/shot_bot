import pandas as pd

from shot_bot.research import build_feature_frame, expanding_walk_forward_scores


def _prices():
    dates = pd.bdate_range("2025-01-01", periods=55)
    rows = []
    for ticker, scale in [("AAA", 1.0), ("BBB", 1.1), ("CCC", 0.9)]:
        for i, date in enumerate(dates):
            close = scale * (100 + i + (2 if ticker == "AAA" else 0))
            rows.append({"date": date, "ticker": ticker, "open": close - 0.5, "high": close + 1, "low": close - 1, "close": close, "volume": 2_000_000})
    return pd.DataFrame(rows)


def test_feature_frame_keeps_last_forward_returns_missing():
    features = build_feature_frame(_prices(), horizon_days=3)

    last_rows = features.groupby("ticker", group_keys=False).tail(3)
    assert last_rows["forward_return"].isna().all()
    assert {"rsi_14", "atr_pct", "dollar_volume_20d", "target_rank"}.issubset(features.columns)


def test_expanding_walk_forward_only_scores_after_training_window():
    features = build_feature_frame(_prices(), horizon_days=2).dropna()

    scored = expanding_walk_forward_scores(
        features,
        feature_columns=["ret_1d", "ma_ratio_5", "rsi_14", "atr_pct", "dollar_volume_20d"],
        min_train_dates=15,
        rebalance_every=5,
        horizon_days=2,
        n_estimators=5,
    )

    assert not scored.empty
    assert scored["score"].notna().all()
    assert scored["date"].min() > features["date"].unique()[15]
