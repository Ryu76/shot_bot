"""YouTube upload planning and state management for rendered Shorts."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UploadConfig:
    client_secrets_file: Path
    token_file: Path
    privacy_status: str = "private"
    made_for_kids: bool | None = None
    category_id: str = "25"
    default_tags: tuple[str, ...] = ()
    playlist_id: str = ""
    notify_subscribers: bool = False
    upload_captions: bool = True
    language: str = "ko"

    def __post_init__(self) -> None:
        if self.privacy_status not in {"private", "unlisted", "public"}:
            raise ValueError("privacy_status must be private, unlisted or public")
        if not isinstance(self.made_for_kids, bool):
            raise ValueError("made_for_kids must be explicitly true or false")
        if not str(self.category_id).isdigit():
            raise ValueError("category_id must contain only digits")


@dataclass(frozen=True)
class UploadJob:
    slug: str
    title: str
    description: str
    tags: tuple[str, ...]
    video_path: Path
    caption_path: Path
    privacy_status: str
    made_for_kids: bool
    category_id: str
    playlist_id: str
    notify_subscribers: bool
    upload_captions: bool
    language: str


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def load_upload_config(path: str | Path) -> UploadConfig:
    data = _read_json(Path(path))
    return UploadConfig(
        client_secrets_file=Path(str(data.get("client_secrets_file", ""))),
        token_file=Path(str(data.get("token_file", ""))),
        privacy_status=str(data.get("privacy_status", "private")),
        made_for_kids=data.get("made_for_kids"),
        category_id=str(data.get("category_id", "25")),
        default_tags=tuple(str(item) for item in data.get("default_tags", [])),
        playlist_id=str(data.get("playlist_id", "")).strip(),
        notify_subscribers=bool(data.get("notify_subscribers", False)),
        upload_captions=bool(data.get("upload_captions", True)),
        language=str(data.get("language", "ko")),
    )


def get_youtube_service(config: UploadConfig) -> Any:
    if not config.client_secrets_file.is_file():
        raise FileNotFoundError(
            "Google Cloud에서 OAuth 2.0 데스크톱 앱 클라이언트 JSON을 내려받아 "
            f"다음 경로에 저장하세요: {config.client_secrets_file}"
        )
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    scopes = (
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
    )
    credentials = None
    if config.token_file.is_file():
        credentials = Credentials.from_authorized_user_file(str(config.token_file), scopes)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(config.client_secrets_file), scopes)
        credentials = flow.run_local_server(port=0, open_browser=True, prompt="consent")
    config.token_file.parent.mkdir(parents=True, exist_ok=True)
    config.token_file.write_text(credentials.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def discover_latest_output(shorts_root: str | Path) -> Path:
    root = Path(shorts_root)
    candidates = sorted(
        path for path in root.iterdir()
        if path.is_dir() and (path / "manifest.json").is_file()
    )
    if not candidates:
        raise FileNotFoundError(f"no completed Shorts output folder under {root}")
    return candidates[-1]


def _shorts_title(title: str) -> str:
    suffix = " #Shorts"
    cleaned = " ".join(str(title).split())
    if cleaned.lower().endswith("#shorts"):
        return cleaned[:100]
    return cleaned[: 100 - len(suffix)].rstrip() + suffix


def _description(issue: dict[str, Any]) -> str:
    lines = [
        str(issue.get("fact", "")).strip(),
        "",
        "기존 단타 봇 50종목을 긍정·관찰·위험·중립으로 매핑한 60초 설명입니다.",
        "뉴스만으로 매수·매도를 결정하지 않으며 기존 점수·거래대금·RSI·손절 조건과 함께 판단합니다.",
        "",
        "출처",
    ]
    for source in issue.get("sources", []):
        publisher = str(source.get("publisher", "출처")).strip()
        url = str(source.get("url", "")).strip()
        if url:
            lines.append(f"- {publisher}: {url}")
    lines.extend([
        "",
        "본 콘텐츠는 공개 자료를 바탕으로 한 일반 정보이며 투자 권유가 아닙니다.",
        "#나스닥 #미국주식 #주식이슈 #Shorts",
    ])
    return "\n".join(lines)[:5000]


def build_upload_jobs(output_dir: str | Path, config: UploadConfig) -> list[UploadJob]:
    folder = Path(output_dir)
    manifest = _read_json(folder / "manifest.json")
    bundle = _read_json(folder / "issues.json")
    issues = {str(item.get("slug")): item for item in bundle.get("issues", []) if isinstance(item, dict)}
    jobs: list[UploadJob] = []
    for item in manifest.get("videos", []):
        slug = str(item.get("slug", "")).strip()
        issue = issues.get(slug)
        if not slug or issue is None:
            raise ValueError(f"manifest issue metadata missing for slug: {slug}")
        video_path = folder / str(item.get("video", ""))
        caption_path = folder / str(item.get("captions", ""))
        if not video_path.is_file():
            raise FileNotFoundError(str(video_path))
        if config.upload_captions and not caption_path.is_file():
            raise FileNotFoundError(str(caption_path))
        issue_tags = tuple(
            ticker for group in issue.get("mapping", {}).values()
            for ticker in group[:5]
        )
        tags = tuple(dict.fromkeys((*config.default_tags, *issue_tags, "Shorts")))[:30]
        jobs.append(UploadJob(
            slug=slug,
            title=_shorts_title(str(item.get("title", slug))),
            description=_description(issue),
            tags=tags,
            video_path=video_path,
            caption_path=caption_path,
            privacy_status=config.privacy_status,
            made_for_kids=config.made_for_kids,
            category_id=config.category_id,
            playlist_id=config.playlist_id,
            notify_subscribers=config.notify_subscribers,
            upload_captions=config.upload_captions,
            language=config.language,
        ))
    return jobs


def load_upload_state(path: str | Path) -> dict[str, dict[str, Any]]:
    state_path = Path(path)
    if not state_path.exists():
        return {}
    data = _read_json(state_path)
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def save_upload_state(path: str | Path, state: dict[str, dict[str, Any]]) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(state_path)


def pending_jobs(jobs: list[UploadJob], state: dict[str, dict[str, Any]]) -> list[UploadJob]:
    return [job for job in jobs if not state.get(job.slug, {}).get("video_id")]


def _execute_with_retry(request: Any, *, resumable: bool, sleep: Any, max_retries: int = 5) -> dict[str, Any]:
    retries = 0
    while True:
        try:
            if resumable:
                response = None
                while response is None:
                    _, response = request.next_chunk()
                return response
            return request.execute()
        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status not in {500, 502, 503, 504} or retries >= max_retries:
                raise
            sleep(2 ** retries)
            retries += 1


def upload_job(
    service: Any,
    job: UploadJob,
    *,
    media_factory: Any | None = None,
    sleep: Any = time.sleep,
) -> dict[str, str]:
    if media_factory is None:
        from googleapiclient.http import MediaFileUpload
        media_factory = MediaFileUpload

    video_media = media_factory(
        str(job.video_path),
        mimetype="video/mp4",
        chunksize=8 * 1024 * 1024,
        resumable=True,
    )
    request = service.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": job.title,
                "description": job.description,
                "tags": list(job.tags),
                "categoryId": job.category_id,
                "defaultLanguage": job.language,
                "defaultAudioLanguage": job.language,
            },
            "status": {
                "privacyStatus": job.privacy_status,
                "selfDeclaredMadeForKids": job.made_for_kids,
            },
        },
        media_body=video_media,
        notifySubscribers=job.notify_subscribers,
    )
    response = _execute_with_retry(request, resumable=True, sleep=sleep)
    video_id = str(response.get("id", "")).strip()
    if not video_id:
        raise RuntimeError("YouTube upload response did not contain a video id")

    if job.upload_captions:
        caption_media = media_factory(
            str(job.caption_path),
            mimetype="application/x-subrip",
            resumable=False,
        )
        caption_request = service.captions().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "language": job.language,
                    "name": "한국어",
                    "isDraft": False,
                }
            },
            media_body=caption_media,
        )
        _execute_with_retry(caption_request, resumable=False, sleep=sleep)

    if job.playlist_id:
        playlist_request = service.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": job.playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        )
        _execute_with_retry(playlist_request, resumable=False, sleep=sleep)

    return {"video_id": video_id, "url": f"https://youtu.be/{video_id}"}
