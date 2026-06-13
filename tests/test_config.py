"""Tests for clawed.config — API-key resolution and keyring resilience.

These lock in a real, observed failure: on macOS the keychain backend can
raise (error -25291) when it is locked, or in a headless / SSH / cron context.
The previous code only caught ImportError, so a keychain hiccup propagated all
the way up and made AppConfig.load() declare the app "not configured" — even
when a perfectly valid key was sitting in secrets.json or the environment. For
a tool meant to be dependable for any teacher daily, a keychain backend failure
must degrade gracefully to the next key source, never crash the app.
"""

from __future__ import annotations

import sys
import types

import clawed.config as cfg


def _fake_keyring(*, get=None, set_=None, delete=None) -> types.ModuleType:
    """Build a stand-in `keyring` module with the given callables."""
    mod = types.ModuleType("keyring")
    if get is not None:
        mod.get_password = get  # type: ignore[attr-defined]
    if set_ is not None:
        mod.set_password = set_  # type: ignore[attr-defined]
    if delete is not None:
        mod.delete_password = delete  # type: ignore[attr-defined]
    return mod


def _raise_keychain_error(*_args, **_kwargs):
    # Mirrors the real macOS failure surface (keyring.errors.KeyringError).
    raise RuntimeError("Can't get password from keychain: (-25291, 'Unknown Error')")


def test_get_api_key_survives_keyring_error_falls_through_to_secrets(monkeypatch):
    """A keychain GET failure must fall through to the secrets.json key."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "keyring", _fake_keyring(get=_raise_keychain_error))
    monkeypatch.setattr(cfg, "_load_secrets", lambda: {"openrouter_api_key": "sk-from-file"})

    assert cfg.get_api_key("openrouter") == "sk-from-file"


def test_get_api_key_prefers_env_even_with_broken_keyring(monkeypatch):
    """The env var still wins and is reached before keyring is ever consulted."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-env")
    monkeypatch.setitem(sys.modules, "keyring", _fake_keyring(get=_raise_keychain_error))

    assert cfg.get_api_key("openrouter") == "sk-from-env"


def test_appconfig_load_survives_keyring_error(monkeypatch):
    """The whole config load must not crash when the keychain backend raises."""
    monkeypatch.setitem(sys.modules, "keyring", _fake_keyring(get=_raise_keychain_error))

    from clawed.models import AppConfig

    config = AppConfig.load()  # must NOT raise
    assert config is not None


def test_set_api_key_falls_back_to_file_on_keyring_error(monkeypatch):
    """A keychain WRITE failure must fall back to the secrets.json file."""
    monkeypatch.setitem(sys.modules, "keyring", _fake_keyring(set_=_raise_keychain_error))
    saved: dict[str, str] = {}
    monkeypatch.setattr(cfg, "_load_secrets", lambda: dict(saved))
    monkeypatch.setattr(cfg, "_save_secrets", lambda s: saved.update(s))

    cfg.set_api_key("openrouter", "sk-written")

    assert saved.get("openrouter_api_key") == "sk-written"


def test_set_api_key_falls_back_when_keyring_write_is_not_readable(monkeypatch):
    """A no-op keyring backend must not make set-key look successful."""
    monkeypatch.setitem(
        sys.modules,
        "keyring",
        _fake_keyring(
            set_=lambda *_args, **_kwargs: None,
            get=lambda *_args, **_kwargs: None,
        ),
    )
    saved: dict[str, str] = {}
    monkeypatch.setattr(cfg, "_load_secrets", lambda: dict(saved))
    monkeypatch.setattr(cfg, "_save_secrets", lambda s: saved.update(s))

    cfg.set_api_key("openrouter", "sk-readable-next-process")

    assert saved.get("openrouter_api_key") == "sk-readable-next-process"


def test_delete_api_key_survives_keyring_error(monkeypatch):
    """A keychain DELETE failure must not crash; the file cleanup still runs."""
    monkeypatch.setitem(sys.modules, "keyring", _fake_keyring(delete=_raise_keychain_error))
    saved: dict[str, str] = {"openrouter_api_key": "sk-old"}
    monkeypatch.setattr(cfg, "_load_secrets", lambda: dict(saved))
    monkeypatch.setattr(cfg, "_save_secrets", lambda s: saved.clear() or saved.update(s))

    cfg.delete_api_key("openrouter")  # must NOT raise

    assert "openrouter_api_key" not in saved


def test_missing_keyring_import_still_falls_through(monkeypatch):
    """Absent keyring (ImportError) keeps working — the pre-existing contract."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def _raise_import(*_args, **_kwargs):
        raise ImportError("no keyring")

    # Force `import keyring` inside the helper to raise ImportError.
    monkeypatch.setitem(sys.modules, "keyring", None)  # `import keyring` -> ImportError
    monkeypatch.setattr(cfg, "_load_secrets", lambda: {"openrouter_api_key": "sk-file2"})

    assert cfg.get_api_key("openrouter") == "sk-file2"
