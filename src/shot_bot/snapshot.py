"""Immutable-on-write CSV snapshots with verifiable metadata."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def save_snapshot(frame: pd.DataFrame, directory: str | Path, *, name: str) -> tuple[Path, Path]:
    """Write a CSV snapshot and JSON metadata including a SHA-256 digest."""
    if frame.empty:
        raise ValueError("cannot snapshot an empty frame")
    output_dir = Path(directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / f"{name}.csv"
    metadata_path = output_dir / f"{name}.metadata.json"
    if data_path.exists() or metadata_path.exists():
        raise FileExistsError(f"snapshot already exists: {data_path}")
    frame.to_csv(data_path, index=False, lineterminator="\n")
    digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
    metadata = {
        "name": name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": len(frame),
        "columns": list(frame.columns),
        "sha256": digest,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return data_path, metadata_path


def load_snapshot(data_path: str | Path) -> pd.DataFrame:
    """Load a saved CSV snapshot without reaching an external data provider."""
    return pd.read_csv(data_path)
