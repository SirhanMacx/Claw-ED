#!/usr/bin/env python3
"""
Jon's curriculum ingestion script.
Connects to Sirhan over SSH, samples files from each course,
copies them locally, then runs EDUagent persona extraction.

Usage:
  python3 scripts/ingest_jon.py --sample   # Quick sample (300 files, ~20 min)
  python3 scripts/ingest_jon.py --full     # Full ingestion (23K files, background)
"""

import argparse
import subprocess
import sys
from pathlib import Path

SIRHAN_HOST = "sirhan"
CURRICULA_BASE = "/Volumes/MAC2025/Curricula"
LOCAL_CACHE = Path.home() / ".eduagent" / "jon_curriculum_cache"

# Courses and how many files to sample (prioritize lesson plan-heavy courses)
SAMPLE_STRATEGY = {
    "9th global1": 40,
    "10th Global II": 40,
    "11th Grade US": 40,
    "APUSH": 30,
    "AP U.S. Government and Politics": 30,
    "7th us history 1": 25,
    "Economics": 20,
    "Criminal Justice": 20,
    "Participation in Government ": 20,
    "Pre AP World": 30,
}


def run_ssh(cmd: str) -> str:
    result = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=30", SIRHAN_HOST, cmd], capture_output=True, text=True, timeout=60
    )
    return result.stdout.strip()


def copy_files(remote_dir: str, local_dir: Path, max_files: int = 30) -> list[Path]:
    """Copy up to max_files from remote_dir to local_dir."""
    local_dir.mkdir(parents=True, exist_ok=True)

    # Get file list via SSH
    file_list_cmd = (
        f'find "{remote_dir}" -maxdepth 3 -type f'
        f' \\( -name "*.pdf" -o -name "*.docx" -o -name "*.pptx" -o -name "*.txt" \\)'
        f" 2>/dev/null | head -n {max_files}"
    )
    output = run_ssh(file_list_cmd)

    if not output:
        return []

    files = [f.strip() for f in output.split("\n") if f.strip()]
    copied = []

    for i, remote_file in enumerate(files[:max_files]):
        filename = Path(remote_file).name
        local_path = local_dir / filename
        if local_path.exists():
            copied.append(local_path)
            continue
        # SCP the file
        result = subprocess.run(
            ["scp", "-q", f"{SIRHAN_HOST}:{remote_file}", str(local_path)], capture_output=True, timeout=30
        )
        if result.returncode == 0:
            copied.append(local_path)
        if (i + 1) % 10 == 0:
            print(f"  Copied {i + 1}/{len(files)} files...", flush=True)

    return copied


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true", help="Quick sample (~300 files)")
    parser.add_argument("--full", action="store_true", help="Full ingestion (background)")
    parser.add_argument("--extract-only", action="store_true", help="Run persona extraction on cached files")
    args = parser.parse_args()

    if args.extract_only:
        print("Running persona extraction on cached files...")
        _run_extraction()
        return

    print("🎓 Jon's Curriculum Ingestion")
    print(f"   Source: {SIRHAN_HOST}:{CURRICULA_BASE}")
    print(f"   Cache: {LOCAL_CACHE}")
    print()

    all_copied = []

    if args.sample or (not args.full):
        print("📚 Sampling files from each course...")
        for course, count in SAMPLE_STRATEGY.items():
            remote_dir = f"{CURRICULA_BASE}/{course}"
            local_dir = LOCAL_CACHE / course.replace(" ", "_").replace("/", "_")
            print(f"  {course}: fetching {count} files...", flush=True)
            copied = copy_files(remote_dir, local_dir, max_files=count)
            all_copied.extend(copied)
            print(f"    → Got {len(copied)} files")

        print(f"\n✅ Sample complete: {len(all_copied)} files cached at {LOCAL_CACHE}")

    elif args.full:
        print("⚠️  Full ingestion: this will copy ~23K files. Starting in background.")
        # Just copy everything
        result = subprocess.Popen(
            [
                "rsync",
                "-av",
                "--progress",
                f"{SIRHAN_HOST}:{CURRICULA_BASE}/",
                str(LOCAL_CACHE),
                "--include=*.pdf",
                "--include=*.docx",
                "--include=*.pptx",
                "--include=*.txt",
                "--include=*/",
                "--exclude=*",
            ]
        )
        print(f"Rsync PID: {result.pid}. Running in background.")
        print("Monitor: ps aux | grep rsync")
        return

    # Run persona extraction on what we have
    print("\n🧠 Running persona extraction...")
    _run_extraction()


def _run_extraction():
    """Run eduagent persona extraction on the cached files."""
    if not LOCAL_CACHE.exists():
        print(f"No cached files found at {LOCAL_CACHE}")
        print("Run with --sample first.")
        return

    # Count files
    files = list(LOCAL_CACHE.rglob("*.pdf")) + list(LOCAL_CACHE.rglob("*.docx")) + list(LOCAL_CACHE.rglob("*.pptx"))
    print(f"Found {len(files)} cached files")

    # Run eduagent ingest
    result = subprocess.run(
        [sys.executable, "-m", "eduagent.cli", "ingest", str(LOCAL_CACHE)],
        cwd=Path(__file__).parent.parent,
        capture_output=False,
    )

    if result.returncode == 0:
        print("\n✅ Jon's persona extracted successfully!")
        print("Run 'eduagent persona show' to see the result.")
    else:
        print(f"\n❌ Extraction failed (code {result.returncode})")


if __name__ == "__main__":
    main()
