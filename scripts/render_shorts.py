"""Render validated daily Nasdaq issue bundles into 60-second vertical Shorts."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import edge_tts
import imageio_ffmpeg

from shot_bot.shorts import load_issue_bundle, load_universe, mapping_counts, timeline, validate_bundle
from shot_bot.shorts_render import render_scene_card, write_srt

VOICE = "ko-KR-SunHiNeural"
VOICE_RATE = "+0%"


def run(command: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout}\n{completed.stderr}")
    return completed.stdout + completed.stderr


def media_duration(ffmpeg: str, path: Path) -> float:
    completed = subprocess.run([ffmpeg, "-i", str(path), "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", completed.stderr)
    if not match:
        raise RuntimeError(f"could not read media duration: {path}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def atempo_chain(factor: float) -> str:
    factors: list[float] = []
    while factor > 2.0:
        factors.append(2.0)
        factor /= 2.0
    while factor < 0.5:
        factors.append(0.5)
        factor /= 0.5
    factors.append(factor)
    return ",".join(f"atempo={item:.6f}" for item in factors)


async def synthesize(text: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    await edge_tts.Communicate(text=text, voice=VOICE, rate=VOICE_RATE).save(str(output))


def render_visuals(ffmpeg: str, cards: list[tuple[Path, float]], output: Path) -> None:
    concat = output.with_suffix(".ffconcat")
    lines = ["ffconcat version 1.0"]
    for card, duration in cards:
        escaped = card.resolve().as_posix().replace("'", "'\\''")
        lines.extend([f"file '{escaped}'", f"duration {duration:.3f}"])
    escaped = cards[-1][0].resolve().as_posix().replace("'", "'\\''")
    lines.append(f"file '{escaped}'")
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run([
        ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-t", "60", "-vf", "fps=30,scale=1120:1992:flags=lanczos,zoompan=z=1.037:x='20+18*sin(on/38)':y='36+24*cos(on/52)':d=1:s=1080x1920:fps=30,format=yuv420p",
        "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-movflags", "+faststart", str(output),
    ])


def fit_narration(ffmpeg: str, source: Path, output: Path) -> float:
    source_duration = media_duration(ffmpeg, source)
    factor = source_duration / 59.2
    filters = f"{atempo_chain(factor)},apad,atrim=duration=60"
    run([ffmpeg, "-y", "-i", str(source), "-af", filters, "-c:a", "aac", "-b:a", "160k", str(output)])
    return source_duration


def mux(ffmpeg: str, video: Path, audio: Path, output: Path) -> None:
    run([
        ffmpeg, "-y", "-i", str(video), "-i", str(audio), "-t", "60",
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy",
        "-movflags", "+faststart", str(output),
    ])


def write_script(issue: dict[str, Any], segments: list[dict[str, Any]], path: Path) -> None:
    lines = [f"# {issue['title']}", "", "## 60초 대본", ""]
    for item in segments:
        lines.extend([
            f"### {item['start']:04.1f}~{item['end']:04.1f}초 · {item['kind']}",
            "",
            item["narration"],
            "",
            f"화면: **{item['headline']}** — {item['body']}",
            "",
        ])
    lines.extend(["## 출처", ""])
    for source in issue["sources"]:
        lines.append(f"- {source['publisher']} ({source['published']}): {source['url']}")
    lines.extend(["", "## 설명란 면책", "", "본 콘텐츠는 공개 자료를 바탕으로 한 일반 정보이며 특정 증권의 매수·매도 권유가 아닙니다. 시장 상황과 데이터는 변경될 수 있으며 투자 판단과 책임은 시청자 본인에게 있습니다.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def render_issue(ffmpeg: str, issue: dict[str, Any], bundle: dict[str, Any], universe: list[str], output_dir: Path, *, force_voice: bool) -> dict[str, Any]:
    slug = issue["slug"]
    work = output_dir / "assets" / slug
    work.mkdir(parents=True, exist_ok=True)
    segments = timeline(issue["scenes"])
    cards: list[tuple[Path, float]] = []
    for number, segment in enumerate(segments, start=1):
        path = work / f"scene_{number:02d}_{segment['kind']}.png"
        render_scene_card(issue=issue, segment=segment, universe=universe, issue_date=bundle["issue_date"], scene_number=number).save(path, quality=95)
        cards.append((path, segment["duration"]))

    srt = output_dir / f"{slug}.srt"
    write_srt(segments, srt)
    write_script(issue, segments, output_dir / f"{slug}_script.md")
    narration_text = " ".join(segment["narration"] for segment in segments)
    voice = work / "narration.mp3"
    if force_voice or not voice.exists():
        asyncio.run(synthesize(narration_text, voice))

    silent = work / "visuals.mp4"
    fitted = work / "narration_60s.m4a"
    final = output_dir / f"{slug}.mp4"
    render_visuals(ffmpeg, cards, silent)
    source_audio_duration = fit_narration(ffmpeg, voice, fitted)
    mux(ffmpeg, silent, fitted, final)
    duration = media_duration(ffmpeg, final)
    return {
        "slug": slug,
        "title": issue["title"],
        "video": final.name,
        "script": f"{slug}_script.md",
        "captions": srt.name,
        "duration_seconds": duration,
        "resolution": "1080x1920",
        "fps": 30,
        "source_audio_duration_seconds": round(source_audio_duration, 2),
        "mapping_counts": mapping_counts(issue, universe),
        "sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
        "bytes": final.stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issues", required=True)
    parser.add_argument("--universe", default="config/shorts_50_universe.json")
    parser.add_argument("--force-voice", action="store_true")
    args = parser.parse_args()
    issues_path = Path(args.issues)
    output_dir = issues_path.parent
    universe = load_universe(args.universe)
    bundle = load_issue_bundle(issues_path)
    validate_bundle(bundle, universe)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    results = [render_issue(ffmpeg, issue, bundle, universe, output_dir, force_voice=args.force_voice) for issue in bundle["issues"]]
    manifest = {
        "issue_date": bundle["issue_date"],
        "created_for_timezone": bundle["timezone"],
        "voice": VOICE,
        "strategy": "50종목 이슈 매핑 후 기존 리밸런싱 점수·유동성·RSI와 결합",
        "current_rebalance_candidates": bundle["current_rebalance_candidates"],
        "videos": results,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
