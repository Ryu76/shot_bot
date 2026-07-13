import json

import pandas as pd

from shot_bot.ranking import fit_ranker_predict, group_sizes_by_date
from shot_bot.snapshot import load_snapshot, save_snapshot


def test_snapshot_round_trip_writes_metadata_and_content_hash(tmp_path):
    frame = pd.DataFrame(
        {"date": ["2025-01-02", "2025-01-03"], "ticker": ["AAA", "AAA"], "close": [100.0, 101.0]}
    )

    data_path, metadata_path = save_snapshot(frame, tmp_path, name="prices")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    loaded = load_snapshot(data_path)
    assert metadata["rows"] == 2
    assert len(metadata["sha256"]) == 64
    assert loaded["close"].tolist() == [100.0, 101.0]


def test_group_sizes_follow_sorted_date_groups():
    frame = pd.DataFrame(
        {"date": pd.to_datetime(["2025-01-03", "2025-01-02", "2025-01-02"]), "x": [1, 2, 3]}
    )

    ordered, groups = group_sizes_by_date(frame)

    assert ordered["date"].tolist() == [pd.Timestamp("2025-01-02")] * 2 + [pd.Timestamp("2025-01-03")]
    assert groups == [2, 1]


def test_ranker_predicts_score_for_each_test_row():
    train = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02"] * 3 + ["2025-01-03"] * 3),
            "ticker": list("ABC") * 2,
            "feature": [3.0, 2.0, 1.0, 3.1, 2.1, 1.1],
            "target_rank": [1.0, 0.5, 0.0, 1.0, 0.5, 0.0],
        }
    )
    test = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-06"] * 3),
            "ticker": list("ABC"),
            "feature": [3.2, 2.2, 1.2],
        }
    )

    scored = fit_ranker_predict(train, test, feature_columns=["feature"], n_estimators=10)

    assert len(scored) == 3
    assert scored["score"].notna().all()
