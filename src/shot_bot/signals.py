"""Cross-sectional targets and deterministic signal eligibility filters."""

import pandas as pd


def cross_sectional_return_target(frame: pd.DataFrame) -> pd.Series:
    """Map each date's observed forward return to a 0..1 cross-sectional rank."""
    required = {"date", "forward_return"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    ranks = frame.groupby("date")["forward_return"].rank(method="average")
    counts = frame.groupby("date")["forward_return"].transform("count")
    denominator = (counts - 1).where(counts > 1)
    result = ((ranks - 1) / denominator)
    singleton_observed = counts.eq(1) & frame["forward_return"].notna()
    result.loc[singleton_observed] = 0.5
    return result.where(frame["forward_return"].notna())


def select_top_k(
    frame: pd.DataFrame,
    *,
    top_k: int,
    min_dollar_volume: float,
    rsi_max: float,
) -> pd.DataFrame:
    """Select liquid, non-overbought candidates by model score, not a raw probability."""
    if top_k < 1 or min_dollar_volume <= 0:
        raise ValueError("top_k and min_dollar_volume must be positive")
    required = {"ticker", "score", "dollar_volume_20d", "rsi_14"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    eligible = frame.loc[
        (frame["dollar_volume_20d"] >= min_dollar_volume)
        & (frame["rsi_14"] < rsi_max)
        & frame["score"].notna()
    ]
    return eligible.sort_values("score", ascending=False).head(top_k).copy()
