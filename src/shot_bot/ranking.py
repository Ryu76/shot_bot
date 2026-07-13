"""Date-grouped LightGBM ranking helpers for research-only experiments."""

from __future__ import annotations

import pandas as pd


def group_sizes_by_date(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[int]]:
    """Sort rows by date and return LightGBM group sizes for each date."""
    if "date" not in frame.columns:
        raise ValueError("frame requires a date column")
    ordered = frame.sort_values("date", kind="stable").reset_index(drop=True)
    groups = ordered.groupby("date", sort=False).size().tolist()
    if not groups:
        raise ValueError("frame is empty")
    return ordered, groups


def fit_ranker_predict(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    feature_columns: list[str],
    n_estimators: int = 200,
) -> pd.DataFrame:
    """Fit a LightGBM LambdaRank model and append scores to a test frame."""
    from lightgbm import LGBMRanker

    if not feature_columns:
        raise ValueError("at least one feature column is required")
    required_train = {"date", "target_rank", *feature_columns}
    required_test = {"date", *feature_columns}
    if missing := required_train.difference(train.columns):
        raise ValueError(f"train missing columns: {sorted(missing)}")
    if missing := required_test.difference(test.columns):
        raise ValueError(f"test missing columns: {sorted(missing)}")
    train_ordered, groups = group_sizes_by_date(train.dropna(subset=["target_rank", *feature_columns]))
    if len(groups) < 2 or any(group < 2 for group in groups):
        raise ValueError("ranking training needs at least two dates with two or more assets each")
    model = LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        learning_rate=0.05,
        num_leaves=15,
        min_child_samples=10,
        n_estimators=n_estimators,
        random_state=42,
        verbosity=-1,
    )
    relevance = (
        train_ordered.groupby("date")["target_rank"].rank(method="dense").astype(int) - 1
    )
    model.fit(train_ordered[feature_columns], relevance, group=groups)
    scored = test.copy()
    scored["score"] = model.predict(scored[feature_columns])
    return scored
