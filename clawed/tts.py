"""Text-to-speech narration for slide presentations.

Generates MP3 audio files from slide content so teachers can create
narrated presentations without recording their own voice.

Engine preference (all free, no paid API):
  1. **edge-tts** — Microsoft's free neural voices (natural-sounding;
     needs network, no key). Preferred when available.
  2. **gTTS** — Google Translate TTS (free, no key; more robotic).
  3. **macOS ``say``** — offline system voice fallback.

The public functions keep their original signatures; the neural path is
opportunistic and degrades gracefully.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Default free neural voice for edge-tts (clear US-English narrator).
DEFAULT_EDGE_VOICE = "en-US-AndrewMultilingualNeural"


def _find_edge_tts() -> str | None:
    """Locate the ``edge-tts`` CLI on PATH or in ~/.local/bin."""
    found = shutil.which("edge-tts")
    if found:
        return found
    for env in ("EDUAGENT_EDGE_TTS", "EDGE_TTS"):
        val = os.environ.get(env)
        if val and os.path.isfile(val) and os.access(val, os.X_OK):
            return val
    user_bin = Path.home() / ".local" / "bin" / "edge-tts"
    if user_bin.is_file() and os.access(user_bin, os.X_OK):
        return str(user_bin)
    return None


def _synthesize_edge(
    text: str,
    output_path: Path,
    voice: str = DEFAULT_EDGE_VOICE,
    rate: str = "+0%",
) -> Path | None:
    """Generate MP3 via edge-tts neural voices. Returns None if unavailable.

    edge-tts is the Python module form of Microsoft's free neural TTS. We
    try the module first (so it works regardless of console-script PATH),
    then the CLI. Any failure returns None so callers fall back.
    """
    # Preferred: invoke the installed module directly.
    try:
        import edge_tts  # type: ignore[import-not-found]  # noqa: F401

        result = subprocess.run(
            [sys.executable, "-m", "edge_tts", "--voice", voice,
             f"--rate={rate}", "--text", text, "--write-media", str(output_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            logger.info("Narration saved (edge-tts neural): %s (%d chars)", output_path.name, len(text))
            return output_path
        logger.debug("edge-tts module run failed: %s", (result.stderr or "")[-300:])
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("edge-tts module path errored: %s", exc)

    # Fallback: the console script if it's on PATH.
    edge_bin = _find_edge_tts()
    if edge_bin:
        try:
            result = subprocess.run(
                [edge_bin, "--voice", voice, f"--rate={rate}",
                 "--text", text, "--write-media", str(output_path)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                logger.info("Narration saved (edge-tts CLI): %s (%d chars)", output_path.name, len(text))
                return output_path
            logger.debug("edge-tts CLI failed: %s", (result.stderr or "")[-300:])
        except Exception as exc:
            logger.debug("edge-tts CLI errored: %s", exc)

    return None


def _synthesize_gtts(text: str, output_path: Path, lang: str = "en") -> Path:
    """Generate MP3 from text using gTTS (raises ImportError if missing)."""
    try:
        from gtts import gTTS
    except ImportError:
        logger.warning("gTTS not installed. Run: pip install gTTS")
        raise

    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(str(output_path))
    logger.info("Narration saved (gTTS): %s (%d chars)", output_path.name, len(text))
    return output_path


def _synthesize_say(text: str, output_path: Path) -> Path | None:
    """Generate audio via the macOS ``say`` command. Returns None if absent.

    ``say`` writes AIFF; the file is saved with a ``.aiff`` sibling and that
    path is returned (callers that need MP3 should prefer the other engines).
    """
    say_bin = shutil.which("say")
    if not say_bin:
        return None
    aiff_path = output_path.with_suffix(".aiff")
    try:
        result = subprocess.run(
            [say_bin, "-o", str(aiff_path), text],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and aiff_path.exists() and aiff_path.stat().st_size > 0:
            logger.info("Narration saved (macOS say): %s (%d chars)", aiff_path.name, len(text))
            return aiff_path
    except Exception as exc:
        logger.debug("macOS say errored: %s", exc)
    return None


def synthesize_text(
    text: str,
    output_path: Path,
    lang: str = "en",
    voice: str = DEFAULT_EDGE_VOICE,
    prefer_neural: bool = True,
) -> Path:
    """Generate narration audio from text.

    Prefers the free **edge-tts** neural voice for natural-sounding output,
    then falls back to **gTTS**, then macOS **say**. Returns the path to the
    written audio (the requested ``output_path`` for edge-tts/gTTS; a
    ``.aiff`` sibling when only ``say`` is available).

    The signature is backward compatible — existing callers passing only
    ``(text, output_path)`` (and optionally ``lang``) keep working, now with
    a better default voice.
    """
    output_path = Path(output_path)

    # 1) Preferred: edge-tts neural.
    if prefer_neural:
        neural = _synthesize_edge(text, output_path, voice=voice)
        if neural is not None:
            return neural

    # 2) Fallback: gTTS (free, no key).
    try:
        return _synthesize_gtts(text, output_path, lang=lang)
    except Exception as exc:
        logger.debug("gTTS unavailable (%s); trying macOS say", exc)

    # 3) Last resort: macOS say.
    said = _synthesize_say(text, output_path)
    if said is not None:
        return said

    # Nothing worked — raise so callers can report honestly.
    raise RuntimeError(
        "No TTS engine available. Install a free one: pip install edge-tts "
        "(neural) or pip install gTTS, or run on macOS for the 'say' fallback."
    )


def narrate_slides(pptx_path: Path, slide_texts: list[str]) -> list[Path]:
    """Generate MP3 narration for each slide.

    Args:
        pptx_path: Path to the PPTX file (MP3s saved alongside it)
        slide_texts: List of narration text for each slide

    Returns:
        List of MP3 file paths
    """
    narration_dir = pptx_path.parent / f"{pptx_path.stem}_narration"
    narration_dir.mkdir(parents=True, exist_ok=True)

    mp3_paths = []
    for i, text in enumerate(slide_texts, 1):
        if not text or not text.strip():
            continue
        mp3_path = narration_dir / f"slide_{i:02d}.mp3"
        try:
            synthesize_text(text, mp3_path)
            mp3_paths.append(mp3_path)
        except Exception as e:
            logger.warning("Failed to narrate slide %d: %s", i, e)

    if mp3_paths:
        logger.info("Generated %d narration files in %s", len(mp3_paths), narration_dir)

    return mp3_paths
