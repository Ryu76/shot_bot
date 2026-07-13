"""Label construction that never invents a future observation."""

import numpy as np
import pandas as pd


def forward_direction_label(close: pd.Series, horizon: int) -> pd.Series:
    """Return 1/0 only where the forward close is actually observed.

    The final ``horizon`` rows remain NaN and must be excluded from fitting.
    """
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    future_close = close.shift(-horizon)
    label = pd.Series(np.nan, index=close.index, dtype=float)
    observed = future_close.notna() & close.notna()
    label.loc[observed] = (future_close.loc[observed] > close.loc[observed]).astype(float)
    return label
