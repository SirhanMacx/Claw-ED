"""Secure configuration and API key management for Claw-ED.

Stores API keys in OS keychain when available (via keyring library),
with fallback to ~/.eduagent/secrets.json (0600 permissions).
Non-secret config lives in ~/.eduagent/config.json via AppConfig.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Optional

from clawed.models import AppConfig

_BASE_DIR = Path(os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))
_SECRETS_DIR = _BASE_DIR
_SECRETS_FILE = _SECRETS_DIR / "secrets.json"
# Internal service name — matches filesystem path (~/.eduagent) and keyring
# entries. Kept as "eduagent" for backwards compatibility with existing installs.
# The user-facing brand is "Claw-ED" / "Ed" via the CLI entry points.
_SERVICE_NAME = "eduagent"


def _load_secrets() -> dict[str, str]:
    if _SECRETS_FILE.exists():
        try:
            return json.loads(_SECRETS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_secrets(secrets: dict[str, str]) -> None:
    _SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    _SECRETS_FILE.write_text(json.dumps(secrets, indent=2), encoding="utf-8")
    try:
        os.chmod(str(_SECRETS_FILE), stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass


def _try_keyring_get(key: str) -> Optional[str]:
    try:
        import keyring

        return keyring.get_password(_SERVICE_NAME, key)
    except Exception:
        return None


def _try_keyring_set(key: str, value: str) -> bool:
    try:
        import keyring

        keyring.set_password(_SERVICE_NAME, key, value)
        return True
    except Exception:
        return False


def _try_keyring_delete(key: str) -> bool:
    try:
        import keyring

        keyring.delete_password(_SERVICE_NAME, key)
        return True
    except Exception:
        return False


def _resolve_claude_code_token() -> Optional[str]:
    """Get a valid OAuth token, refreshing if near expiry.

    Uses the OAuth refresh flow from Claude Code's credential store.
    Tokens are refreshed automatically when less than 10 minutes remain.
    """
    try:
        from clawed.oauth_refresh import get_oauth_token

        token = get_oauth_token()
        if token:
            return token
    except (ImportError, AttributeError, ValueError):
        pass

    # Fallback: read raw token without refresh
    import json as _json

    for path in [
        Path.home() / ".claude" / ".credentials.json",
        Path.home() / ".claude.json",
    ]:
        if path.exists():
            try:
                data = _json.loads(path.read_text(encoding="utf-8"))
                oauth = data.get("claudeAiOauth", {})
                token = oauth.get("accessToken", "")
                if token:
                    return token
            except (ValueError, KeyError, OSError):
                continue
    return None


def _resolve_codex_token() -> Optional[str]:
    """Get OpenAI access token from Codex CLI (~/.codex/auth.json).

    Codex stores OAuth tokens at ~/.codex/auth.json with structure:
    {"tokens": {"access_token": "...", "refresh_token": "..."}}

    The token may expire — if the API returns 401, the teacher needs
    to run `codex` to re-authenticate.
    """
    import json as _json

    auth_path = Path.home() / ".codex" / "auth.json"
    if not auth_path.exists():
        return None
    try:
        data = _json.loads(auth_path.read_text(encoding="utf-8"))
        token = data.get("tokens", {}).get("access_token", "")
        if token:
            return token
    except (ValueError, KeyError, OSError):
        pass
    return None


def get_api_key(provider: str) -> Optional[str]:
    """Retrieve an API key for the given provider.

    Priority: environment variable > Claude Code credentials (anthropic only)
              > keyring > secrets.json file.
    """
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "ollama": "OLLAMA_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "telegram": "TELEGRAM_BOT_TOKEN",
        "tavily": "TAVILY_API_KEY",
        "unsplash": "UNSPLASH_ACCESS_KEY",
        "search_brave": "BRAVE_SEARCH_API_KEY",
        "search_tavily": "TAVILY_API_KEY",
    }
    env_var = env_map.get(provider)
    if env_var:
        val = os.environ.get(env_var)
        if val and val not in ("ollama-local", "ollama", "local"):
            return val

    # Claude Code credential store (Anthropic OAuth)
    if provider == "anthropic":
        cc_token = _resolve_claude_code_token()
        if cc_token:
            return cc_token

    # Note: OpenAI Codex CLI tokens (~/.codex/auth.json) are OAuth
    # tokens for the Codex CLI only — they do NOT work with the
    # OpenAI chat completions API. A real API key from
    # platform.openai.com/api-keys is required for the openai provider.

    key_name = f"{provider}_api_key"
    val = _try_keyring_get(key_name)
    if val:
        return val

    secrets = _load_secrets()
    return secrets.get(key_name)


def resolve_credentials(config=None):
    """Resolve the best available provider and key.

    Priority: environment variables > keyring/secrets > Ollama (if configured).
    Returns (provider_name, api_key) or (None, None) if nothing is available.
    """
    import os

    for env_var, provider in [
        ("ANTHROPIC_API_KEY", "anthropic"),
        ("OPENAI_API_KEY", "openai"),
        ("GOOGLE_API_KEY", "google"),
        ("OPENROUTER_API_KEY", "openrouter"),
    ]:
        key = os.environ.get(env_var)
        if key:
            return provider, key
    for provider in ["anthropic", "openai", "google", "openrouter"]:
        key = get_api_key(provider)
        if key:
            return provider, key
    if config:
        from clawed.models import LLMProvider

        if getattr(config, "provider", None) == LLMProvider.OLLAMA:
            return "ollama", None
    return None, None


def set_api_key(provider: str, api_key: str) -> None:
    """Store an API key securely. Tries keyring first, falls back to file."""
    key_name = f"{provider}_api_key"

    if not _try_keyring_set(key_name, api_key):
        secrets = _load_secrets()
        secrets[key_name] = api_key
        _save_secrets(secrets)


def delete_api_key(provider: str) -> None:
    """Remove a stored API key."""
    key_name = f"{provider}_api_key"
    _try_keyring_delete(key_name)

    secrets = _load_secrets()
    if key_name in secrets:
        del secrets[key_name]
        _save_secrets(secrets)


def mask_api_key(key: Optional[str]) -> str:
    """Mask an API key for display: sk-...abc123."""
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return key[:3] + "..." + key[-6:]


def is_anthropic_oauth_token(api_key: str) -> bool:
    """Detect if a key is an Anthropic OAuth token vs a regular API key."""
    if not api_key:
        return False
    if api_key.startswith("sk-ant-api"):
        return False
    if api_key.startswith("sk-ant-"):
        return True
    return False


def is_ollama_cloud(base_url: str) -> bool:
    """Check if an Ollama URL is a cloud endpoint (not local)."""
    return "ollama.com" in base_url.lower() or "api.ollama.com" in base_url.lower()


def has_config() -> bool:
    """Check if any configuration has been saved (first-run detection)."""
    return AppConfig.config_path().exists()


def has_teacher_profile() -> bool:
    """Check if the teacher has completed profile setup (name/subjects/grades).

    This is stricter than has_config() — config.json may exist with just
    the API provider set (from quick_model_setup), but the teacher hasn't
    gone through conversational onboarding yet.
    """
    if not AppConfig.config_path().exists():
        return False
    try:
        config = AppConfig.load()
        tp = config.teacher_profile
        return bool(tp and (tp.name or tp.subjects or tp.grade_levels))
    except (KeyError, TypeError, ValueError, OSError):
        return False


async def test_llm_connection(config: Optional[AppConfig] = None) -> dict:
    """Test the LLM connection and return status info."""
    cfg = config or AppConfig.load()
    provider = cfg.provider.value

    def _result(connected, model, msg_or_err, is_err=False):
        r = {"connected": connected, "provider": provider, "model": model}
        r["error" if is_err else "message"] = msg_or_err
        return r

    if provider == "ollama":
        import httpx

        base = cfg.ollama_base_url.rstrip("/")
        is_cloud = is_ollama_cloud(base)
        api_key = cfg.ollama_api_key or get_api_key("ollama")
        try:
            if is_cloud:
                # Cloud: test with a minimal chat completion
                headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                cloud_base = base.rstrip("/")
                if not cloud_base.endswith("/v1"):
                    cloud_base = f"{cloud_base}/v1"
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    resp = await client.post(
                        f"{cloud_base}/chat/completions",
                        headers=headers,
                        json={
                            "model": cfg.ollama_model,
                            "messages": [{"role": "user", "content": "hi"}],
                            "max_tokens": 5,
                        },
                    )
                    if resp.status_code == 401:
                        return _result(
                            False,
                            cfg.ollama_model,
                            "API key missing or invalid for Ollama Cloud. Run: clawed config set-key ollama YOUR_KEY",
                            is_err=True,
                        )
                    resp.raise_for_status()
                    return _result(True, cfg.ollama_model, f"{cfg.ollama_model} is ready")
            else:
                # Local: test with /api/tags
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(f"{base}/api/tags")
                    resp.raise_for_status()
                    data = resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    model_name = cfg.ollama_model
                    connected = any(model_name in m for m in models)
                    if not connected and models:
                        avail = ", ".join(models[:5])
                        msg = f"Model '{model_name}' not found. Available: {avail}"
                        return _result(False, model_name, msg, is_err=True)
                    return _result(connected, model_name, f"{model_name} is ready")
        except Exception as e:
            return _result(False, cfg.ollama_model, str(e), is_err=True)

    elif provider == "anthropic":
        api_key = get_api_key("anthropic")
        model = cfg.anthropic_model
        if not api_key:
            return _result(
                False,
                model,
                "No API key configured. Set ANTHROPIC_API_KEY or log in to Claude Code.",
                is_err=True,
            )
        try:
            import anthropic as _anthropic
        except ImportError:
            return _result(False, model, "Anthropic SDK not installed. Run: pip install anthropic", is_err=True)
        try:
            is_oauth = is_anthropic_oauth_token(api_key)
            if is_oauth:
                client = _anthropic.Anthropic(
                    auth_token=api_key,
                    default_headers={"anthropic-beta": "oauth-2025-04-20", "x-app": "cli"},
                )
            else:
                client = _anthropic.Anthropic(api_key=api_key)
            client.messages.create(
                model=model,
                max_tokens=5,
                messages=[{"role": "user", "content": "Hi"}],
            )
            return _result(True, model, f"{model} is ready")
        except _anthropic.AuthenticationError:
            return _result(False, model, "API key or OAuth token invalid", is_err=True)
        except _anthropic.RateLimitError:
            return _result(True, model, f"{model} connected (rate limited, will retry)")
        except Exception as e:
            return _result(False, model, str(e), is_err=True)

    elif provider == "openai":
        api_key = get_api_key("openai")
        model = cfg.openai_model
        if not api_key:
            return _result(False, model, "No API key configured", is_err=True)
        import httpx

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-type": "application/json",
                }
                body = {
                    "model": model,
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "Hi"}],
                }
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=body,
                )
                if resp.status_code == 401:
                    return _result(False, model, "API key invalid", is_err=True)
                resp.raise_for_status()
                return _result(True, model, f"{model} is ready")
        except Exception as e:
            return _result(False, model, str(e), is_err=True)

    return {"connected": False, "provider": provider, "error": "Unknown provider"}
