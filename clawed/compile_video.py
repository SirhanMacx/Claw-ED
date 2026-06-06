"""Faceless narrated educational-video pipeline (local-first, no paid API).

Turns a list of scenes into a captioned MP4:

    script (scenes[] + meta)
      -> per-scene HTML/CSS rendered to PNG via Chrome headless ``--screenshot``
      -> neural voiceover (edge-tts preferred, macOS ``say`` fallback)
      -> ffmpeg ``zoompan`` Ken-Burns clips
      -> concat + mux voice + fade-in/out
      -> final.mp4 (verified with ffprobe)

Ported from the proven MacxLabs ``build_video.py`` engine and adapted to
Claw-ED conventions: binaries are resolved via :func:`shutil.which` with a
common-path fallback list (no hard-coded user paths), Chrome is resolved the
same way other binaries are, output respects the caller's ``out_path``, and
missing dependencies raise a clear, catchable :class:`VideoDependencyError`
rather than calling ``sys.exit``.

Public API
----------
``build_video(scenes, meta, out_path, image_resolver=None) -> Path``
    Render the whole pipeline and return the path to the finished MP4.

``scenes_from_lesson(topic, points, narration, aspect="9:16") -> list[dict]``
    Map lesson-shaped content (a title, key points, and per-point narration)
    into the scene dicts ``build_video`` expects.

Everything is free and runs locally. edge-tts uses Microsoft's free neural
voices over the network (no key); when offline or unavailable it degrades to
the macOS ``say`` command, and ``build_video`` still produces a video.
"""

from __future__ import annotations

import html
import logging
import math
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Errors ───────────────────────────────────────────────────────────


class VideoDependencyError(RuntimeError):
    """A required external tool (ffmpeg / ffprobe / Chrome) is unavailable.

    Raised before any work begins so callers (e.g. the generate_video tool)
    can catch it and surface friendly install guidance instead of crashing.
    """


class VideoBuildError(RuntimeError):
    """A pipeline step (render / tts / encode) failed."""


# ── Binary resolution (shutil.which + common-path fallback) ──────────
# No hard-coded user paths: we search PATH first, then a small set of
# well-known install locations, then (for Chrome) macOS app bundles.

_BIN_FALLBACK_DIRS = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/snap/bin",
)

# macOS / Linux Chrome & Chromium locations checked after PATH.
_CHROME_FALLBACKS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/opt/homebrew/bin/chromium",
    "/usr/local/bin/chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)

# PATH names Chrome/Chromium might be installed under.
_CHROME_PATH_NAMES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
)


def _resolve_binary(
    names: tuple[str, ...] | str,
    fallbacks: tuple[str, ...] = (),
    env_vars: tuple[str, ...] = (),
) -> str | None:
    """Resolve an executable: env override → PATH (``which``) → fallbacks.

    Returns the absolute path to a runnable executable, or ``None``.
    """
    if isinstance(names, str):
        names = (names,)

    # 1) Explicit env override always wins (and must point at a real file).
    for env in env_vars:
        val = os.environ.get(env)
        if val and os.path.isfile(val) and os.access(val, os.X_OK):
            return val

    # 2) PATH lookup.
    for name in names:
        found = shutil.which(name)
        if found:
            return found

    # 3) Common install locations not on PATH.
    for name in names:
        for d in _BIN_FALLBACK_DIRS:
            cand = os.path.join(d, name)
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand

    # 4) Caller-supplied fully-qualified fallbacks (e.g. macOS app bundles).
    for cand in fallbacks:
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand

    return None


def find_ffmpeg() -> str | None:
    """Locate the ``ffmpeg`` binary, or ``None`` if unavailable."""
    return _resolve_binary("ffmpeg", env_vars=("EDUAGENT_FFMPEG", "FFMPEG"))


def find_ffprobe() -> str | None:
    """Locate the ``ffprobe`` binary, or ``None`` if unavailable."""
    return _resolve_binary("ffprobe", env_vars=("EDUAGENT_FFPROBE", "FFPROBE"))


def find_chrome() -> str | None:
    """Locate a Chrome/Chromium binary for headless screenshots.

    Resolution mirrors the other binaries: ``EDUAGENT_CHROME`` / ``CHROME``
    env override, then PATH, then a list of common desktop install paths
    (macOS app bundles + Linux locations). Returns ``None`` if none found.
    """
    return _resolve_binary(
        _CHROME_PATH_NAMES,
        fallbacks=_CHROME_FALLBACKS,
        env_vars=("EDUAGENT_CHROME", "CHROME", "CHROME_BIN", "CHROMIUM"),
    )


def find_edge_tts() -> str | None:
    """Locate the ``edge-tts`` CLI (free Microsoft neural TTS), or ``None``.

    Checks PATH plus the user-local ``~/.local/bin`` install location that
    ``pip install --user edge-tts`` uses.
    """
    found = _resolve_binary("edge-tts", env_vars=("EDUAGENT_EDGE_TTS", "EDGE_TTS"))
    if found:
        return found
    user_bin = Path.home() / ".local" / "bin" / "edge-tts"
    if user_bin.is_file() and os.access(user_bin, os.X_OK):
        return str(user_bin)
    return None


def find_say() -> str | None:
    """Locate the macOS ``say`` command (offline TTS fallback)."""
    return _resolve_binary("say")


def check_dependencies() -> dict[str, str | None]:
    """Return a map of pipeline dependency → resolved path (or ``None``).

    Useful for tools that want to give precise install guidance before
    starting a build.
    """
    return {
        "ffmpeg": find_ffmpeg(),
        "ffprobe": find_ffprobe(),
        "chrome": find_chrome(),
        "edge-tts": find_edge_tts(),
        "say": find_say(),
    }


# ── Shell helper ──────────────────────────────────────────────────────


def _run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run a subprocess, raising :class:`VideoBuildError` on failure."""
    proc = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-1500:]
        logger.error("Command failed (%s): %s", proc.returncode, " ".join(cmd[:4]))
        raise VideoBuildError(
            f"Command failed: {os.path.basename(cmd[0])} "
            f"(exit {proc.returncode}). {tail.strip()[-400:]}"
        )
    return proc


def _duration_of(ffprobe: str, path: Path) -> float:
    """Return media duration in seconds via ffprobe."""
    proc = _run([
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path),
    ])
    try:
        return float(proc.stdout.strip())
    except ValueError as exc:  # pragma: no cover - defensive
        raise VideoBuildError(f"Could not read duration of {path.name}: {exc}") from exc


# ── Aspect ratio → pixel dimensions ──────────────────────────────────

_ASPECT_DIMS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),   # vertical (Shorts / Reels / TikTok)
    "16:9": (1920, 1080),   # widescreen (YouTube / projector)
    "1:1": (1080, 1080),    # square
    "4:5": (1080, 1350),    # portrait feed
}


def _dims_for_aspect(aspect: str) -> tuple[int, int]:
    return _ASPECT_DIMS.get((aspect or "9:16").strip(), _ASPECT_DIMS["9:16"])


# ── Decorative SVG visuals (clean, abstract, on-brand) ───────────────
# Ported from build_video.py. Rendered inside the slide HTML so no extra
# binary is needed. ``visual`` keys map to a vector motif; unknown / "none"
# render nothing (the slide still looks good with just text + Ken Burns).


def _svg(visual: str, accent: str) -> str:
    a = accent
    dim = "rgba(255,255,255,.14)"
    if visual == "spark":
        rays = "".join(
            f'<line x1="300" y1="190" x2="{300 + 155 * math.cos(i * 0.5236):.0f}" '
            f'y2="{190 + 155 * math.sin(i * 0.5236):.0f}" stroke="{a}" '
            f'stroke-width="6" stroke-linecap="round" opacity="{0.35 + 0.55 * (i % 2)}"/>'
            for i in range(12)
        )
        return (
            f'<svg viewBox="0 0 600 380"><circle cx="300" cy="190" r="150" fill="none" '
            f'stroke="{dim}" stroke-width="2"/><circle cx="300" cy="190" r="100" fill="none" '
            f'stroke="{dim}" stroke-width="2"/>{rays}<circle cx="300" cy="190" r="34" fill="{a}"/>'
            f'<circle cx="300" cy="190" r="60" fill="none" stroke="{a}" stroke-width="3" opacity=".5"/></svg>'
        )
    if visual == "bars":
        heights = [70, 120, 180, 250, 320]
        bars = ""
        for i, h in enumerate(heights):
            x = 70 + i * 100
            op = 0.45 + 0.55 * i / 4
            bars += f'<rect x="{x}" y="{340 - h}" width="64" height="{h}" rx="10" fill="{a}" opacity="{op:.2f}"/>'
        return (
            f'<svg viewBox="0 0 600 380"><line x1="55" y1="342" x2="560" y2="342" '
            f'stroke="{dim}" stroke-width="3"/>{bars}</svg>'
        )
    if visual == "globe":
        lon = "".join(
            f'<ellipse cx="300" cy="190" rx="{rx}" ry="150" fill="none" stroke="{dim}" stroke-width="2"/>'
            for rx in (45, 95, 140)
        )
        lat = "".join(
            f'<line x1="160" y1="{190 + dy}" x2="440" y2="{190 + dy}" stroke="{dim}" stroke-width="2"/>'
            for dy in (-80, 0, 80)
        )
        return (
            f'<svg viewBox="0 0 600 380"><circle cx="300" cy="190" r="150" fill="none" '
            f'stroke="{a}" stroke-width="3"/>{lon}{lat}'
            f'<path d="M300 40 A150 150 0 0 1 450 190 L300 190 Z" fill="{a}" opacity=".18"/>'
            f'<path d="M300 340 A150 150 0 0 1 150 190 L300 190 Z" fill="{a}" opacity=".30"/></svg>'
        )
    if visual == "steps":
        rows = ""
        for i in range(4):
            y = 70 + i * 78
            rows += (
                f'<rect x="120" y="{y}" width="{180 + i * 70}" height="54" rx="14" '
                f'fill="{a}" opacity="{0.30 + 0.18 * i:.2f}"/>'
            )
        return f'<svg viewBox="0 0 600 380">{rows}</svg>'
    if visual == "brand":
        return (
            f'<svg viewBox="0 0 600 380"><rect x="232" y="92" width="136" height="136" rx="30" '
            f'fill="none" stroke="{a}" stroke-width="5"/>'
            f'<circle cx="300" cy="160" r="40" fill="{a}" opacity=".85"/>'
            f'<text x="300" y="300" text-anchor="middle" font-size="34" font-weight="800" '
            f'fill="rgba(255,255,255,.92)" letter-spacing="4">CLAW-ED</text></svg>'
        )
    return "<svg viewBox='0 0 600 380'></svg>"


# ── Slide HTML (captions baked in — no ffmpeg text filter needed) ────


def _slide_html(
    sc: dict[str, Any],
    idx: int,
    total: int,
    width: int,
    height: int,
    brand: str,
    tag: str,
) -> str:
    """Build the HTML for one slide. Mirrors the MacxLabs slide design,
    parameterised by output dimensions and brand text."""
    accent = sc.get("accent", "#60a5fa")
    hero = str(sc.get("hero", ""))
    is_letter = len(hero) <= 2 and bool(hero)
    if is_letter:
        hero_block = (
            f'<div class="badge" style="border-color:{accent};color:{accent};'
            f'box-shadow:0 0 60px {accent}44">{html.escape(hero)}</div>'
        )
    elif hero:
        hero_block = f'<div class="herotext">{html.escape(hero)}</div>'
    else:
        hero_block = ""

    segs = "".join(
        f'<span class="seg {"on" if i <= idx else ""}"></span>' for i in range(total)
    )

    art = sc.get("art")  # optional background image (absolute path) — already resolved
    art_layer = ""
    if art and Path(str(art)).exists():
        art_uri = Path(str(art)).resolve().as_uri()
        art_layer = (
            f'<div class="art" style="background-image:url(\'{art_uri}\')"></div>'
            f'<div class="scrim"></div>'
        )

    kicker = html.escape(str(sc.get("kicker", "")))
    title = html.escape(str(sc.get("title", "")))
    detail = html.escape(str(sc.get("detail", "")))
    caption = html.escape(str(sc.get("caption", "")))
    visual = str(sc.get("visual", "none"))

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
:root{{--a:{accent}}}
*{{margin:0;box-sizing:border-box}}
html,body{{width:{width}px;height:{height}px;overflow:hidden}}
body{{background:#070a0f;font-family:"Avenir Next","Helvetica Neue","Segoe UI",Arial,sans-serif;color:#fff;
  background-image:radial-gradient(1200px 900px at 50% 24%, {accent}1f, transparent 60%),
    radial-gradient(900px 900px at 50% 118%, #0c1320, transparent 70%);}}
.grain{{position:absolute;inset:0;z-index:1;opacity:.05;
  background-image:radial-gradient(rgba(255,255,255,.7) 1px, transparent 1px);background-size:38px 38px}}
.art{{position:absolute;inset:0;z-index:0;background-size:cover;background-position:center}}
.scrim{{position:absolute;inset:0;z-index:1;background:
  radial-gradient(1100px 850px at 50% 26%, {accent}2b, transparent 62%),
  linear-gradient(180deg, rgba(6,9,14,.76), rgba(6,9,14,.5) 42%, rgba(6,9,14,.92));}}
.top,.prog,.wrap,.cap{{z-index:2}}
.top{{position:absolute;top:60px;left:0;right:0;display:flex;
  justify-content:space-between;align-items:center;padding:0 80px}}
.wm{{display:flex;align-items:center;gap:16px;font-weight:800;letter-spacing:1px;font-size:34px}}
.wm .sq{{width:34px;height:34px;border-radius:9px;border:3px solid {accent}}}
.tag{{font-size:26px;font-weight:700;letter-spacing:3px;color:rgba(255,255,255,.55);
  border:2px solid rgba(255,255,255,.18);border-radius:999px;padding:10px 22px}}
.prog{{position:absolute;top:140px;left:0;right:0;display:flex;gap:12px;justify-content:center;padding:0 90px}}
.seg{{height:7px;border-radius:99px;background:rgba(255,255,255,.15);flex:1;max-width:96px}}
.seg.on{{background:var(--a)}}
.wrap{{position:absolute;left:0;right:0;top:300px;padding:0 90px;text-align:center;
  display:flex;flex-direction:column;align-items:center}}
.kick{{color:{accent};font-weight:800;letter-spacing:7px;font-size:32px;margin-bottom:30px}}
.badge{{width:264px;height:264px;border-radius:46px;border:6px solid;display:flex;
  align-items:center;justify-content:center;
  font-size:186px;font-weight:900;line-height:1;margin-bottom:34px;background:rgba(255,255,255,.02)}}
.herotext{{font-size:96px;font-weight:900;letter-spacing:-2px;line-height:1.04;margin-bottom:26px;max-width:920px}}
.title{{font-size:84px;font-weight:800;letter-spacing:-1px;margin-bottom:22px;max-width:940px}}
.detail{{font-size:46px;font-weight:600;color:rgba(255,255,255,.74);max-width:860px;line-height:1.26;margin-bottom:26px}}
.stage{{margin-top:10px;width:720px;height:360px;display:flex;align-items:center;justify-content:center}}
.stage svg{{width:100%;height:100%}}
.cap{{position:absolute;left:70px;right:70px;bottom:312px;display:flex;justify-content:center}}
.cap span{{background:rgba(6,10,16,.62);border:1px solid rgba(255,255,255,.10);border-radius:24px;
  padding:24px 36px;font-size:46px;font-weight:700;line-height:1.24;color:#fff;max-width:900px;
  text-align:center;box-shadow:0 12px 44px rgba(0,0,0,.45)}}
</style></head><body>{art_layer}<div class="grain"></div>
<div class="top"><div class="wm"><span class="sq"></span>{html.escape(brand)}</div>
<div class="tag">{html.escape(tag)}</div></div>
<div class="prog">{segs}</div>
<div class="wrap">
  <div class="kick">{kicker}</div>
  {hero_block}
  <div class="title">{title}</div>
  <div class="detail">{detail}</div>
  <div class="stage">{_svg(visual, accent)}</div>
</div>
<div class="cap"><span>{caption}</span></div>
</body></html>"""


# ── Scene mapping helper ──────────────────────────────────────────────

# A rotating palette so consecutive scenes feel distinct, mirroring the
# per-scene accents in the cold-war example.
_ACCENTS = (
    "#60a5fa", "#a5b4fc", "#f87171", "#fbbf24",
    "#fb923c", "#34d399", "#5eead4", "#c084fc",
)
# Lightweight kicker labels cycled per content scene.
_KICKERS = (
    "KEY IDEA", "WHAT TO KNOW", "THE DETAILS", "WHY IT MATTERS",
    "IN CONTEXT", "REMEMBER THIS", "THE TAKEAWAY", "GOING DEEPER",
)


def _split_hero_title(point: str) -> tuple[str, str, str]:
    """Split a key point into (hero, title, detail) for a slide.

    A point like ``"Containment: stop communism from spreading"`` becomes
    hero/title ``"Containment"`` with detail ``"stop communism from spreading"``.
    Points with no separator put the whole point in the title.
    """
    point = (point or "").strip()
    for sep in (": ", " — ", " – ", " - "):
        if sep in point:
            head, _, tail = point.partition(sep)
            head = head.strip()
            tail = tail.strip()
            if head and tail:
                # Short head reads well as the big hero line; longer heads
                # become the title with the tail as supporting detail.
                if len(head) <= 22:
                    return head, head, tail
                return "", head, tail
    return "", point, ""


def scenes_from_lesson(
    topic: str,
    points: list[str],
    narration: list[str],
    aspect: str = "9:16",
) -> list[dict[str, Any]]:
    """Map lesson content into the scene dicts :func:`build_video` consumes.

    Produces an intro (hook) scene, one scene per key point, and a closing
    scene. Each scene carries every field the renderer needs: ``id``,
    ``accent``, ``kicker``, ``hero``, ``title``, ``detail``, ``visual``,
    ``narration``, ``caption``.

    Parameters
    ----------
    topic:
        The video title / subject (used for the opening hero and intro).
    points:
        4-6 key teaching points. Each becomes one content scene.
    narration:
        One narration line per key point (same length as ``points`` when
        possible). If shorter, the point text is reused as narration.
    aspect:
        Output aspect ratio (kept on each scene for callers that inspect it).
    """
    topic = (topic or "Lesson").strip()
    points = [p.strip() for p in (points or []) if p and p.strip()]
    narration = list(narration or [])

    scenes: list[dict[str, Any]] = []

    # 1) Hook / title scene.
    intro_narration = (
        narration[0]
        if narration and len(narration) > len(points)
        else f"Let's break down {topic} in just a minute."
    )
    scenes.append({
        "id": "00_intro",
        "accent": _ACCENTS[0],
        "kicker": "QUICK REVIEW",
        "hero": topic if len(topic) <= 26 else "",
        "title": topic if len(topic) > 26 else "A quick breakdown",
        "detail": "Everything you need, fast.",
        "visual": "spark",
        "narration": intro_narration,
        "caption": topic,
        "aspect": aspect,
    })

    # Align narration to points (intro may have consumed narration[0]).
    if len(narration) > len(points):
        point_narration = narration[1:]
    else:
        point_narration = narration

    # 2) One scene per key point.
    for i, point in enumerate(points):
        hero, title, detail = _split_hero_title(point)
        if i < len(point_narration) and point_narration[i].strip():
            narr = point_narration[i].strip()
        else:
            narr = point
        scenes.append({
            "id": f"{i + 1:02d}_point",
            "accent": _ACCENTS[(i + 1) % len(_ACCENTS)],
            "kicker": _KICKERS[i % len(_KICKERS)],
            "hero": hero,
            "title": title or point,
            "detail": detail,
            "visual": ("bars", "globe", "steps", "spark")[i % 4],
            "narration": narr,
            "caption": point if len(point) <= 90 else point[:87] + "…",
            "aspect": aspect,
        })

    # 3) Closing scene.
    scenes.append({
        "id": "99_outro",
        "accent": _ACCENTS[(len(points) + 1) % len(_ACCENTS)],
        "kicker": "KEEP STUDYING",
        "hero": "",
        "title": "You've got this.",
        "detail": f"Review {topic} anytime.",
        "visual": "brand",
        "narration": f"That's {topic}. Review it anytime — you've got this.",
        "caption": f"Review {topic} anytime.",
        "aspect": aspect,
    })

    return scenes


# ── TTS for one scene ────────────────────────────────────────────────


def _synthesize_scene_audio(
    text: str,
    out_wav: Path,
    workdir: Path,
    ffmpeg: str,
    voice: str,
    edge_rate: str,
    edge_bin: str | None,
    say_bin: str | None,
    say_voice: str,
    say_rate: int,
) -> None:
    """Render one narration line to a normalized mono 48k WAV.

    Prefers edge-tts (free neural). Falls back to macOS ``say``. The raw
    audio is run through the same broadcast-style filter chain as the
    original engine (highpass / compress / normalize / limiter / pad).
    """
    src: Path | None = None

    # 1) Preferred: edge-tts neural voice (network, no key).
    if edge_bin:
        mp3 = workdir / (out_wav.stem + ".mp3")
        try:
            _run([
                edge_bin, "--voice", voice, f"--rate={edge_rate}",
                "--text", text, "--write-media", str(mp3),
            ])
            if mp3.exists() and mp3.stat().st_size > 0:
                src = mp3
        except VideoBuildError as exc:
            logger.warning("edge-tts failed (%s); falling back to 'say'", exc)

    # 2) Fallback: macOS `say`.
    if src is None and say_bin:
        aiff = workdir / (out_wav.stem + ".aiff")
        _run([say_bin, "-v", say_voice, "-r", str(say_rate), "-o", str(aiff), text])
        if aiff.exists() and aiff.stat().st_size > 0:
            src = aiff

    if src is None:
        raise VideoDependencyError(
            "No text-to-speech engine available. Install the free neural voice "
            "with: pip install edge-tts (or run on macOS for the 'say' fallback)."
        )

    # Normalize → mono 48k WAV with a gentle broadcast chain + tail pad.
    _run([
        ffmpeg, "-y", "-i", str(src), "-af",
        "highpass=f=85,acompressor=threshold=-18dB:ratio=3:attack=8:release=180,"
        "dynaudnorm=f=200:g=6,alimiter=limit=0.95,adelay=150,apad=pad_dur=0.30",
        "-ac", "1", "-ar", "48000", str(out_wav),
    ])


# ── Main pipeline ─────────────────────────────────────────────────────


def build_video(
    scenes: list[dict[str, Any]],
    meta: dict[str, Any],
    out_path: str | Path,
    image_resolver: Callable[[dict[str, Any]], Path | None] | None = None,
) -> Path:
    """Render scenes + meta into a captioned MP4 at ``out_path``.

    Parameters
    ----------
    scenes:
        List of scene dicts (see :func:`scenes_from_lesson` for the shape).
        Each needs at least ``narration``; visual fields default sensibly.
    meta:
        Video-level settings. Recognised keys::

            aspect       "9:16" | "16:9" | "1:1" | "4:5"  (default "9:16")
            width/height explicit pixel size (overrides aspect)
            fps          frames per second (default 30)
            voice        edge-tts voice (default en-US-AndrewMultilingualNeural)
            edge_rate    edge-tts rate, e.g. "+10%" (default "+8%")
            say_voice    macOS say voice fallback (default "Samantha")
            say_rate     macOS say words-per-minute (default 178)
            brand        watermark text (default "Claw-ED")
            tag          top-right tag pill (default "EDUCATIONAL")
            no_audio     if True, build a silent timed video (testing)

    out_path:
        Destination ``.mp4`` path. Parent dirs are created.
    image_resolver:
        Optional callback ``scene -> Path|None``. When provided, each scene
        is passed to it; a returned image becomes that scene's background
        ("art" layer). Lets callers wire in Claw-ED's image sourcing
        (e.g. ``slide_images.fetch_slide_image``) without this module
        depending on it. Failures are swallowed (slide renders text-only).

    Returns
    -------
    Path to the finished MP4.

    Raises
    ------
    VideoDependencyError
        If ffmpeg / ffprobe / Chrome (and, when audio is on, a TTS engine)
        are unavailable. Raised before work begins so callers can recover.
    VideoBuildError
        If a render / encode step fails.
    """
    if not scenes:
        raise VideoBuildError("No scenes provided — nothing to render.")

    # ── Resolve dependencies up front (fail fast, fail clear) ─────────
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    chrome = find_chrome()

    missing = []
    if not ffmpeg:
        missing.append("ffmpeg")
    if not ffprobe:
        missing.append("ffprobe")
    if not chrome:
        missing.append("Chrome/Chromium")
    if missing:
        raise VideoDependencyError(
            "Cannot build video — missing: " + ", ".join(missing) + ". "
            "Install ffmpeg (brew install ffmpeg) and Google Chrome. "
            "Chrome can be pointed at explicitly with the EDUAGENT_CHROME env var."
        )

    no_audio = bool(meta.get("no_audio"))
    edge_bin = None if no_audio else find_edge_tts()
    say_bin = None if no_audio else find_say()
    if not no_audio and not edge_bin and not say_bin:
        raise VideoDependencyError(
            "Cannot build narrated video — no text-to-speech engine found. "
            "Install the free neural voice with: pip install edge-tts "
            "(macOS 'say' is used automatically when present)."
        )

    # ── Resolve output + render settings ──────────────────────────────
    out_path = Path(out_path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    aspect = str(meta.get("aspect", "9:16"))
    if meta.get("width") and meta.get("height"):
        width, height = int(meta["width"]), int(meta["height"])
    else:
        width, height = _dims_for_aspect(aspect)
    fps = int(meta.get("fps", 30))
    voice = str(meta.get("voice", "en-US-AndrewMultilingualNeural"))
    edge_rate = str(meta.get("edge_rate", "+8%"))
    say_voice = str(meta.get("say_voice", "Samantha"))
    say_rate = int(meta.get("say_rate", 178))
    brand = str(meta.get("brand", "Claw-ED"))
    tag = str(meta.get("tag", "EDUCATIONAL"))

    logger.info(
        "build_video: %d scenes, %dx%d @ %dfps, audio=%s, tts=%s",
        len(scenes), width, height, fps, not no_audio,
        "edge" if edge_bin else ("say" if say_bin else "none"),
    )

    # Everything intermediate lives in a temp dir; only the final MP4 persists.
    with tempfile.TemporaryDirectory(prefix="clawed_video_") as tmp:
        work = Path(tmp)
        slides_dir = work / "slides"
        audio_dir = work / "audio"
        clips_dir = work / "clips"
        for d in (slides_dir, audio_dir, clips_dir):
            d.mkdir(parents=True, exist_ok=True)

        # Normalise scene ids so filenames are unique & safe.
        for i, sc in enumerate(scenes):
            sc.setdefault("id", f"{i:02d}_scene")

        # 1) Optional image resolution → "art" background per scene.
        if image_resolver is not None:
            for sc in scenes:
                try:
                    img = image_resolver(sc)
                    if img and Path(img).exists():
                        sc["art"] = str(Path(img).resolve())
                except Exception as exc:  # never let image sourcing break a build
                    logger.debug("image_resolver failed for scene %s: %s", sc.get("id"), exc)

        # 2) Render each slide to PNG via Chrome headless.
        png_paths: list[Path] = []
        for i, sc in enumerate(scenes):
            sid = str(sc["id"])
            hp = slides_dir / f"{sid}.html"
            pp = slides_dir / f"{sid}.png"
            hp.write_text(
                _slide_html(sc, i, len(scenes), width, height, brand, tag),
                encoding="utf-8",
            )
            _run([
                chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                "--no-sandbox", "--force-device-scale-factor=1",
                f"--window-size={width},{height}",
                f"--screenshot={pp}", hp.resolve().as_uri(),
            ])
            if not pp.exists() or pp.stat().st_size == 0:
                raise VideoBuildError(f"Chrome did not produce a screenshot for scene {sid}.")
            png_paths.append(pp)

        # 3) Voiceover per scene (or fixed-length silent timing).
        durations: list[float] = []
        wav_paths: list[Path] = []
        if not no_audio:
            for sc in scenes:
                sid = str(sc["id"])
                wav = audio_dir / f"{sid}.wav"
                narr = str(sc.get("narration", "")).strip() or str(sc.get("caption", "")).strip() or " "
                _synthesize_scene_audio(
                    narr, wav, audio_dir, ffmpeg, voice, edge_rate,
                    edge_bin, say_bin, say_voice, say_rate,
                )
                durations.append(_duration_of(ffprobe, wav))
                wav_paths.append(wav)

            # Concatenate the per-scene voice WAVs into one track.
            voice_list = work / "voice_list.txt"
            voice_list.write_text(
                "".join(f"file '{w.as_posix()}'\n" for w in wav_paths),
                encoding="utf-8",
            )
            voice_wav = work / "voice.wav"
            _run([
                ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(voice_list),
                "-c", "copy", str(voice_wav),
            ])
        else:
            durations = [3.0] * len(scenes)

        total = sum(durations)

        # 4) Ken-Burns clip per scene (slow zoom on the still).
        clip_paths: list[Path] = []
        for png, dur, sc in zip(png_paths, durations, scenes, strict=False):
            sid = str(sc["id"])
            clip = clips_dir / f"{sid}.mp4"
            frames = max(2, round(dur * fps))
            z = f"min(1.0+(0.06/{frames})*on,1.06)"
            vf = (
                f"scale={width * 2}:{height * 2},"
                f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={width}x{height}:fps={fps},format=yuv420p"
            )
            _run([
                ffmpeg, "-y", "-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}",
                "-i", str(png), "-vf", vf, "-frames:v", str(frames),
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", str(clip),
            ])
            clip_paths.append(clip)

        # 5) Concat clips → raw silent video.
        clips_list = work / "clips_list.txt"
        clips_list.write_text(
            "".join(f"file '{c.as_posix()}'\n" for c in clip_paths),
            encoding="utf-8",
        )
        raw = work / "video_raw.mp4"
        _run([
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(clips_list),
            "-c", "copy", str(raw),
        ])

        # 6) Mux audio (if any) + global fade from/to black.
        fade_out = max(0.0, total - 0.45)
        vfade = f"fade=t=in:st=0:d=0.35,fade=t=out:st={fade_out:.2f}:d=0.45"
        if not no_audio:
            _run([
                ffmpeg, "-y", "-i", str(raw), "-i", str(voice_wav),
                "-vf", vfade, "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", "-shortest", str(out_path),
            ])
        else:
            _run([
                ffmpeg, "-y", "-i", str(raw), "-vf", vfade,
                "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path),
            ])

    # 7) Verify the finished file.
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise VideoBuildError("Encode finished but the output file is missing or empty.")
    final_dur = _duration_of(ffprobe, out_path)
    logger.info("build_video done: %s (%.2fs, %d KB)", out_path, final_dur, out_path.stat().st_size // 1024)
    return out_path


__all__ = [
    "VideoBuildError",
    "VideoDependencyError",
    "build_video",
    "check_dependencies",
    "find_chrome",
    "find_edge_tts",
    "find_ffmpeg",
    "find_ffprobe",
    "scenes_from_lesson",
]
