"""Feature construction and expanding walk-forward ranking for research only."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .ranking import fit_ranker_predict
from .signals import cross_sectional_return_target


def _ticker_features(ticker_prices: pd.DataFrame, horizon_days: int) -> pd.DataFrame:
    data = ticker_prices.sort_values("date").copy()
    close = data["close"].astype(float)
    high = data["high"].astype(float)
    low = data["low"].astype(float)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    relative_strength = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + relative_strength))
    rsi = rsi.mask(loss.eq(0) & gain.gt(0), 100.0)
    rsi = rsi.mask(loss.eq(0) & gain.eq(0), 50.0)
    data["ret_1d"] = close.pct_change(1)
    data["ma_ratio_5"] = close / close.rolling(5, min_periods=5).mean() - 1
    data["rsi_14"] = rsi
    data["atr_pct"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / close
    data["dollar_volume_20d"] = (close * data["volume"].astype(float)).rolling(20, min_periods=20).mean()
    data["forward_return"] = close.shift(-horizon_days) / close - 1
    return data


def build_feature_frame(prices: pd.DataFrame, *, horizon_days: int) -> pd.DataFrame:
    """Build causal features and an observed-only cross-sectional rank target."""
    required = {"date", "ticker", "open", "high", "low", "close", "volume"}
    if horizon_days < 1:
        raise ValueError("horizon_days must be at least 1")
    if missing := required.difference(prices.columns):
        raise ValueError(f"prices missing columns: {sorted(missing)}")
    prepared = prices.copy()
    prepared["date"] = pd.to_datetime(prepared["date"])
    pieces = [_ticker_features(group, horizon_days) for _, group in prepared.groupby("ticker", sort=False)]
    features = pd.concat(pieces, ignore_index=True)
    features["target_rank"] = cross_sectional_return_target(features)
    return features.sort_values(["date", "ticker"], kind="stable").reset_index(drop=True)


def expanding_walk_forward_scores(
    features: pd.DataFrame,
    *,
    feature_columns: list[str],
    min_train_dates: int,
    rebalance_every: int,
    horizon_days: int,
    n_estimators: int = 200,
) -> pd.DataFrame:
    """Train only on past, fully observed labels and score periodic future dates."""
    if min_train_dates < 2 or rebalance_every < 1 or horizon_days < 1:
        raise ValueError("min_train_dates must be >= 2; rebalance_every and horizon_days must be >= 1")
    required = {"date", "ticker", "target_rank", *feature_columns}
    if missing := required.difference(features.columns):
        raise ValueError(f"features missing columns: {sorted(missing)}")
    data = features.dropna(subset=["target_rank", *feature_columns]).copy()
    dates = pd.DatetimeIndex(sorted(data["date"].unique()))
    # The horizon already removed unobserved targets; reserve it again to avoid
    # allowing a training label to end on the scored date.
    horizon_embargo = horizon_days
    scored_parts = []
    first_score_idx = min_train_dates + horizon_embargo
    for idx in range(first_score_idx, len(dates), rebalance_every):
        train_end = idx - horizon_embargo
        train_dates = dates[:train_end]
        train = data[data["date"].isin(train_dates)]
        test = data[data["date"] == dates[idx]]
        if test.empty:
            continue
        scored_parts.append(
            fit_ranker_predict(train, test, feature_columns=feature_columns, n_estimators=n_estimators)
        )
    if not scored_parts:
        return pd.DataFrame(columns=[*features.columns, "score"])
    return pd.concat(scored_parts, ignore_index=True)
