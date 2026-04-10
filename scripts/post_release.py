#!/usr/bin/env python3
"""Post EDUagent release notes to X (@uploaded_crab) after every push.

Usage: python3 scripts/post_release.py [commit_message]
If no commit message given, reads from git log.

Follows @openclaw release note format:
  EDUagent 2026.X.XX 🎓
  🔥 Feature 1
  ✅ Feature 2
  github.com/SirhanMacx/eduagent
"""

import subprocess
import sys
from datetime import datetime


def get_last_commit_message() -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        capture_output=True,
        text=True,
        cwd="/Users/mind_uploaded_crustacean/Projects/eduagent",
    )
    return result.stdout.strip()


def get_changed_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "--name-only"],
        capture_output=True,
        text=True,
        cwd="/Users/mind_uploaded_crustacean/Projects/eduagent",
    )
    return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


def format_release_tweet(commit_msg: str, date: str) -> str:
    """Format commit message as OpenClaw-style release tweet."""
    # Parse conventional commit format
    lines = []

    # Extract key changes from commit message
    if "student" in commit_msg.lower():
        lines.append("🎓 Student bot — answers questions in teacher's voice")
    if "mcp" in commit_msg.lower():
        lines.append("🔌 MCP server — callable from any agent")
    if "persona" in commit_msg.lower():
        lines.append("🧠 Teacher persona extraction from curriculum files")
    if "standard" in commit_msg.lower():
        lines.append("📋 50-state standards auto-alignment")
    if "corpus" in commit_msg.lower():
        lines.append("📚 Teaching excellence corpus — shared teacher wisdom")
    if "ollama" in commit_msg.lower() or "minimax" in commit_msg.lower():
        lines.append("🤖 MiniMax M2.7 cloud — generating real lessons")
    if "web" in commit_msg.lower() or "fastapi" in commit_msg.lower():
        lines.append("🌐 Web platform — teacher dashboard + lesson viewer")
    if "stream" in commit_msg.lower():
        lines.append("⚡ Streaming generation — watch lessons appear in real-time")
    if "telegram" in commit_msg.lower() or "openclaw" in commit_msg.lower():
        lines.append("💬 Telegram-native — just talk, no terminal")

    # Fallback: use the commit message directly
    if not lines:
        # Clean up conventional commit prefix
        clean_msg = commit_msg.replace("feat: ", "✅ ").replace("fix: ", "🔧 ").replace("chore: ", "🔨 ")
        lines.append(clean_msg[:80])

    body = "\n".join(lines[:4])  # Max 4 bullet points

    tweet = (
        f"EDUagent {date} 🎓\n\n{body}\n\n"
        f"First AI co-teacher trained on YOUR curriculum.\n\ngithub.com/SirhanMacx/eduagent"
    )

    # Ensure under 280 chars
    if len(tweet) > 276:
        tweet = tweet[:273] + "..."

    return tweet


def post_to_x(tweet: str) -> bool:
    """Post to X using the browser automation approach."""
    try:
        # This would use the browser automation
        # For now, print and return True (manual posting)
        print(f"\nREADY TO POST:\n{'-' * 40}\n{tweet}\n{'-' * 40}")
        print(f"Length: {len(tweet)}/280")
        return True
    except Exception as e:
        print(f"Error posting: {e}")
        return False


if __name__ == "__main__":
    commit_msg = sys.argv[1] if len(sys.argv) > 1 else get_last_commit_message()
    date = datetime.now().strftime("%Y.%-m.%-d")

    tweet = format_release_tweet(commit_msg, date)
    print(tweet)
