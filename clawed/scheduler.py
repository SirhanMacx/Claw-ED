"""APScheduler-based task scheduler for autonomous Claw-ED behavior.

Gives Claw-ED scheduled tasks like Hermes Agent's cron jobs, adapted for teachers:
- morning-prep: review today's classes, auto-generate missing lessons
- weekly-plan: draft next week's lesson plans
- feedback-digest: summarize today's ratings and interactions
- memory-compress: compress old daily notes into memory highlights
- student-digest: summarize student bot interactions for the week

The scheduler is optional -- the app works fine without it running.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Config paths ───────────────────────────────────────────────────────

SCHEDULE_CONFIG_PATH = Path(
    os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
) / "schedule.json"


# ── Built-in task definitions ──────────────────────────────────────────

# Core tasks (morning-prep, weekly-plan, gap-detection) are ENABLED by
# default — teachers can disable via CLI or schedule.json.  Other tasks
# start disabled and can be opted into.
DEFAULT_TASKS: dict[str, dict[str, Any]] = {
    "morning-prep": {
        "description": "Review today's classes. Auto-generate missing lesson drafts and notify via Telegram.",
        "cron": {"hour": "6", "minute": "0"},
        "enabled": True,
    },
    "weekly-plan": {
        "description": "Draft next week's lesson plans based on unit pacing. Send summary via Telegram.",
        "cron": {"day_of_week": "sun", "hour": "19", "minute": "0"},
        "enabled": True,
    },
    "feedback-digest": {
        "description": "Summarize today's ratings and student interactions. Append to daily notes.",
        "cron": {"hour": "20", "minute": "0"},
        "enabled": False,
    },
    "memory-compress": {
        "description": "Compress old daily notes into memory.md highlights using the LLM.",
        "cron": {"day_of_week": "sun", "hour": "5", "minute": "0"},
        "enabled": False,
    },
    "student-digest": {
        "description": "Summarize student bot interactions for the week.",
        "cron": {"day_of_week": "fri", "hour": "16", "minute": "0"},
        "enabled": False,
    },
    "gap-detection": {
        "description": "Scan standards coverage, alert teacher about uncovered standards.",
        "cron": {"day_of_week": "mon", "hour": "7", "minute": "0"},
        "enabled": True,
    },
    "curriculum-watch": {
        "description": "Monitor ingested folders for new/changed files, auto-re-ingest.",
        "cron": {"hour": "5", "minute": "30"},
        "enabled": True,
    },
    "self-distill": {
        "description": "Analyze best/worst outputs, distill improvement rules into soul.md.",
        "cron": {"day_of_week": "sun", "hour": "20", "minute": "0"},
        "enabled": True,
    },
    "dream-cycle": {
        "description": (
            "Overnight brain enrichment — consolidates timeline entries "
            "into compiled truth, detects gaps, cross-links pages. "
            "Makes the brain smarter while the teacher sleeps."
        ),
        "cron": {"hour": "3", "minute": "15"},
        "enabled": True,
    },
}


# ── Schedule config persistence ────────────────────────────────────────


def load_schedule_config() -> dict[str, dict[str, Any]]:
    """Load schedule config from disk, merging with defaults."""
    config = {}
    for name, task_def in DEFAULT_TASKS.items():
        config[name] = {
            "description": task_def["description"],
            "cron": dict(task_def["cron"]),
            "enabled": task_def["enabled"],
        }

    if SCHEDULE_CONFIG_PATH.exists():
        try:
            saved = json.loads(SCHEDULE_CONFIG_PATH.read_text(encoding="utf-8"))
            for name, overrides in saved.items():
                if name in config:
                    if "cron" in overrides:
                        config[name]["cron"] = overrides["cron"]
                    if "enabled" in overrides:
                        config[name]["enabled"] = overrides["enabled"]
                else:
                    # Custom task
                    config[name] = overrides
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load schedule config: %s", exc)

    return config


def save_schedule_config(config: dict[str, dict[str, Any]]) -> None:
    """Persist schedule config to disk."""
    SCHEDULE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def enable_task(name: str) -> bool:
    """Enable a scheduled task. Returns True if the task exists."""
    config = load_schedule_config()
    if name not in config:
        return False
    config[name]["enabled"] = True
    save_schedule_config(config)
    return True


def disable_task(name: str) -> bool:
    """Disable a scheduled task. Returns True if the task exists."""
    config = load_schedule_config()
    if name not in config:
        return False
    config[name]["enabled"] = False
    save_schedule_config(config)
    return True


def set_task_schedule(name: str, cron_expr: str) -> bool:
    """Set a task's cron schedule from a cron expression string.

    Accepts simplified cron: "6:00" (daily at 6am), "sun 19:00", etc.
    Also accepts full cron fields as key=value: "hour=6 minute=0".

    Returns True if the task exists and was updated.
    """
    config = load_schedule_config()
    if name not in config:
        return False

    cron_dict = _parse_cron_expr(cron_expr)
    config[name]["cron"] = cron_dict
    save_schedule_config(config)
    return True


def _parse_cron_expr(expr: str) -> dict[str, str]:
    """Parse a simplified cron expression into APScheduler cron kwargs.

    Formats:
      "6:00"          -> {"hour": "6", "minute": "0"}
      "sun 19:00"     -> {"day_of_week": "sun", "hour": "19", "minute": "0"}
      "hour=6 minute=0" -> {"hour": "6", "minute": "0"}
    """
    expr = expr.strip()

    # Key=value format
    if "=" in expr:
        result = {}
        for part in expr.split():
            if "=" in part:
                k, v = part.split("=", 1)
                result[k.strip()] = v.strip()
        return result

    parts = expr.split()

    # Day of week + time
    days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    if len(parts) == 2 and parts[0].lower() in days:
        day = parts[0].lower()
        time_parts = parts[1].split(":")
        return {
            "day_of_week": day,
            "hour": str(int(time_parts[0])),
            "minute": str(int(time_parts[1])) if len(time_parts) > 1 else "0",
        }

    # Just time
    if ":" in parts[0]:
        time_parts = parts[0].split(":")
        return {
            "hour": str(int(time_parts[0])),
            "minute": str(int(time_parts[1])) if len(time_parts) > 1 else "0",
        }

    return {"hour": expr, "minute": "0"}


# ── Job status tracking (F11 audit fix) ──────────────────────────────

_job_status: dict[str, dict] = {}  # name → {status, last_run, result, error}


def get_job_status() -> dict[str, dict]:
    """Get the status of all scheduler jobs."""
    return dict(_job_status)


def _record_job_start(name: str) -> None:
    from datetime import datetime
    _job_status[name] = {
        "status": "running",
        "last_run": datetime.now().isoformat(),
        "result": None,
        "error": None,
    }


def _record_job_complete(name: str, result: str) -> None:
    if name in _job_status:
        _job_status[name]["status"] = "completed"
        _job_status[name]["result"] = result[:500]


def _record_job_failed(name: str, error: str) -> None:
    if name in _job_status:
        _job_status[name]["status"] = "failed"
        _job_status[name]["error"] = error[:500]


# ── Task implementations ────────────────────────────────────────────


async def _task_morning_prep() -> str:
    """Morning prep: check for missing lessons, auto-generate drafts.

    Scans the current unit for lessons that haven't been generated yet.
    If any are missing, auto-generates them using the teacher's persona
    and notifies via Telegram.
    """
    _record_job_start("morning-prep")
    from clawed.workspace import append_daily_note

    append_daily_note("Morning prep task started.", category="scheduler")

    try:
        from clawed.agent_core.identity import get_teacher_id
        from clawed.models import AppConfig, TeacherPersona
        from clawed.state import TeacherSession

        teacher_id = get_teacher_id()
        session = TeacherSession.load(teacher_id)
        config = AppConfig.load()
        persona = session.persona or TeacherPersona()

        # Check if there's a current unit with ungenerated lessons
        if not session.current_unit:
            summary = "Morning prep: no active unit. Start a unit with 'plan a unit on [topic]'."
            append_daily_note(summary, category="morning-prep")
            return summary

        unit = session.current_unit
        generated_ids = set(session.config.get("generated_lesson_ids", []))
        missing = [
            b for b in unit.daily_lessons
            if b.lesson_number not in generated_ids
        ]

        if not missing:
            summary = (
                f"Morning prep: all {len(unit.daily_lessons)} lessons in "
                f"'{unit.title}' are generated. You're set!"
            )
            append_daily_note(summary, category="morning-prep")
            return summary

        # Auto-generate the NEXT missing lesson (not all at once)
        next_brief = missing[0]
        from clawed.lesson import generate_lesson as _gen

        lesson = await _gen(
            lesson_number=next_brief.lesson_number,
            unit=unit,
            persona=persona,
            config=config,
        )
        session.save_lesson(lesson)
        generated_ids.add(next_brief.lesson_number)
        session.config["generated_lesson_ids"] = list(generated_ids)
        session.save()

        summary = (
            f"Morning prep: auto-generated lesson {next_brief.lesson_number} "
            f"'{next_brief.topic}' for unit '{unit.title}'. "
            f"{len(missing) - 1} lessons still pending."
        )

        # Notify via Telegram if bot is configured
        try:
            from clawed.transports.telegram import send_notification
            send_notification(
                f"\U0001f305 Good morning! I generated today's lesson:\n"
                f"Lesson {next_brief.lesson_number}: {next_brief.topic}\n\n"
                f"Reply 'show lesson {next_brief.lesson_number}' to review it."
            )
        except Exception:
            pass  # Telegram not configured — that's fine

    except Exception as exc:
        summary = f"Morning prep failed: {exc}"
        logger.exception("morning-prep task error")

    append_daily_note(summary, category="morning-prep")
    logger.info("morning-prep: %s", summary)
    if "failed" in summary.lower():
        _record_job_failed("morning-prep", summary)
    else:
        _record_job_complete("morning-prep", summary)
    return summary


async def _task_weekly_plan() -> str:
    """Weekly plan: draft next week's lessons from the current unit.

    Generates up to 5 lessons for the next week using the current unit's
    lesson briefs. Saves each lesson to the session and notifies the teacher.
    """
    from clawed.workspace import append_daily_note

    append_daily_note("Weekly plan task started.", category="scheduler")

    try:
        from clawed.agent_core.identity import get_teacher_id
        from clawed.models import AppConfig, TeacherPersona
        from clawed.state import TeacherSession

        teacher_id = get_teacher_id()
        session = TeacherSession.load(teacher_id)
        config = AppConfig.load()
        persona = session.persona or TeacherPersona()

        if not session.current_unit:
            summary = "Weekly plan: no active unit to plan from."
            append_daily_note(summary, category="weekly-plan")
            return summary

        unit = session.current_unit
        generated_ids = set(session.config.get("generated_lesson_ids", []))
        missing = [
            b for b in unit.daily_lessons
            if b.lesson_number not in generated_ids
        ]

        # Generate up to 5 lessons for next week
        to_generate = missing[:5]
        if not to_generate:
            summary = f"Weekly plan: all lessons in '{unit.title}' already generated!"
            append_daily_note(summary, category="weekly-plan")
            return summary

        from clawed.lesson import generate_lesson as _gen

        generated_count = 0
        for brief in to_generate:
            try:
                lesson = await _gen(
                    lesson_number=brief.lesson_number,
                    unit=unit,
                    persona=persona,
                    config=config,
                )
                session.save_lesson(lesson)
                generated_ids.add(brief.lesson_number)
                generated_count += 1
            except Exception as exc:
                logger.warning(
                    "Weekly plan: failed to generate lesson %d: %s",
                    brief.lesson_number, exc,
                )

        session.config["generated_lesson_ids"] = list(generated_ids)
        session.save()

        remaining = len(missing) - generated_count
        summary = (
            f"Weekly plan: generated {generated_count} lessons for "
            f"'{unit.title}'. {remaining} lessons remaining in unit."
        )

        try:
            from clawed.transports.telegram import send_notification
            topics = ", ".join(b.topic for b in to_generate[:generated_count])
            send_notification(
                f"\U0001f4c5 Weekly plan ready!\n"
                f"Generated {generated_count} lessons:\n{topics}\n\n"
                f"Reply 'show lesson 1' to start reviewing."
            )
        except Exception:
            pass

    except Exception as exc:
        summary = f"Weekly plan failed: {exc}"
        logger.exception("weekly-plan task error")

    append_daily_note(summary, category="weekly-plan")
    logger.info("weekly-plan: %s", summary)
    return summary


async def _task_feedback_digest() -> str:
    """Feedback digest: summarize today's ratings and update the memory engine."""
    from clawed.workspace import append_daily_note

    try:
        from clawed.database import Database
        from clawed.feedback import analyze_feedback

        db = Database()
        analysis = analyze_feedback(db, days=1)
        db.close()

        total = analysis.get("total_feedback", 0)
        avg = analysis.get("avg_rating", 0.0)
        summary = f"Feedback digest: {total} ratings today, avg {avg}/5."
    except Exception as exc:
        summary = f"Feedback digest: could not analyze ({exc})"

    # Update memory engine stats
    try:
        from clawed.memory_engine import get_improvement_stats

        stats = get_improvement_stats()
        if stats["total_rated"] > 0:
            summary += (
                f" Memory engine: {stats['total_patterns']} patterns learned, "
                f"avg {stats['avg_rating']}/5, trend: {stats['trend']}."
            )
    except Exception as exc:
        logger.debug("Memory engine stats failed: %s", exc)

    append_daily_note(summary, category="feedback-digest")
    logger.info("feedback-digest: %s", summary)
    return summary


async def _task_memory_compress() -> str:
    """Memory compress: summarize old notes into memory highlights."""
    from clawed.workspace import NOTES_DIR, append_daily_note

    # Count old notes files
    note_files = sorted(NOTES_DIR.glob("*.md")) if NOTES_DIR.exists() else []
    old_count = max(0, len(note_files) - 7)  # Keep last 7 days
    summary = f"Memory compress: {len(note_files)} note files, {old_count} eligible for compression (stub)."
    append_daily_note(summary, category="memory-compress")
    logger.info("memory-compress: %s", summary)
    return summary


async def _task_student_digest() -> str:
    """Student digest: summarize student interactions for the week."""
    from clawed.workspace import append_daily_note

    try:
        from clawed.state import _get_conn, init_db

        init_db()
        with _get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) as c FROM student_questions").fetchone()
            q_count = row["c"] if row else 0
        summary = f"Student digest: {q_count} total student questions in database."
    except Exception as exc:
        summary = f"Student digest: could not query ({exc})"

    append_daily_note(summary, category="student-digest")
    logger.info("student-digest: %s", summary)
    return summary


async def _task_gap_detection() -> str:
    """Scan standards coverage and identify gaps."""
    from clawed.workspace import append_daily_note

    try:
        from clawed.agent_core.identity import get_teacher_id
        from clawed.state import TeacherSession

        teacher_id = get_teacher_id()
        session = TeacherSession.load(teacher_id)
        recent_units = session.get_recent_units(limit=20)

        if not recent_units:
            summary = "Gap detection: no units generated yet — nothing to scan."
            append_daily_note(summary, category="gap-detection")
            return summary

        # Collect covered topics
        topics = [u.get("topic", "") for u in recent_units if u.get("topic")]
        subjects = set(u.get("subject", "") for u in recent_units if u.get("subject"))

        summary = (
            f"Gap detection: scanned {len(recent_units)} units across "
            f"{', '.join(subjects) or 'unknown subjects'}. "
            f"Topics covered: {', '.join(topics[:10])}."
        )
        if len(recent_units) < 5:
            summary += " Coverage is sparse — more units needed for meaningful gap analysis."

    except Exception as exc:
        summary = f"Gap detection: scan failed ({exc})"

    append_daily_note(summary, category="gap-detection")
    logger.info("gap-detection: %s", summary)
    return summary


async def _task_curriculum_watch() -> str:
    """Monitor ingested folders for changes and re-ingest."""
    from clawed.workspace import append_daily_note

    try:
        from clawed.agent_core.identity import get_teacher_id
        from clawed.models import AppConfig

        _tid = get_teacher_id()  # noqa: F841 — reserved for future per-teacher watch
        config = AppConfig.load()
        materials_paths = getattr(config.teacher_profile, "materials_paths", [])

        if not materials_paths:
            summary = "Curriculum watch: no materials paths configured."
            append_daily_note(summary, category="curriculum-watch")
            return summary

        import os
        from pathlib import Path

        new_files = []
        for path_str in materials_paths:
            path = Path(path_str).expanduser()
            if not path.exists():
                continue
            # Check for files modified in the last 24 hours
            cutoff = os.path.getmtime(str(path)) if path.is_file() else 0
            if path.is_dir():
                for f in path.rglob("*"):
                    if f.is_file() and f.suffix.lower() in {".pdf", ".docx", ".pptx", ".txt", ".md"}:
                        try:
                            if os.path.getmtime(str(f)) > (cutoff - 86400):
                                new_files.append(f)
                        except OSError:
                            continue

        if new_files:
            summary = f"Curriculum watch: found {len(new_files)} recently modified files. Auto-re-ingest recommended."
        else:
            summary = "Curriculum watch: no changes detected in materials folders."

    except Exception as exc:
        summary = f"Curriculum watch: check failed ({exc})"

    append_daily_note(summary, category="curriculum-watch")
    logger.info("curriculum-watch: %s", summary)
    return summary


# Map task names to their async implementations
TASK_IMPLEMENTATIONS: dict[str, Callable[[], Any]] = {
    "morning-prep": _task_morning_prep,
    "weekly-plan": _task_weekly_plan,
    "feedback-digest": _task_feedback_digest,
    "memory-compress": _task_memory_compress,
    "student-digest": _task_student_digest,
    "gap-detection": _task_gap_detection,
    "curriculum-watch": _task_curriculum_watch,
}


async def _task_self_distill() -> str:
    """Self-distillation: analyze outputs, improve soul.md."""
    from clawed.workspace import append_daily_note

    try:
        from clawed.agent_core.identity import get_teacher_id
        from clawed.agent_core.quality import self_distill

        teacher_id = get_teacher_id()
        result = self_distill(teacher_id)

        if result:
            summary = (
                f"Self-distillation: analyzed outputs, "
                f"distilled {result.count(chr(10))} insights into soul.md"
            )
        else:
            summary = "Self-distillation: not enough data yet"

    except Exception as exc:
        summary = f"Self-distillation failed: {exc}"

    append_daily_note(summary, category="self-distill")
    logger.info("self-distill: %s", summary)
    return summary


TASK_IMPLEMENTATIONS["self-distill"] = _task_self_distill


async def _task_dream_cycle() -> str:
    """Run the overnight brain enrichment cycle."""
    from clawed.workspace import append_daily_note

    try:
        from clawed.brain.dream import dream_cycle
        report = await dream_cycle(consolidate=True, dry_run=False)
        summary = (
            f"Dream cycle: scanned {report.pages_scanned} pages, "
            f"consolidated {report.pages_consolidated}, "
            f"added {report.cross_links_added} cross-links"
        )
        if report.gaps_detected:
            summary += f" ({len(report.gaps_detected)} gaps flagged)"
        if report.errors:
            summary += f" ({len(report.errors)} errors)"
    except Exception as exc:
        summary = f"Dream cycle failed: {exc}"

    append_daily_note(summary, category="dream-cycle")
    logger.info("dream-cycle: %s", summary)
    return summary


TASK_IMPLEMENTATIONS["dream-cycle"] = _task_dream_cycle


# ── Manual run ─────────────────────────────────────────────────────────


async def run_task(name: str) -> str:
    """Run a task immediately by name. Returns the task's summary string."""
    config = load_schedule_config()
    if name not in config:
        raise ValueError(f"Unknown task: {name}. Available: {', '.join(config.keys())}")

    impl = TASK_IMPLEMENTATIONS.get(name)
    if impl is None:
        raise ValueError(f"No implementation for task: {name}")

    from clawed.workspace import append_daily_note

    append_daily_note(f"Manual run of '{name}' started.", category="scheduler")
    result = await impl()
    return result


# ── Scheduler class ────────────────────────────────────────────────────


class EduScheduler:
    """APScheduler-based task scheduler for Claw-ED.

    Uses AsyncIOScheduler with CronTrigger for scheduled tasks.
    The scheduler is entirely optional and does not block normal usage.
    """

    def __init__(self) -> None:
        self._scheduler = None
        self._config = load_schedule_config()

    def _get_scheduler(self):
        """Lazy-init the APScheduler instance."""
        if self._scheduler is None:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            self._scheduler = AsyncIOScheduler()
        return self._scheduler

    def register_jobs(self) -> None:
        """Register all enabled tasks as APScheduler jobs."""
        from apscheduler.triggers.cron import CronTrigger

        scheduler = self._get_scheduler()

        for name, task_cfg in self._config.items():
            if not task_cfg.get("enabled", False):
                continue

            impl = TASK_IMPLEMENTATIONS.get(name)
            if impl is None:
                logger.warning("No implementation for task '%s', skipping.", name)
                continue

            cron_kwargs = task_cfg.get("cron", {})
            trigger = CronTrigger(**cron_kwargs)

            scheduler.add_job(
                impl,
                trigger=trigger,
                id=name,
                name=name,
                replace_existing=True,
            )
            logger.info("Registered task '%s' with cron %s", name, cron_kwargs)

    def start(self) -> None:
        """Start the scheduler (call from within a running event loop)."""
        scheduler = self._get_scheduler()
        self.register_jobs()
        scheduler.start()
        logger.info("Claw-ED scheduler started with %d job(s).", len(scheduler.get_jobs()))

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Claw-ED scheduler stopped.")

    def get_jobs_info(self) -> list[dict[str, Any]]:
        """Return info about all configured tasks (enabled or not)."""
        info: list[dict[str, Any]] = []
        scheduler = self._get_scheduler() if self._scheduler else None

        for name, task_cfg in self._config.items():
            entry: dict[str, Any] = {
                "name": name,
                "description": task_cfg.get("description", ""),
                "cron": task_cfg.get("cron", {}),
                "enabled": task_cfg.get("enabled", False),
                "next_run": None,
            }

            # Get next run time from APScheduler if running
            if scheduler and scheduler.running:
                job = scheduler.get_job(name)
                if job and job.next_run_time:
                    entry["next_run"] = job.next_run_time.isoformat()

            info.append(entry)

        return info

    @property
    def running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running
