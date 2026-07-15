"""Validated content model for Nasdaq issue YouTube Shorts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EXPECTED_SCENE_KINDS = (
    "hook",
    "proof",
    "context",
    "causal",
    "twist",
    "groups",
    "heatmap",
    "invalidation",
    "loop",
)
SCENE_DURATIONS = (1.5, 2.5, 6.0, 8.0, 9.0, 10.0, 12.0, 6.0, 5.0)
MAPPING_GROUPS = ("positive", "watch", "risk")


def _read_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def load_universe(path: str | Path) -> list[str]:
    data = _read_json(path)
    tickers = data.get("tickers")
    if not isinstance(tickers, list) or not all(isinstance(item, str) for item in tickers):
        raise ValueError("universe tickers must be a list of strings")
    normalized = [item.strip().upper() for item in tickers]
    if len(normalized) != 50 or len(set(normalized)) != 50:
        raise ValueError("universe must contain exactly 50 unique tickers")
    return normalized


def load_issue_bundle(path: str | Path) -> dict[str, Any]:
    return _read_json(path)


def timeline(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(scenes) != len(EXPECTED_SCENE_KINDS):
        raise ValueError("each issue must contain exactly nine scenes")
    result: list[dict[str, Any]] = []
    cursor = 0.0
    for expected, duration, scene in zip(EXPECTED_SCENE_KINDS, SCENE_DURATIONS, scenes):
        if scene.get("kind") != expected:
            raise ValueError(f"expected scene kind {expected}")
        if not all(str(scene.get(key, "")).strip() for key in ("headline", "body", "narration")):
            raise ValueError(f"scene {expected} requires headline, body and narration")
        item = dict(scene)
        item["start"] = cursor
        cursor += duration
        item["end"] = cursor
        item["duration"] = duration
        result.append(item)
    if cursor != 60.0:
        raise ValueError("timeline must total exactly 60 seconds")
    return result


def _mapped_tickers(issue: dict[str, Any]) -> dict[str, list[str]]:
    mapping = issue.get("mapping")
    if not isinstance(mapping, dict):
        raise ValueError("issue mapping must be an object")
    groups: dict[str, list[str]] = {}
    for name in MAPPING_GROUPS:
        values = mapping.get(name, [])
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ValueError(f"mapping group {name} must be a list")
        groups[name] = [item.strip().upper() for item in values]
    return groups


def mapping_counts(issue: dict[str, Any], universe: list[str]) -> dict[str, int]:
    groups = _mapped_tickers(issue)
    mapped = {ticker for values in groups.values() for ticker in values}
    return {
        "positive": len(groups["positive"]),
        "watch": len(groups["watch"]),
        "risk": len(groups["risk"]),
        "neutral": len(universe) - len(mapped),
    }


def validate_bundle(bundle: dict[str, Any], universe: list[str]) -> None:
    if not str(bundle.get("issue_date", "")).strip():
        raise ValueError("issue_date is required")
    issues = bundle.get("issues")
    if not isinstance(issues, list) or not issues:
        raise ValueError("at least one issue is required")
    universe_set = set(universe)
    slugs: set[str] = set()
    for issue in issues:
        if not isinstance(issue, dict):
            raise ValueError("each issue must be an object")
        slug = str(issue.get("slug", "")).strip()
        if not slug or slug in slugs:
            raise ValueError("issue slugs must be unique")
        slugs.add(slug)
        timeline(issue.get("scenes", []))
        groups = _mapped_tickers(issue)
        seen: set[str] = set()
        for values in groups.values():
            for ticker in values:
                if ticker not in universe_set:
                    raise ValueError(f"unknown ticker: {ticker}")
                if ticker in seen:
                    raise ValueError(f"ticker appears in multiple mapping groups: {ticker}")
                seen.add(ticker)
        sources = issue.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"issue {slug} requires at least one source")
        for source in sources:
            if not all(str(source.get(key, "")).strip() for key in ("publisher", "published", "url")):
                raise ValueError(f"issue {slug} has incomplete source metadata")
