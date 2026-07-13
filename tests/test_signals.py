import pandas as pd

from shot_bot.signals import cross_sectional_return_target, select_top_k


def test_cross_sectional_target_is_excess_return_rank_per_date():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02"] * 3),
            "ticker": ["A", "B", "C"],
            "forward_return": [0.10, 0.05, -0.02],
        }
    )

    target = cross_sectional_return_target(frame)

    assert target.tolist() == [1.0, 0.5, 0.0]


def test_cross_sectional_target_keeps_unobserved_forward_return_as_nan():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-02"]),
            "ticker": ["A", "B"],
            "forward_return": [0.10, float("nan")],
        }
    )

    target = cross_sectional_return_target(frame)

    assert target.iloc[0] == 0.5
    assert pd.isna(target.iloc[1])


def test_select_top_k_requires_liquidity_and_returns_only_highest_scores():
    frame = pd.DataFrame(
        {
            "ticker": ["A", "B", "C"],
            "score": [0.80, 0.95, 0.90],
            "dollar_volume_20d": [2_000_000, 500_000, 3_000_000],
            "rsi_14": [55.0, 55.0, 72.0],
        }
    )

    chosen = select_top_k(
        frame,
        top_k=2,
        min_dollar_volume=1_000_000,
        rsi_max=65.0,
    )

    assert chosen["ticker"].tolist() == ["A"]
