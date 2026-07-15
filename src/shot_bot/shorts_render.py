"""Pillow-based vertical card renderer for issue Shorts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1920
BG_TOP = (9, 17, 31)
BG_BOTTOM = (17, 30, 48)
WHITE = (244, 247, 251)
MUTED = (158, 174, 194)
GREEN = (91, 230, 157)
ORANGE = (255, 178, 76)
RED = (255, 100, 111)
CYAN = (89, 206, 255)
NEUTRAL = (59, 75, 97)


def _font_path(bold: bool = False) -> str:
    candidates = (
        [r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf"]
        if bold
        else [r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunbd.ttf"]
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError("Korean Malgun Gothic font was not found")


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_font_path(bold), size)


def _background() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG_TOP)
    pixels = image.load()
    for y in range(HEIGHT):
        ratio = y / (HEIGHT - 1)
        color = tuple(round(a + (b - a) * ratio) for a, b in zip(BG_TOP, BG_BOTTOM))
        for x in range(WIDTH):
            pixels[x, y] = color
    return image


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = str(text).replace("\n", " \n ").split()
    lines: list[str] = []
    current = ""
    for word in words:
        if word == "\n":
            if current:
                lines.append(current)
                current = ""
            continue
        candidate = word if not current else f"{current} {word}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_text_block(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], font: ImageFont.FreeTypeFont, fill: tuple[int, int, int], max_width: int, spacing: int = 16) -> int:
    x, y = xy
    lines = _wrap(draw, text, font, max_width)
    line_height = font.size + spacing
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def _group_for(ticker: str, issue: dict[str, Any]) -> str:
    for group in ("positive", "watch", "risk"):
        if ticker in issue["mapping"].get(group, []):
            return group
    return "neutral"


def _heatmap(draw: ImageDraw.ImageDraw, issue: dict[str, Any], universe: list[str], top: int) -> None:
    colors = {"positive": GREEN, "watch": ORANGE, "risk": RED, "neutral": NEUTRAL}
    labels = {"positive": "긍정", "watch": "관찰", "risk": "위험", "neutral": "중립"}
    x0, gap, cell_w, cell_h = 70, 10, 180, 64
    for index, ticker in enumerate(universe):
        row, col = divmod(index, 5)
        x = x0 + col * (cell_w + gap)
        y = top + row * (cell_h + gap)
        group = _group_for(ticker, issue)
        color = colors[group]
        draw.rounded_rectangle((x, y, x + cell_w, y + cell_h), radius=12, fill=tuple(int(c * 0.23) for c in color), outline=color, width=2)
        draw.text((x + 14, y + 14), ticker, font=_font(26, bold=True), fill=WHITE)
    legend_y = top + 10 * (cell_h + gap) + 15
    legend_x = 70
    for group in ("positive", "watch", "risk", "neutral"):
        color = colors[group]
        draw.rounded_rectangle((legend_x, legend_y, legend_x + 24, legend_y + 24), radius=5, fill=color)
        draw.text((legend_x + 34, legend_y - 4), labels[group], font=_font(24), fill=MUTED)
        legend_x += 210


def _group_cards(draw: ImageDraw.ImageDraw, issue: dict[str, Any], top: int) -> None:
    groups = (("positive", "긍정", GREEN), ("watch", "관찰", ORANGE), ("risk", "위험", RED))
    y = top
    for key, label, color in groups:
        values = issue["mapping"].get(key, [])
        draw.rounded_rectangle((70, y, 1010, y + 185), radius=24, fill=(25, 40, 60), outline=color, width=3)
        draw.text((100, y + 24), f"{label}  {len(values)}", font=_font(31, bold=True), fill=color)
        ticker_text = " · ".join(values[:9]) if values else "해당 없음"
        _draw_text_block(draw, ticker_text, (100, y + 78), _font(28, bold=True), WHITE, 840, 10)
        y += 210


def render_scene_card(*, issue: dict[str, Any], segment: dict[str, Any], universe: list[str], issue_date: str, scene_number: int) -> Image.Image:
    image = _background()
    draw = ImageDraw.Draw(image)
    accent = {"twist": RED, "heatmap": CYAN, "invalidation": ORANGE, "loop": GREEN}.get(segment["kind"], GREEN)

    draw.rectangle((0, 0, WIDTH, 22), fill=(30, 44, 63))
    draw.rectangle((0, 0, int(WIDTH * segment["end"] / 60), 22), fill=accent)
    draw.text((70, 68), "NASDAQ ISSUE / 60 SEC", font=_font(25, bold=True), fill=accent)
    draw.text((790, 68), f"{scene_number:02d} / 09", font=_font(25, bold=True), fill=MUTED)
    draw.text((70, 125), issue_date, font=_font(25), fill=MUTED)

    y = _draw_text_block(draw, segment["headline"], (70, 220), _font(64, bold=True), WHITE, 930, 18)
    draw.rounded_rectangle((70, y + 22, 1010, y + 180), radius=24, fill=(24, 40, 61), outline=accent, width=3)
    _draw_text_block(draw, segment["body"], (105, y + 58), _font(34, bold=True), accent, 870, 12)
    content_top = y + 235

    if segment["kind"] == "heatmap":
        _heatmap(draw, issue, universe, content_top)
    elif segment["kind"] == "groups":
        _group_cards(draw, issue, content_top)
    else:
        number = str(scene_number).zfill(2)
        draw.text((70, content_top + 20), number, font=_font(190, bold=True), fill=(34, 55, 79))
        narration_y = content_top + 260
        _draw_text_block(draw, segment["narration"], (70, narration_y), _font(42, bold=True), WHITE, 930, 18)
        draw.line((70, 1430, 1010, 1430), fill=(48, 67, 90), width=2)
        draw.text((70, 1475), "사실", font=_font(28, bold=True), fill=CYAN)
        _draw_text_block(draw, issue["fact"], (160, 1470), _font(27), MUTED, 830, 10)

    publisher = issue["sources"][0]["publisher"]
    draw.text((70, 1740), f"출처: {publisher} · {issue_date}", font=_font(24), fill=MUTED)
    draw.text((70, 1790), "50종목 이슈 매핑 · 기존 점수/유동성/RSI와 함께 판단", font=_font(23), fill=MUTED)
    draw.rounded_rectangle((70, 1840, 1010, 1890), radius=12, fill=(22, 35, 52))
    draw.text((95, 1850), "정보 제공 목적이며 투자 권유가 아닙니다.", font=_font(22, bold=True), fill=(195, 205, 218))
    return image


def _srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(segments: list[dict[str, Any]], path: str | Path) -> Path:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.extend([
            str(index),
            f"{_srt_time(segment['start'])} --> {_srt_time(segment['end'])}",
            segment["narration"],
            "",
        ])
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
