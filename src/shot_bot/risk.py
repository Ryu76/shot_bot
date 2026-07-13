"""Conservative, risk-budgeted position sizing."""


def risk_based_shares(
    *,
    equity: float,
    entry_price: float,
    atr: float,
    stop_atr_multiple: float,
    risk_fraction: float,
    max_position_fraction: float,
) -> float:
    """Size a position by the smaller of loss-budget and notional caps."""
    values = (equity, entry_price, atr, stop_atr_multiple, risk_fraction, max_position_fraction)
    if any(value <= 0 for value in values):
        raise ValueError("all sizing inputs must be positive")
    per_share_risk = atr * stop_atr_multiple
    by_risk = (equity * risk_fraction) / per_share_risk
    by_notional = (equity * max_position_fraction) / entry_price
    return min(by_risk, by_notional)
