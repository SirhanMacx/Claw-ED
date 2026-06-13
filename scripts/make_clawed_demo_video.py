#!/usr/bin/env python3
"""Build a short vertical Claw-ED demo video ending with "coming soon"."""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


W = 1080
H = 1920
FPS = 30


@dataclass(frozen=True)
class Scene:
    slug: str
    kicker: str
    hero: str
    title: str
    bullets: tuple[str, ...]
    caption: str
    narration: str
    accent: str


SCENES = [
    Scene(
        slug="01_hook",
        kicker="TEACHER AI, ON YOUR MAC",
        hero="Claw-ED",
        title="A local agent harness built for educator work.",
        bullets=(
            "Mac mini as the workhorse",
            "iPhone as the remote",
            "Real files, not just chat",
        ),
        caption="A teaching agent that runs from your Mac.",
        narration=(
            "What if the Mac on your desk could become a tireless teaching "
            "assistant?"
        ),
        accent="#48d4ff",
    ),
    Scene(
        slug="02_key",
        kicker="BRING YOUR OWN MODEL",
        hero="API key",
        title="Use OpenRouter, Ollama, or a local model.",
        bullets=(
            "Choose the provider",
            "Keep the harness local",
            "Use cloud models when output quality matters",
        ),
        caption="Local harness. Your model choice.",
        narration=(
            "Claw-ED is a local harness. You bring your own AI key, and choose "
            "the model that fits the job."
        ),
        accent="#f6c453",
    ),
    Scene(
        slug="03_index",
        kicker="INGEST AND INDEX",
        hero="19 docs",
        title="The Mac reads lesson materials and builds context.",
        bullets=(
            "19 indexed demo documents",
            "21 searchable chunks",
            "53 durable teaching brain pages",
        ),
        caption="The agent searches before it writes.",
        narration=(
            "It can ingest lesson materials, index them, and search the teacher's "
            "curriculum before generating anything."
        ),
        accent="#71e38a",
    ),
    Scene(
        slug="04_approvals",
        kicker="TEACHER CONTROL",
        hero="Approve",
        title="Risky actions pause for permission.",
        bullets=(
            "Allow once",
            "Always allow",
            "Deny and stop the action",
        ),
        caption="The iPhone can resolve Mac approvals remotely.",
        narration=(
            "When the agent wants to write files or update its teaching brain, "
            "the harness asks first."
        ),
        accent="#ff7aa2",
    ),
    Scene(
        slug="05_cloud_demo",
        kicker="LIVE CLOUD DEMO",
        hero="9 files",
        title="OpenRouter drove the local tools end to end.",
        bullets=(
            "Brain stats and index search",
            "Dream preview and self-distill",
            "Full American Revolution bundle",
        ),
        caption="Cloud model, local tools, real outputs.",
        narration=(
            "In the cloud model test, the agent ran the tools and produced a "
            "complete American Revolution teaching bundle."
        ),
        accent="#a78bfa",
    ),
    Scene(
        slug="06_outputs",
        kicker="TEACHER-READY FILES",
        hero="DOCX + PPTX",
        title="The output lands as files teachers can open.",
        bullets=(
            "Teacher lesson plan",
            "Student handout",
            "Slides and differentiation supports",
            "Review game and research note",
        ),
        caption="Not a chat answer. Classroom artifacts.",
        narration=(
            "The result is not just a response in a chat window. It is documents, "
            "slides, supports, and review materials."
        ),
        accent="#fb923c",
    ),
    Scene(
        slug="07_boundary",
        kicker="HONEST PRIVACY BOUNDARY",
        hero="Local agent",
        title="Cloud providers see tasks when you choose cloud models.",
        bullets=(
            "The Mac agent runs locally",
            "OpenRouter or Ollama cloud process model requests",
            "Local models are the privacy-first path",
        ),
        caption="Clear boundaries for teachers and districts.",
        narration=(
            "The agent runs locally. If you choose a cloud provider, the model "
            "provider processes the task data."
        ),
        accent="#38bdf8",
    ),
    Scene(
        slug="08_soon",
        kicker="CLAW-ED",
        hero="coming soon",
        title="A Mac mini harness for agentic education work.",
        bullets=(
            "Prototype in testing",
            "Mac and iPhone workflow",
            "Free resource for educators",
        ),
        caption="coming soon",
        narration="Claw-ED for educators. coming soon",
        accent="#ffffff",
    ),
]


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def wrapped(draw: ImageDraw.ImageDraw, text: str, max_width: int, fnt: ImageFont.ImageFont) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textbbox((0, 0), trial, font=fnt)[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: tuple[int, int, int], outline=None, width=2) -> None:
    draw.rounded_rectangle(box, radius=22, fill=fill, outline=outline, width=width)


def render_scene(scene: Scene, index: int, out_path: Path) -> None:
    bg = Image.new("RGB", (W, H), "#070a0f")
    accent = hex_rgb(scene.accent)

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-260, 80, 780, 1120), fill=(*accent, 44))
    gd.ellipse((520, 930, 1500, 2100), fill=(*accent, 28))
    glow = glow.filter(ImageFilter.GaussianBlur(110))
    bg = Image.alpha_composite(bg.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(bg)

    # Subtle grid.
    for y in range(240, 1640, 92):
        draw.line((90, y, W - 90, y), fill=(255, 255, 255, 9), width=1)
    for x in range(90, W - 80, 92):
        draw.line((x, 240, x, 1640), fill=(255, 255, 255, 7), width=1)

    small = font(30, bold=True)
    eyebrow = font(28, bold=True)
    hero_font = font(118 if len(scene.hero) < 13 else 92, bold=True)
    title_font = font(52, bold=True)
    bullet_font = font(38)
    caption_font = font(42, bold=True)

    draw.text((82, 70), "Claw-ED", font=font(42, bold=True), fill=(255, 255, 255))
    draw.text((W - 255, 84), "MACXLABS", font=small, fill=(185, 196, 214))

    progress_y = 154
    seg_w = 96
    for i in range(len(SCENES)):
        x0 = 82 + i * (seg_w + 12)
        fill = accent if i <= index else (48, 56, 70)
        draw.rounded_rectangle((x0, progress_y, x0 + seg_w, progress_y + 8), radius=4, fill=fill)

    draw.text((82, 255), scene.kicker, font=eyebrow, fill=accent)

    hero_lines = wrapped(draw, scene.hero, W - 164, hero_font)
    y = 335
    for line in hero_lines:
        draw.text((82, y), line, font=hero_font, fill=(255, 255, 255))
        y += hero_font.size + 6

    y += 12
    for line in wrapped(draw, scene.title, W - 164, title_font):
        draw.text((82, y), line, font=title_font, fill=(228, 235, 246))
        y += title_font.size + 10

    card_top = max(y + 58, 780)
    card = (82, card_top, W - 82, min(card_top + 470, 1350))
    draw_rounded(draw, card, (13, 18, 29), outline=(*accent, 160), width=2)
    draw.text((124, card_top + 36), "DEMO PROOF", font=font(30, bold=True), fill=accent)
    by = card_top + 104
    for bullet in scene.bullets:
        draw.ellipse((124, by + 11, 146, by + 33), fill=accent)
        lines = wrapped(draw, bullet, W - 220, bullet_font)
        for line in lines:
            draw.text((166, by), line, font=bullet_font, fill=(246, 249, 255))
            by += 48
        by += 18

    # Mini artifact strip.
    strip_y = 1410
    labels = ["teacher.docx", "student.docx", "slides.pptx"]
    for i, label in enumerate(labels):
        x = 82 + i * 306
        draw_rounded(draw, (x, strip_y, x + 270, strip_y + 120), (18, 25, 38), outline=(68, 80, 102), width=2)
        draw.rectangle((x + 28, strip_y + 30, x + 72, strip_y + 84), fill=accent)
        draw.text((x + 88, strip_y + 43), label, font=font(27, bold=True), fill=(228, 235, 246))

    caption_box = (82, H - 330, W - 82, H - 220)
    draw_rounded(draw, caption_box, (246, 249, 255), outline=None, width=0)
    cap_lines = wrapped(draw, scene.caption, W - 220, caption_font)
    cy = caption_box[1] + 28
    for line in cap_lines[:2]:
        tw = draw.textbbox((0, 0), line, font=caption_font)[2]
        draw.text(((W - tw) // 2, cy), line, font=caption_font, fill=(7, 10, 15))
        cy += 48

    if scene.slug == "08_soon":
        draw.rectangle((0, 0, W, H), fill=(7, 10, 15))
        draw.text((82, 90), "Claw-ED", font=font(56, bold=True), fill=(255, 255, 255))
        coming = "coming soon"
        f = font(126, bold=True)
        bbox = draw.textbbox((0, 0), coming, font=f)
        draw.text(((W - bbox[2]) // 2, 790), coming, font=f, fill=(255, 255, 255))
        sub = "Mac + iPhone teaching-agent harness"
        sf = font(42, bold=True)
        sb = draw.textbbox((0, 0), sub, font=sf)
        draw.text(((W - sb[2]) // 2, 950), sub, font=sf, fill=(185, 196, 214))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    bg.save(out_path, quality=95)


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nk=1:nw=1",
        str(path),
    ])
    return float(out.decode("utf-8").strip())


def build_audio(scene: Scene, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    run([
        "say",
        "-v",
        "Samantha",
        "-r",
        "178",
        "-o",
        str(path),
        scene.narration,
    ])


def build_clip(slide: Path, audio: Path, out: Path) -> None:
    duration = max(ffprobe_duration(audio) + 0.35, 2.8)
    run([
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(slide),
        "-i",
        str(audio),
        "-vf",
        "scale=1080:1920,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-shortest",
        str(out),
    ])


def concat_clips(clips: list[Path], out: Path) -> None:
    concat_file = out.parent / "concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in clips) + "\n",
        encoding="utf-8",
    )
    temp = out.with_name(out.stem + "_raw.mp4")
    run([
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        str(temp),
    ])
    run([
        "ffmpeg",
        "-y",
        "-i",
        str(temp),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(out),
    ])


def contact_sheet(video: Path, out: Path, duration: float) -> None:
    frames: list[Path] = []
    for i in range(8):
        t = min(duration - 0.5, 1.8 + i * max(2.0, (duration - 4.0) / 7.0))
        frame = out.parent / f"contact_{i:02d}.jpg"
        run([
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{t:.2f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(frame),
        ])
        frames.append(frame)
    thumbs = [Image.open(p).resize((270, 480)) for p in frames]
    sheet = Image.new("RGB", (4 * 270 + 5 * 10, 2 * 480 + 3 * 10), "#161b22")
    for i, thumb in enumerate(thumbs):
        x = 10 + (i % 4) * 280
        y = 10 + (i // 4) * 490
        sheet.paste(thumb, (x, y))
    sheet.save(out, quality=92)


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    project = Path.home() / ".eduagent" / "workspace" / "demo_videos" / f"clawed-coming-soon-{stamp}"
    if project.exists():
        shutil.rmtree(project)
    slides = project / "slides"
    audio = project / "audio"
    clips_dir = project / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    clip_paths: list[Path] = []
    manifest = {
        "title": "Claw-ED Demo - coming soon",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "width": W,
        "height": H,
        "fps": FPS,
        "scenes": [scene.__dict__ for scene in SCENES],
    }
    (project / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    for idx, scene in enumerate(SCENES):
        slide = slides / f"{scene.slug}.jpg"
        voice = audio / f"{scene.slug}.aiff"
        clip = clips_dir / f"{scene.slug}.mp4"
        render_scene(scene, idx, slide)
        build_audio(scene, voice)
        build_clip(slide, voice, clip)
        clip_paths.append(clip)

    final = project / "clawed_demo_coming_soon.mp4"
    concat_clips(clip_paths, final)
    duration = ffprobe_duration(final)
    contact = project / "contact_sheet.jpg"
    contact_sheet(final, contact, duration)

    probe = subprocess.run(
        ["ffmpeg", "-i", str(final), "-af", "volumedetect", "-f", "null", "-"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    (project / "volumedetect.txt").write_text(probe.stderr, encoding="utf-8")
    print(json.dumps({
        "project": str(project),
        "video": str(final),
        "contact_sheet": str(contact),
        "duration_seconds": round(duration, 2),
        "volumedetect": str(project / "volumedetect.txt"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
