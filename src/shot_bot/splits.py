"""Time-aware dataset splits for overlapping forward-return labels."""

import pandas as pd


def purged_train_validation_split(
    dates: pd.DatetimeIndex,
    *,
    validation_start: pd.Timestamp,
    test_start: pd.Timestamp,
    horizon_days: int,
) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Split dates while removing labels whose horizon crosses a boundary.

    A row dated t has a label that depends on t + horizon_days. Therefore rows
    in the embargo window immediately before validation/test are not usable.
    """
    if horizon_days < 1:
        raise ValueError("horizon_days must be at least 1")
    dates = pd.DatetimeIndex(pd.to_datetime(dates)).sort_values().unique()
    validation_start = pd.Timestamp(validation_start)
    test_start = pd.Timestamp(test_start)
    validation_idx = dates.get_indexer([validation_start])[0]
    test_idx = dates.get_indexer([test_start])[0]
    if validation_idx < 0 or test_idx < 0:
        raise ValueError("split boundaries must be observed trading dates")
    train_end = validation_idx - horizon_days
    validation_end = test_idx - horizon_days
    train = dates[:train_end]
    validation = dates[validation_idx:validation_end]
    if train.empty or validation.empty:
        raise ValueError("split leaves no train or validation observations")
    return train, validation
