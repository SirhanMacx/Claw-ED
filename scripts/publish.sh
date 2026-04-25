#!/bin/bash
set -euo pipefail

# Build and publish Claw-ED to PyPI
# Usage: ./scripts/publish.sh
#
# Requires: uv

echo "==> Claw-ED PyPI Publisher"
echo ""

# ── Check dist/ ──────────────────────────────────────────────────────────────

if [[ ! -d dist/ ]] || [[ -z "$(ls -A dist/ 2>/dev/null)" ]]; then
    echo "No dist/ found. Building package first..."
    uv build
fi

# Verify wheel and tarball exist
WHEEL=$(ls dist/*.whl 2>/dev/null | head -1)
TARBALL=$(ls dist/*.tar.gz 2>/dev/null | head -1)

if [[ -z "$WHEEL" || -z "$TARBALL" ]]; then
    echo "✗ Missing wheel or tarball in dist/. Rebuilding..."
    uv build --clear
fi

echo "✓ Found artifacts:"
ls -1 dist/

# ── PyPI credentials ─────────────────────────────────────────────────────────

if [[ -z "${UV_PUBLISH_TOKEN:-}" && -n "${TWINE_PASSWORD:-}" ]]; then
    export UV_PUBLISH_TOKEN="${TWINE_PASSWORD}"
fi

if [[ -z "${UV_PUBLISH_TOKEN:-}" ]]; then
    echo ""
    echo "PyPI API token not found in env (UV_PUBLISH_TOKEN)."
    echo "Get one at: https://pypi.org/manage/account/token/"
    read -rsp "Enter PyPI API token (starts with pypi-): " UV_PUBLISH_TOKEN
    echo ""
    export UV_PUBLISH_TOKEN
fi

# ── Upload ────────────────────────────────────────────────────────────────────

echo ""
echo "Uploading to PyPI..."
uv publish dist/*

echo ""
echo "✓ Upload complete! https://pypi.org/project/clawed/"

# ── Bump version for next dev cycle ──────────────────────────────────────────

CURRENT=$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)".*/\1/')
IFS='.' read -r -a PARTS <<< "$CURRENT"
case "${#PARTS[@]}" in
    3)
        NEXT="${PARTS[0]}.${PARTS[1]}.$((PARTS[2] + 1))"
        ;;
    4)
        NEXT="${PARTS[0]}.${PARTS[1]}.${PARTS[2]}.$((PARTS[3] + 1))"
        ;;
    *)
        echo "Cannot auto-bump version '${CURRENT}'. Expected 3 or 4 numeric segments."
        exit 1
        ;;
esac

echo ""
read -rp "Bump version to ${NEXT} for next release? [Y/n] " bump
if [[ "${bump:-Y}" =~ ^[Yy]$ ]]; then
    sed -i.bak "s/^version = \"${CURRENT}\"/version = \"${NEXT}\"/" pyproject.toml
    sed -i.bak "s/^__version__ = \"${CURRENT}\"/__version__ = \"${NEXT}\"/" clawed/__init__.py
    rm -f pyproject.toml.bak clawed/__init__.py.bak
    echo "✓ Version bumped to ${NEXT}"

    echo "Rebuilding with new version..."
    uv build --clear
    echo "✓ Rebuilt dist/ with v${NEXT}"
fi

echo ""
echo "Done!"
