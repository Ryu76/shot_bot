"""Upload rendered Nasdaq Shorts to YouTube with OAuth 2.0."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from shot_bot.youtube_upload import (
    build_upload_jobs,
    discover_latest_output,
    get_youtube_service,
    load_upload_config,
    load_upload_state,
    pending_jobs,
    save_upload_state,
    upload_job,
)


def output_folder(shorts_root: Path, date: str | None) -> Path:
    if date:
        folder = shorts_root / date
        if not (folder / "manifest.json").is_file():
            raise FileNotFoundError(f"완료된 manifest.json이 없습니다: {folder}")
        return folder
    return discover_latest_output(shorts_root)


def dry_run_payload(jobs):
    return [
        {
            "slug": job.slug,
            "video": str(job.video_path),
            "caption": str(job.caption_path),
            "title": job.title,
            "privacy_status": job.privacy_status,
            "made_for_kids": job.made_for_kids,
            "playlist_id": job.playlist_id or None,
            "upload_captions": job.upload_captions,
            "notify_subscribers": job.notify_subscribers,
        }
        for job in jobs
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="날짜별 Nasdaq Shorts를 YouTube에 중복 없이 업로드합니다.")
    parser.add_argument("--config", default="config/youtube_upload.json")
    parser.add_argument("--shorts-root", default="shorts")
    parser.add_argument("--date", help="YYYY-MM-DD. 생략하면 manifest가 있는 최신 폴더")
    parser.add_argument("--dry-run", action="store_true", help="OAuth/API 호출 없이 업로드 계획만 검증")
    parser.add_argument("--limit", type=int, default=0, help="이번 실행에서 올릴 최대 영상 수. 0은 전체")
    args = parser.parse_args()

    try:
        config = load_upload_config(args.config)
        folder = output_folder(Path(args.shorts_root), args.date)
        state_path = folder / "youtube_upload_state.json"
        state = load_upload_state(state_path)
        jobs = pending_jobs(build_upload_jobs(folder, config), state)
        if args.limit > 0:
            jobs = jobs[: args.limit]
        if args.dry_run:
            print(json.dumps(dry_run_payload(jobs), ensure_ascii=False, indent=2))
            return 0
        if not jobs:
            print("업로드할 새 영상이 없습니다.")
            return 0

        service = get_youtube_service(config)
        for index, job in enumerate(jobs, start=1):
            print(f"[{index}/{len(jobs)}] 업로드 시작: {job.video_path.name}", flush=True)
            result = upload_job(service, job)
            state[job.slug] = {
                **result,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "privacy_status": job.privacy_status,
            }
            save_upload_state(state_path, state)
            print(f"완료: {result['url']}", flush=True)
        return 0
    except Exception as exc:
        print(f"업로드 실패: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
