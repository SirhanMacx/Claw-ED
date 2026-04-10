"""Voice note transcription — teachers and students can send audio.

Uses faster-whisper for local transcription. Falls back to the whisper CLI
if faster-whisper is not installed.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

AUDIO_EXTENSIONS = {".ogg", ".wav", ".mp3", ".m4a", ".flac", ".webm", ".opus"}


def is_audio_file(path: str | Path) -> bool:
    """Return True if *path* looks like an audio file we can transcribe."""
    return Path(path).suffix.lower() in AUDIO_EXTENSIONS


async def transcribe_audio(audio_path: Path) -> str:
    """Transcribe an audio file to text.

    Tries faster-whisper first (Python library, GPU-accelerated).
    Falls back to the ``whisper`` CLI if faster-whisper is unavailable.

    Args:
        audio_path: Path to the audio file (ogg/wav/mp3/m4a/flac/webm/opus).

    Returns:
        Transcribed text.

    Raises:
        FileNotFoundError: If the audio file does not exist.
        RuntimeError: If no transcription backend is available.
    """
    audio_path = Path(audio_path).expanduser().resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if audio_path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError(f"Unsupported audio format: {audio_path.suffix}")

    # Try faster-whisper first
    if WhisperModel is not None:
        return await _transcribe_faster_whisper(audio_path)

    # Fall back to whisper CLI
    if shutil.which("whisper"):
        return await _transcribe_whisper_cli(audio_path)

    raise RuntimeError("Voice transcription requires faster-whisper.\nInstall it with: pip install 'clawed[voice]'")


async def _transcribe_faster_whisper(audio_path: Path) -> str:
    """Transcribe using the faster-whisper Python library."""
    if WhisperModel is None:
        raise RuntimeError("Voice transcription requires faster-whisper.\nInstall it with: pip install 'clawed[voice]'")

    loop = asyncio.get_event_loop()

    def _run() -> str:
        model = WhisperModel("base", device="auto", compute_type="int8")
        segments, _info = model.transcribe(str(audio_path), beam_size=5)
        return " ".join(seg.text.strip() for seg in segments).strip()

    return await loop.run_in_executor(None, _run)


async def _transcribe_whisper_cli(audio_path: Path) -> str:
    """Transcribe using the whisper CLI (openai-whisper package)."""
    proc = await asyncio.create_subprocess_exec(
        "whisper",
        str(audio_path),
        "--model",
        "base",
        "--output_format",
        "txt",
        "--output_dir",
        str(audio_path.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"whisper CLI failed: {stderr.decode()[:500]}")

    # whisper writes <stem>.txt next to the audio file
    txt_path = audio_path.with_suffix(".txt")
    if txt_path.exists():
        text = txt_path.read_text(encoding="utf-8").strip()
        txt_path.unlink()  # clean up
        return text

    raise RuntimeError("whisper CLI did not produce output file")
