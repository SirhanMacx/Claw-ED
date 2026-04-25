"""Thin Telegram transport — delegates all logic to the Gateway.

Uses urllib3 directly for reliable cross-platform compatibility.
The bot is a ~200-line polling loop that:
  1. Receives updates from Telegram
  2. Delegates to Gateway.handle() / Gateway.handle_callback()
  3. Renders GatewayResponse back to Telegram

Usage:
    from clawed.transports.telegram import EduAgentTelegramBot
    bot = EduAgentTelegramBot(token="YOUR_TOKEN")
    bot.run()
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, cast

import urllib3
from urllib3.exceptions import HTTPError

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org"
_MAX_MESSAGE_LENGTH = 4096
_HTTP = urllib3.PoolManager()

# Base data directory — respects EDUAGENT_DATA_DIR env override
_BASE = Path(os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))

# Lock file for preventing multiple bot instances
_BOT_LOCK = _BASE / "bot.lock"

# Error log path
_ERROR_LOG = _BASE / "errors.log"


def _timeout(read_timeout: float) -> urllib3.Timeout:
    """Build a conservative timeout for Telegram API calls."""
    return urllib3.Timeout(connect=min(10.0, read_timeout), read=read_timeout)


def _decode_response(data: bytes) -> tuple[dict[str, Any], str]:
    text = data.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}, text
    if isinstance(parsed, dict):
        return cast(dict[str, Any], parsed), text
    return {}, text


def _post_json(
    http: urllib3.PoolManager,
    url: str,
    payload: dict[str, Any],
    timeout: float,
) -> tuple[int, dict[str, Any], str]:
    resp = http.request(
        "POST",
        url,
        body=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=_timeout(timeout),
    )
    parsed, text = _decode_response(resp.data)
    return resp.status, parsed, text


def _log_error(error: Exception) -> None:
    """Append error to the errors.log file."""
    try:
        _ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_ERROR_LOG, "a") as f:
            import datetime
            f.write(
                f"[{datetime.datetime.now(datetime.UTC).isoformat()}] "
                f"{type(error).__name__}: {error}\n"
            )
    except (FileNotFoundError, OSError):
        pass


def _is_clawed_process(pid: int) -> bool:
    """Check if a PID is actually a running clawed/python process (not just any process)."""
    import sys

    try:
        if sys.platform == "win32":
            import subprocess
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            output = result.stdout.lower()
            return "python" in output or "clawed" in output
        else:
            # Unix: check /proc or ps
            os.kill(pid, 0)  # Raises OSError if process doesn't exist
            try:
                import subprocess
                result = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "comm="],
                    capture_output=True, text=True, timeout=5,
                )
                output = result.stdout.lower()
                return "python" in output or "clawed" in output
            except ImportError:
                return True  # Can't check command name, assume it's ours
    except (OSError, SystemError):
        return False  # Process doesn't exist


def kill_bot_process() -> bool:
    """Find and kill any existing clawed bot process. Returns True if a process was killed."""
    import sys

    if not _BOT_LOCK.exists():
        return False

    try:
        pid = int(_BOT_LOCK.read_text(encoding="utf-8").strip())
        if pid == os.getpid():
            return False
        if not _is_clawed_process(pid):
            _BOT_LOCK.unlink(missing_ok=True)
            return False

        # Kill the process
        if sys.platform == "win32":
            import subprocess
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=10)
        else:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass  # Already dead

        _BOT_LOCK.unlink(missing_ok=True)
        return True
    except (FileNotFoundError, OSError):
        _BOT_LOCK.unlink(missing_ok=True)
        return False


def _check_bot_lock(force: bool = False) -> None:
    """Check if another bot instance is running."""
    if _BOT_LOCK.exists():
        try:
            pid = int(_BOT_LOCK.read_text(encoding="utf-8").strip())
            if pid != os.getpid():
                if _is_clawed_process(pid):
                    if not force:
                        raise RuntimeError(
                            f"Another bot instance is already running (PID {pid}). "
                            f"Stop it first, use --force, or use 'clawed bot --kill'."
                        )
                    logger.warning("Force-killing existing bot (PID %d)", pid)
                    kill_bot_process()
                else:
                    logger.info("Removing stale bot lock (PID %d is not a clawed process)", pid)
        except (ValueError, OSError, SystemError):
            logger.info("Removing invalid bot lock file")

    _BOT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    _BOT_LOCK.write_text(str(os.getpid()), encoding="utf-8")


def _release_bot_lock() -> None:
    """Remove the lock file on shutdown."""
    try:
        if _BOT_LOCK.exists():
            pid = int(_BOT_LOCK.read_text(encoding="utf-8").strip())
            if pid == os.getpid():
                _BOT_LOCK.unlink()
    except (FileNotFoundError, OSError):
        pass


class TelegramAPI:
    """Thin sync wrapper around the Telegram Bot API using urllib3.

    Uses urllib3 instead of httpx for Windows TLS
    compatibility. httpx fails with WinError 10054 on every TLS
    handshake to api.telegram.org on certain Windows machines.
    """

    def __init__(self, token: str, timeout: float = 60.0):
        self.token = token
        self._base = f"{_API_BASE}/bot{token}"
        self._timeout = timeout
        self._http = urllib3.PoolManager()

    def close(self) -> None:
        self._http.clear()

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        timeout: float | None = None,
    ) -> tuple[int, dict[str, Any], str]:
        return _post_json(self._http, url, payload, timeout or self._timeout)

    def _post_multipart(
        self,
        url: str,
        fields: dict[str, Any],
        timeout: float,
    ) -> tuple[int, dict[str, Any], str]:
        resp = self._http.request(
            "POST",
            url,
            fields=fields,
            timeout=_timeout(timeout),
        )
        parsed, text = _decode_response(resp.data)
        return resp.status, parsed, text

    def _call(self, method: str, **params: Any) -> Any:
        """Call a Telegram Bot API method with retry on network errors.

        Returns the raw `result` payload from Telegram — typically a dict,
        but some endpoints (e.g. getUpdates) return a list.
        """
        url = f"{self._base}/{method}"
        data = {k: v for k, v in params.items() if v is not None}

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                status, result, text = self._post_json(url, data)
                if status >= 500:
                    raise RuntimeError(f"Telegram HTTP {status}: {text[:200]}")
                if result.get("ok"):
                    return result.get("result", {})
                raise RuntimeError(
                    f"Telegram API error: "
                    f"{result.get('description', 'Unknown error')}"
                )
            except (
                HTTPError,
                ConnectionResetError,
            ) as e:
                last_err = e
                wait = 2 ** attempt
                logger.warning(
                    "Network error on attempt %d: %s. Retrying in %ds...",
                    attempt + 1, e, wait,
                )
                time.sleep(wait)
            except Exception as e:
                logger.error("Unexpected error calling %s: %s", method, e)
                _log_error(e)
                return {}

        if last_err:
            logger.error("Failed after 3 retries: %s", last_err)
            _log_error(last_err)
        return {}

    def get_me(self) -> dict[str, Any]:
        result = self._call("getMe")
        return result if isinstance(result, dict) else {}

    def get_updates(self, offset: int = 0, timeout: int = 30) -> list[dict[str, Any]]:
        """Long-poll for updates."""
        result = self._call(
            "getUpdates", offset=offset, timeout=timeout,
        )
        return result if isinstance(result, list) else []

    @staticmethod
    def _split_at_boundary(text: str, max_len: int) -> list[str]:
        """Split text at paragraph boundaries, not mid-word."""
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            # Find last double-newline before limit
            split_at = text.rfind("\n\n", 0, max_len)
            if split_at == -1:
                # No paragraph break — try single newline
                split_at = text.rfind("\n", 0, max_len)
            if split_at == -1:
                # No newline at all — split at space
                split_at = text.rfind(" ", 0, max_len)
            if split_at == -1:
                # Give up — hard split
                split_at = max_len
            chunks.append(text[:split_at].rstrip())
            text = text[split_at:].lstrip()
        return chunks

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Try Markdown parse mode if not specified
        if parse_mode is None:
            parse_mode = "Markdown"

        # Split long messages at paragraph boundaries (not mid-word)
        if len(text) > _MAX_MESSAGE_LENGTH:
            chunks = self._split_at_boundary(text, _MAX_MESSAGE_LENGTH - 100)
            result: dict[str, Any] = {}
            for i, chunk in enumerate(chunks):
                kwargs: dict[str, Any] = {
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": parse_mode,
                }
                # Only add reply_markup to the last chunk
                if i == len(chunks) - 1 and reply_markup:
                    kwargs["reply_markup"] = reply_markup
                try:
                    call_res = self._call("sendMessage", **kwargs)
                except Exception:
                    logger.debug("operation_failed", exc_info=True)
                    # Markdown failed — retry without parse_mode
                    kwargs["parse_mode"] = None
                    call_res = self._call("sendMessage", **kwargs)
                if isinstance(call_res, dict):
                    result = call_res
            return result

        try:
            first = self._call(
                "sendMessage",
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            return first if isinstance(first, dict) else {}
        except Exception:
            logger.debug("operation_failed", exc_info=True)
            # Markdown parse failed — retry as plain text
            fallback = self._call(
                "sendMessage",
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
            )
            return fallback if isinstance(fallback, dict) else {}

    def send_document(
        self,
        chat_id: int,
        file_path: Path,
        caption: str | None = None,
    ) -> dict[str, Any]:
        """Send a document file to a chat. Retries on network errors."""
        url = f"{self._base}/sendDocument"
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                with open(file_path, "rb") as f:
                    data: dict[str, Any] = {"chat_id": str(chat_id)}
                    if caption:
                        data["caption"] = caption
                    fields = {
                        **data,
                        "document": (
                            file_path.name,
                            f.read(),
                            "application/octet-stream",
                        ),
                    }
                    status, result, text = self._post_multipart(url, fields, timeout=120)
                    if status >= 500:
                        raise RuntimeError(f"Telegram HTTP {status}: {text[:200]}")
                    if result.get("ok"):
                        inner = result.get("result", {})
                        return inner if isinstance(inner, dict) else {}
                    logger.warning(
                        "Telegram API error: %s",
                        result.get("description", ""),
                    )
                    return {}
            except (
                HTTPError,
                ConnectionResetError,
            ) as e:
                last_err = e
                wait = 2 ** attempt
                logger.warning(
                    "File send attempt %d: %s. Retrying in %ds...",
                    attempt + 1, e, wait,
                )
                time.sleep(wait)
            except Exception as e:
                logger.error("Error sending document: %s", e)
                _log_error(e)
                return {}
        if last_err:
            logger.error("Failed after 3 retries: %s", last_err)
            _log_error(last_err)
        return {}

    def send_chat_action(self, chat_id: int, action: str = "typing") -> dict[str, Any]:
        res = self._call("sendChatAction", chat_id=chat_id, action=action)
        return res if isinstance(res, dict) else {}

    def answer_callback_query(
        self, callback_query_id: str, text: str | None = None,
    ) -> dict[str, Any]:
        res = self._call(
            "answerCallbackQuery",
            callback_query_id=callback_query_id,
            text=text,
        )
        return res if isinstance(res, dict) else {}

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        res = self._call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
        return res if isinstance(res, dict) else {}

    def get_file(self, file_id: str) -> dict[str, Any]:
        res = self._call("getFile", file_id=file_id)
        return res if isinstance(res, dict) else {}

    def download_file(self, file_path: str, local_path: Path) -> bool:
        """Download a file from Telegram servers. Retries on network errors."""
        url = f"{_API_BASE}/file/bot{self.token}/{file_path}"
        for attempt in range(3):
            try:
                resp = self._http.request("GET", url, timeout=_timeout(30))
                if resp.status >= 400:
                    raise RuntimeError(f"Telegram HTTP {resp.status}: {resp.data[:200]!r}")
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_bytes(resp.data)
                return True
            except (HTTPError, ConnectionResetError) as e:
                wait = 2 ** attempt
                logger.warning(
                    "Network error downloading file (attempt %d): %s. Retrying in %ds...",
                    attempt + 1, e, wait,
                )
                time.sleep(wait)
            except Exception as e:
                logger.error("Error downloading file: %s", e)
                return False
        return False

    def set_my_commands(self, commands: list[dict[str, Any]]) -> dict[str, Any]:
        res = self._call("setMyCommands", commands=commands)
        return res if isinstance(res, dict) else {}


# ── Thin transport ────────────────────────────────────────────────────


class EduAgentTelegramBot:
    """Thin Telegram transport — delegates everything to the Gateway."""

    COMMANDS = [
        {"command": "start", "description": "Welcome and setup guide"},
        {"command": "help", "description": "List all commands"},
        {"command": "lesson", "description": "Generate a daily lesson"},
        {"command": "unit", "description": "Plan a unit"},
        {"command": "materials", "description": "Generate worksheets and assessments"},
        {"command": "export", "description": "Export last lesson (DOCX/PPTX/PDF)"},
        {"command": "models", "description": "Browse and switch AI models"},
        {"command": "config", "description": "Show current configuration"},
        {"command": "schedule", "description": "Manage reminders"},
        {"command": "gaps", "description": "Curriculum gap analysis"},
        {"command": "standards", "description": "Search state standards"},
        {"command": "ingest", "description": "Learn from your lesson files"},
        {"command": "demo", "description": "Show demo lesson"},
        {"command": "reset", "description": "Reset configuration"},
    ]

    def __init__(self, token: str, data_dir: Path | None = None):
        self.token = token
        from clawed.paths import data_dir as _data_dir
        self.data_dir = data_dir or _data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.api = TelegramAPI(token)
        self._running = False
        self._chat_ids: set[int] = set()  # Track active teacher chat IDs

        from clawed.gateway import Gateway
        self.gateway = Gateway()
        self._loop = asyncio.new_event_loop()

    @classmethod
    def from_env(cls, data_dir: Path | None = None) -> EduAgentTelegramBot:
        """Create a bot by resolving the token from the environment."""
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            try:
                from clawed.models import AppConfig
                cfg = AppConfig.load()
                token = cfg.telegram_bot_token
            except ImportError:
                pass
        if not token:
            raise ValueError(
                "No Telegram bot token found.\n"
                "Set the TELEGRAM_BOT_TOKEN environment variable or run:\n"
                "  clawed config set-token YOUR_TOKEN"
            )
        return cls(token=token, data_dir=data_dir)

    def run(self, force: bool = False) -> None:
        """Start the polling loop. Blocks until SIGINT/SIGTERM."""
        _check_bot_lock(force=force)

        import atexit
        atexit.register(_release_bot_lock)

        def _signal_handler(sig: int, frame: Any) -> None:
            self._running = False
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        # Clear stale webhooks but keep pending updates
        with contextlib.suppress(Exception):
            self.api._call("deleteWebhook")

        self.api.set_my_commands(self.COMMANDS)
        me = self.api.get_me()
        bot_name = me.get("username", "unknown")
        logger.info("Bot @%s started, entering polling loop", bot_name)
        print(
            f"\nClaw-ED Telegram bot is running!\n"
            f"Send a message to @{bot_name} to start.\n"
            f"Press Ctrl+C to stop.\n",
            flush=True,
        )

        self._running = True
        offset = 0

        # Start from latest update (don't re-process old messages)
        try:
            old = self.api._call("getUpdates", offset=-1, timeout=0)
            if old and isinstance(old, list) and len(old) > 0:
                # Process the most recent pending message
                for update in old:
                    offset = update["update_id"] + 1
                    try:
                        self._process_update(update)
                    except Exception as e:
                        logger.warning("Error processing pending: %s", e)
        except Exception:
            logger.debug("operation_failed", exc_info=True)
        _morning_prep_date = None

        while self._running:
            try:
                # Morning prep: proactive message at 6 AM daily
                try:
                    from datetime import date
                    from datetime import datetime as _dt
                    now = _dt.now()
                    if (now.hour == 6 and now.minute < 5
                            and _morning_prep_date != date.today()):
                        _morning_prep_date = date.today()
                        self._send_morning_prep()
                except ImportError:
                    pass

                updates = self.api.get_updates(offset=offset, timeout=30)
                for update in updates:
                    offset = update["update_id"] + 1
                    self._process_update(update)
            except Exception as e:
                logger.error("Error in polling loop: %s", e)
                _log_error(e)
                self._loop.run_until_complete(asyncio.sleep(2))

        print("\nBot stopped.")
        _release_bot_lock()
        self._loop.close()
        self.api.close()

    def _send_morning_prep(self) -> None:
        """Send proactive morning prep message to the teacher."""
        try:
            # Get the teacher's name from config
            import json

            from clawed.paths import data_dir as _data_dir_fn
            cfg_path = _data_dir_fn() / "config.json"
            name = "there"
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text())
                raw = cfg.get("teacher_profile", {}).get("name", "")
                if raw:
                    parts = raw.strip().split()
                    name = " ".join(parts[:2]) if len(parts) >= 2 else parts[0]

            msg = (
                f"Good morning, {name}! Ready to prep today's lessons.\n\n"
                "What topics are you covering today? I'll generate "
                "everything — lesson plans, handouts, slides, differentiated "
                "versions, and a review game — in a few minutes."
            )
            # Send to the most recent chat
            for chat_id in list(self._chat_ids)[:1]:
                self.api.send_message(chat_id, msg)
                logger.info("Morning prep message sent to %s", chat_id)
        except Exception as e:
            logger.debug("Morning prep failed: %s", e)

    def _process_update(self, update: dict[str, Any]) -> None:
        """Route an update through the Gateway."""
        try:
            # Track chat IDs for proactive messaging (morning prep)
            msg = update.get("message") or update.get("callback_query", {}).get("message")
            if msg and msg.get("chat", {}).get("id"):
                self._chat_ids.add(msg["chat"]["id"])

            if "callback_query" in update:
                cb = update["callback_query"]
                chat_id = cb["message"]["chat"]["id"]
                teacher_id = str(cb["from"]["id"])
                data = cb.get("data", "")
                self.api.answer_callback_query(cb["id"])
                response = self._loop.run_until_complete(
                    self.gateway.handle_callback(data, teacher_id)
                )
                self._send_response(self.api, chat_id, response)

            elif "message" in update:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                teacher_id = str(msg["from"]["id"])

                # Download attached files
                files = self._download_files(msg)

                text = msg.get("text", "")

                # Show typing while gateway processes
                self.api.send_chat_action(chat_id, "typing")

                # Periodic typing indicator for long operations
                typing_stop = threading.Event()

                def _typing_loop() -> None:
                    while not typing_stop.wait(4.0):
                        try:
                            self.api.send_chat_action(chat_id, "typing")
                        except Exception:
                            logger.debug("operation_failed", exc_info=True)
                            break

                typing_thread = threading.Thread(target=_typing_loop, daemon=True)
                typing_thread.start()

                # Progress callback — lets tools send mid-operation updates.
                def _progress_cb(msg: str, _cid: int = chat_id, _tok: str = self.token) -> None:
                    with contextlib.suppress(Exception):
                        _post_json(
                            _HTTP,
                            f"https://api.telegram.org/bot{_tok}/sendMessage",
                            {"chat_id": _cid, "text": msg},
                            timeout=10,
                        )

                try:
                    response = self._loop.run_until_complete(
                        self.gateway.handle(
                            text, teacher_id,
                            files=files or None,
                            progress_callback=_progress_cb,
                            transport="telegram",
                        )
                    )
                finally:
                    typing_stop.set()
                    typing_thread.join(timeout=1)

                try:
                    self._send_response(self.api, chat_id, response)
                except Exception as send_err:
                    logger.error("Failed to send response: %s", send_err)
                    _log_error(send_err)
                    # Last resort: send text even if file delivery fails
                    if hasattr(response, "text") and response.text:
                        with contextlib.suppress(Exception):
                            self.api.send_message(chat_id, response.text)

        except Exception as e:
            logger.error("Error processing update: %s", e)
            _log_error(e)
            # Send error message so teacher isn't left hanging
            with contextlib.suppress(Exception):
                self.api.send_message(
                    chat_id,
                    "Something went wrong processing that. "
                    "Try again or rephrase your request.",
                )

    def _download_files(self, msg: dict[str, Any]) -> list[Path]:
        """Download any attached documents from a Telegram message."""
        files: list[Path] = []
        doc = msg.get("document")
        if not doc:
            return files

        file_info = self.api.get_file(doc["file_id"])
        tg_path = file_info.get("file_path")
        if not tg_path:
            return files

        suffix = Path(doc.get("file_name", "file")).suffix or ""
        fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=self.data_dir / "downloads")
        os.close(fd)
        local = Path(tmp_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        if self.api.download_file(tg_path, local):
            files.append(local)
        return files

    def _send_response(self, api: TelegramAPI, chat_id: int, response: Any) -> None:
        """Render a GatewayResponse to Telegram messages."""
        from clawed.gateway_response import GatewayResponse

        if not isinstance(response, GatewayResponse) or not response.has_content:
            return

        reply_markup = None
        rows = response.button_rows
        if not rows and response.buttons:
            rows = [response.buttons]
        if rows:
            keyboard = []
            for row in rows:
                keyboard.append([
                    {
                        "text": b.label,
                        **({"url": b.url} if b.url else {"callback_data": b.callback_data}),
                    }
                    for b in row
                ])
            reply_markup = {"inline_keyboard": keyboard}

        if response.text:
            api.send_message(chat_id, response.text, reply_markup=reply_markup)

        for file_path in response.files:
            # Add descriptive caption based on file type
            name = file_path.name if hasattr(file_path, "name") else str(file_path)
            caption = ""
            if "teacher" in name.lower():
                caption = "Teacher lesson plan (with answer key)"
            elif "student" in name.lower():
                caption = "Student handout"
            elif "slides" in name.lower() or name.endswith(".pptx"):
                caption = "Slideshow"
            elif "diff_iep" in name.lower() or "diff_504" in name.lower():
                caption = "IEP/504 accommodations"
            elif "diff_ell" in name.lower():
                caption = "ELL scaffolding"
            elif "diff_advanced" in name.lower():
                caption = "Gifted extensions"
            elif "game" in name.lower():
                caption = "Review game (open in browser)"
            elif "journey" in name.lower():
                caption = "Learning journey (open in browser)"
            elif "research" in name.lower():
                caption = "Research report"
            api.send_document(chat_id, file_path, caption=caption)


def run_bot(token: str | None = None, force: bool = False, data_dir: Path | None = None) -> None:
    """Entry point — create and run the bot."""
    bot = EduAgentTelegramBot(token, data_dir=data_dir) if token else EduAgentTelegramBot.from_env(data_dir=data_dir)
    bot.run(force=force)


def send_notification(text: str) -> bool:
    """Send a one-off notification to the teacher via Telegram.

    Used by scheduler tasks (morning-prep, weekly-plan) to alert the
    teacher about auto-generated content. Returns True if sent, False
    if Telegram is not configured.

    Does NOT require the bot polling loop to be running — creates a
    temporary connection, sends the message, and disconnects.
    """
    try:
        from clawed.config import get_api_key

        token = get_api_key("telegram_bot_token")
        if not token:
            logger.debug("send_notification: no bot token configured")
            return False

        # Load teacher chat_id from config
        import json as _json

        config_path = _BASE / "config.json"
        if not config_path.exists():
            logger.debug("send_notification: no config.json")
            return False

        config = _json.loads(config_path.read_text(encoding="utf-8"))
        chat_id = config.get("telegram_chat_id") or config.get("teacher_chat_id")
        if not chat_id:
            logger.debug("send_notification: no chat_id in config")
            return False

        # Send via Telegram API directly (no bot instance needed)
        url = f"{_API_BASE}/bot{token}/sendMessage"
        payload = {
            "chat_id": int(chat_id),
            "text": text[:_MAX_MESSAGE_LENGTH],
            "parse_mode": "Markdown",
        }
        status, result, text_body = _post_json(_HTTP, url, payload, timeout=10)
        if status == 200 and result.get("ok"):
            logger.info("Notification sent to Telegram chat %s", chat_id)
            return True
        else:
            logger.warning("Telegram notification failed: %s", text_body[:200])
            return False

    except Exception as exc:
        logger.debug("send_notification failed: %s", exc)
        return False
