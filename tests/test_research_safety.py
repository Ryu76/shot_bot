import math

import pandas as pd
import pytest

from shot_bot.backtest import DailyBar, evaluate_exit
from shot_bot.labels import forward_direction_label
from shot_bot.risk import risk_based_shares
from shot_bot.splits import purged_train_validation_split


def test_forward_label_keeps_unobserved_future_as_nan():
    close = pd.Series([100.0, 105.0, 101.0, 110.0])

    label = forward_direction_label(close, horizon=2)

    assert label.iloc[0] == 1.0
    assert label.iloc[1] == 1.0
    assert math.isnan(label.iloc[2])
    assert math.isnan(label.iloc[3])


def test_purged_split_excludes_labels_crossing_validation_and_test_boundaries():
    dates = pd.bdate_range("2025-01-01", periods=30)

    train, validation = purged_train_validation_split(
        dates,
        validation_start=dates[15],
        test_start=dates[24],
        horizon_days=3,
    )

    assert train.max() < dates[12]
    assert validation.min() == dates[15]
    assert validation.max() < dates[21]


def test_purged_split_uses_observed_sessions_not_calendar_business_days():
    dates = pd.DatetimeIndex(
        ["2025-01-16", "2025-01-17", "2025-01-21", "2025-01-23", "2025-01-24", "2025-01-27"]
    )  # 2025-01-22 is omitted from the observed data

    train, validation = purged_train_validation_split(
        dates,
        validation_start=pd.Timestamp("2025-01-23"),
        test_start=pd.Timestamp("2025-01-27"),
        horizon_days=1,
    )

    assert train.tolist() == [pd.Timestamp("2025-01-16"), pd.Timestamp("2025-01-17")]
    assert validation.tolist() == [pd.Timestamp("2025-01-23")]


def test_gap_down_stop_uses_open_price_not_unreachable_stop_price():
    result = evaluate_exit(
        DailyBar(open=90.0, high=95.0, low=88.0, close=92.0),
        stop_price=94.0,
        take_profit=110.0,
        trailing_stop=None,
    )

    assert result.reason == "stop"
    assert result.price == 90.0


def test_opening_gap_above_target_exits_at_the_open_before_intrabar_events():
    result = evaluate_exit(
        DailyBar(open=115.0, high=116.0, low=93.0, close=96.0),
        stop_price=94.0,
        take_profit=110.0,
        trailing_stop=None,
    )

    assert result.reason == "take_profit"
    assert result.price == 115.0


def test_stop_has_priority_when_daily_bar_hits_stop_and_target():
    result = evaluate_exit(
        DailyBar(open=100.0, high=115.0, low=93.0, close=108.0),
        stop_price=94.0,
        take_profit=110.0,
        trailing_stop=None,
    )

    assert result.reason == "stop"
    assert result.price == 94.0


def test_new_trailing_stop_is_not_used_on_the_same_daily_bar():
    result = evaluate_exit(
        DailyBar(open=100.0, high=120.0, low=110.0, close=118.0),
        stop_price=94.0,
        take_profit=110.0,
        trailing_stop=None,
    )

    assert result.reason == "take_profit"
    assert result.price == 110.0


def test_risk_position_size_caps_both_risk_and_notional_exposure():
    shares = risk_based_shares(
        equity=100_000.0,
        entry_price=100.0,
        atr=4.0,
        stop_atr_multiple=2.0,
        risk_fraction=0.01,
        max_position_fraction=0.20,
    )

    assert shares == pytest.approx(125.0)
