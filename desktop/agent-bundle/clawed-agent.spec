# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the self-contained clawed agent sidecar.

Strategy: freeze normally (full dependency tracing via hiddenimports),
AND ship the clawed source tree as datas at the same package path. The
agent has file-system-dependent code — ToolRegistry.discover() globs
``*.py`` next to ``tools/base.py``, the API serves ``clawed/api/static``
via ``Path(__file__)`` — which only works when real files exist at the
path ``__file__`` reports. Placing the source tree in the bundle at
``clawed/`` makes both the frozen imports and the file lookups resolve.

Build with desktop/agent-bundle/build.sh (creates the venv, runs
pyinstaller, smoke-tests the result).
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

repo = Path(SPECPATH).resolve().parents[1]  # noqa: F821 — SPECPATH is injected
clawed_src = repo / "clawed"
assert clawed_src.is_dir(), f"clawed package not found at {clawed_src}"

# Real source files at the frozen package path (discover() glob, static/,
# templates, prompt assets — everything Path(__file__)-relative).
datas = [(str(clawed_src), "clawed")]

# Freeze every clawed module (most are imported lazily inside functions,
# which static analysis of the entry script alone would miss) plus the
# dynamic corners of the server stack.
hiddenimports = collect_submodules("clawed")
for pkg in ("uvicorn", "apscheduler", "sse_starlette", "json_repair", "keyring"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass

a = Analysis(
    ["serve_entry.py"],
    pathex=[str(repo)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Optional heavyweights — their tools degrade gracefully when absent.
        "tkinter", "matplotlib", "torch", "onnxruntime", "playwright",
        "manim", "textual", "faster_whisper", "av", "pytest", "mypy",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="clawed-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="clawed-agent",
)
