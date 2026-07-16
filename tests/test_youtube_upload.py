import json
from pathlib import Path
import subprocess
import sys

import pytest

from shot_bot.youtube_upload import (
    UploadConfig,
    build_upload_jobs,
    discover_latest_output,
    get_youtube_service,
    load_upload_config,
    load_upload_state,
    pending_jobs,
    save_upload_state,
    upload_job,
)


ROOT = Path(__file__).parents[1]
OUTPUT = ROOT / "shorts" / "2026-07-15"


def test_discovers_latest_completed_date_folder(tmp_path):
    (tmp_path / "2026-07-14").mkdir()
    latest = tmp_path / "2026-07-15"
    latest.mkdir()
    (latest / "manifest.json").write_text('{"videos": []}', encoding="utf-8")
    assert discover_latest_output(tmp_path) == latest


def test_builds_upload_jobs_from_manifest_and_sources():
    config = UploadConfig(
        client_secrets_file=Path("config/youtube_client_secret.json"),
        token_file=Path("config/youtube_token.json"),
        privacy_status="private",
        made_for_kids=False,
        category_id="25",
        default_tags=("나스닥", "미국주식"),
    )
    jobs = build_upload_jobs(OUTPUT, config)
    assert len(jobs) == 4
    assert all(job.video_path.exists() for job in jobs)
    assert all(job.caption_path.exists() for job in jobs)
    assert all(job.title.endswith("#Shorts") for job in jobs)
    assert all(len(job.title) <= 100 for job in jobs)
    assert all("투자 권유가 아닙니다" in job.description for job in jobs)
    assert all("https://" in job.description for job in jobs)
    assert jobs[0].privacy_status == "private"
    assert jobs[0].made_for_kids is False


def test_rejects_unsafe_or_incomplete_upload_config():
    with pytest.raises(ValueError, match="privacy_status"):
        UploadConfig(
            client_secrets_file=Path("client.json"), token_file=Path("token.json"),
            privacy_status="friends", made_for_kids=False,
        )
    with pytest.raises(ValueError, match="made_for_kids"):
        UploadConfig(
            client_secrets_file=Path("client.json"), token_file=Path("token.json"),
            privacy_status="private", made_for_kids=None,
        )


def test_upload_state_prevents_duplicate_video_uploads(tmp_path):
    config = UploadConfig(
        client_secrets_file=Path("client.json"), token_file=Path("token.json"),
        privacy_status="private", made_for_kids=False,
    )
    jobs = build_upload_jobs(OUTPUT, config)
    state_path = tmp_path / "youtube_upload_state.json"
    state = load_upload_state(state_path)
    assert len(pending_jobs(jobs, state)) == 4

    state[jobs[0].slug] = {"video_id": "abc123", "url": "https://youtu.be/abc123"}
    save_upload_state(state_path, state)
    restored = load_upload_state(state_path)
    remaining = pending_jobs(jobs, restored)
    assert len(remaining) == 3
    assert jobs[0].slug not in {job.slug for job in remaining}


def test_rejects_manifest_when_video_file_is_missing(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({
        "videos": [{"slug": "missing", "title": "없음", "video": "missing.mp4", "captions": "missing.srt"}]
    }), encoding="utf-8")
    (tmp_path / "issues.json").write_text(json.dumps({"issues": [{"slug": "missing", "sources": []}]}), encoding="utf-8")
    config = UploadConfig(
        client_secrets_file=Path("client.json"), token_file=Path("token.json"),
        privacy_status="private", made_for_kids=False,
    )
    with pytest.raises(FileNotFoundError, match="missing.mp4"):
        build_upload_jobs(tmp_path, config)


class FakeRequest:
    def __init__(self, response=None):
        self.response = response or {}

    def next_chunk(self):
        return None, self.response

    def execute(self):
        return self.response


class FakeResource:
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls

    def insert(self, **kwargs):
        self.calls.append((self.name, kwargs))
        if self.name == "videos":
            return FakeRequest({"id": "video123"})
        return FakeRequest({"ok": True})


class FakeYouTube:
    def __init__(self):
        self.calls = []

    def videos(self):
        return FakeResource("videos", self.calls)

    def captions(self):
        return FakeResource("captions", self.calls)

    def playlistItems(self):
        return FakeResource("playlistItems", self.calls)


def test_uploads_video_caption_and_playlist_with_safe_metadata():
    config = UploadConfig(
        client_secrets_file=Path("client.json"), token_file=Path("token.json"),
        privacy_status="private", made_for_kids=False, playlist_id="PL123",
    )
    job = build_upload_jobs(OUTPUT, config)[0]
    service = FakeYouTube()
    media_calls = []

    def media_factory(path, **kwargs):
        media_calls.append((path, kwargs))
        return {"path": path, **kwargs}

    result = upload_job(service, job, media_factory=media_factory, sleep=lambda _: None)

    assert result == {"video_id": "video123", "url": "https://youtu.be/video123"}
    video_call = next(call for name, call in service.calls if name == "videos")
    assert video_call["part"] == "snippet,status"
    assert video_call["body"]["status"] == {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": False,
    }
    assert video_call["notifySubscribers"] is False
    assert video_call["media_body"]["resumable"] is True
    caption_call = next(call for name, call in service.calls if name == "captions")
    assert caption_call["body"]["snippet"]["language"] == "ko"
    playlist_call = next(call for name, call in service.calls if name == "playlistItems")
    assert playlist_call["body"]["snippet"]["playlistId"] == "PL123"
    assert len(media_calls) == 2


def test_loads_user_editable_config_and_explains_missing_oauth_file(tmp_path):
    config_path = tmp_path / "youtube_upload.json"
    config_path.write_text(json.dumps({
        "client_secrets_file": str(tmp_path / "PUT_CLIENT_JSON_HERE.json"),
        "token_file": str(tmp_path / "youtube_token.json"),
        "privacy_status": "private",
        "made_for_kids": False,
        "category_id": "25",
        "default_tags": ["나스닥", "미국주식"],
        "playlist_id": "",
        "notify_subscribers": False,
        "upload_captions": True,
        "language": "ko"
    }), encoding="utf-8")
    config = load_upload_config(config_path)
    assert config.default_tags == ("나스닥", "미국주식")
    assert config.privacy_status == "private"
    with pytest.raises(FileNotFoundError, match="Google Cloud.*OAuth"):
        get_youtube_service(config)


def test_cli_dry_run_needs_no_oauth_credentials(tmp_path):
    config_path = tmp_path / "youtube_upload.json"
    config_path.write_text(json.dumps({
        "client_secrets_file": str(tmp_path / "missing_client.json"),
        "token_file": str(tmp_path / "token.json"),
        "privacy_status": "private",
        "made_for_kids": False,
        "category_id": "25",
        "default_tags": ["나스닥"],
        "playlist_id": "",
        "notify_subscribers": False,
        "upload_captions": True,
        "language": "ko"
    }), encoding="utf-8")
    completed = subprocess.run([
        sys.executable,
        str(ROOT / "scripts" / "upload_youtube_shorts.py"),
        "--config", str(config_path),
        "--shorts-root", str(ROOT / "shorts"),
        "--date", "2026-07-15",
        "--dry-run",
    ], capture_output=True, text=True, encoding="utf-8")
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.count('"slug"') == 4
    assert '"privacy_status": "private"' in completed.stdout
    assert "OAuth" not in completed.stderr
