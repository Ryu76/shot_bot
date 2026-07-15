import json
from pathlib import Path

import pytest

from shot_bot.shorts import (
    EXPECTED_SCENE_KINDS,
    load_issue_bundle,
    load_universe,
    mapping_counts,
    timeline,
    validate_bundle,
)
from shot_bot.shorts_render import render_scene_card, write_srt


ROOT = Path(__file__).parents[1]
UNIVERSE = ROOT / "config" / "shorts_50_universe.json"
ISSUES = ROOT / "shorts" / "2026-07-15" / "issues.json"


def test_loads_exactly_fifty_unique_tickers():
    tickers = load_universe(UNIVERSE)
    assert len(tickers) == 50
    assert len(set(tickers)) == 50
    assert {"AAPL", "MU", "MRVL", "INTC", "NVDA"}.issubset(tickers)


def test_bundle_has_four_issues_and_only_known_tickers():
    universe = load_universe(UNIVERSE)
    bundle = load_issue_bundle(ISSUES)
    validate_bundle(bundle, universe)
    assert bundle["issue_date"] == "2026-07-15"
    assert len(bundle["issues"]) == 4
    assert bundle["current_rebalance_candidates"] == ["MU", "MRVL", "INTC"]


def test_each_issue_has_retention_timeline_of_exactly_sixty_seconds():
    bundle = load_issue_bundle(ISSUES)
    for issue in bundle["issues"]:
        segments = timeline(issue["scenes"])
        assert [item["kind"] for item in segments] == list(EXPECTED_SCENE_KINDS)
        assert segments[0]["start"] == 0
        assert segments[-1]["end"] == 60
        assert segments[4]["start"] == 18
        assert segments[6]["start"] == 37
        assert segments[-1]["start"] == 55


def test_mapping_counts_include_all_fifty_without_reading_them_aloud():
    universe = load_universe(UNIVERSE)
    bundle = load_issue_bundle(ISSUES)
    for issue in bundle["issues"]:
        counts = mapping_counts(issue, universe)
        assert sum(counts.values()) == 50
        assert counts["neutral"] >= 0
        heatmap = next(scene for scene in issue["scenes"] if scene["kind"] == "heatmap")
        assert len(heatmap["narration"]) < 170


def test_rejects_duplicate_or_unknown_mapping_ticker(tmp_path):
    universe = load_universe(UNIVERSE)
    bundle = load_issue_bundle(ISSUES)
    broken = json.loads(json.dumps(bundle))
    broken["issues"][0]["mapping"]["positive"].append("NOTREAL")
    path = tmp_path / "issues.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown ticker"):
        validate_bundle(load_issue_bundle(path), universe)

    broken = json.loads(json.dumps(bundle))
    duplicate = broken["issues"][0]["mapping"]["positive"][0]
    broken["issues"][0]["mapping"]["watch"].append(duplicate)
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError, match="multiple mapping groups"):
        validate_bundle(load_issue_bundle(path), universe)


def test_renders_vertical_scene_card_and_srt(tmp_path):
    universe = load_universe(UNIVERSE)
    bundle = load_issue_bundle(ISSUES)
    issue = bundle["issues"][1]
    segments = timeline(issue["scenes"])
    image = render_scene_card(
        issue=issue,
        segment=segments[6],
        universe=universe,
        issue_date=bundle["issue_date"],
        scene_number=7,
    )
    assert image.size == (1080, 1920)
    image_path = tmp_path / "heatmap.png"
    image.save(image_path)
    assert image_path.stat().st_size > 20_000

    srt_path = tmp_path / "captions.srt"
    write_srt(segments, srt_path)
    text = srt_path.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,500" in text
    assert "00:00:55,000 --> 00:01:00,000" in text
    assert issue["scenes"][0]["narration"] in text
