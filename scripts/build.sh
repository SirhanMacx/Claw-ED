#!/bin/bash
# scripts/build.sh — Build Claw-ED: TypeScript CLI + Python wheel
#
# This script:
# 1. Builds the TypeScript CLI (Ink TUI) via Bun
# 2. Copies the built cli.js into the Python package
# 3. Builds the Python wheel for PyPI distribution
#
# Prerequisites:
#   - Node.js 18+ and Bun installed
#   - Python 3.11+
#   - uv
#
# Usage:
#   bash scripts/build.sh          # Full build
#   bash scripts/build.sh --skip-ts  # Skip TypeScript build (use existing cli.js)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "╔══════════════════════════════════════╗"
echo "║    Building Claw-ED                  ║"
echo "║    The Agentic Layer for Education   ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Step 0: Check prerequisites
echo "→ Checking prerequisites..."
command -v node >/dev/null 2>&1 || { echo "ERROR: Node.js not found. Install from https://nodejs.org"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: Python 3 not found."; exit 1; }
command -v uv >/dev/null 2>&1 || { echo "ERROR: uv not found. Install from https://docs.astral.sh/uv/"; exit 1; }
echo "  Node.js: $(node --version)"
echo "  Python:  $(python3 --version)"
echo "  uv:      $(uv --version)"
echo ""

# Step 1: Build TypeScript CLI
if [[ "${1:-}" != "--skip-ts" ]]; then
    echo "→ Step 1: Building TypeScript CLI..."
    cd "$REPO_ROOT/cli"

    if [ ! -d "node_modules" ]; then
        echo "  Installing npm dependencies..."
        npm install --silent
    fi

    echo "  Running Bun build..."
    node scripts/build-cli.mjs

    if [ ! -f "dist/cli.js" ]; then
        echo "ERROR: TypeScript build failed — dist/cli.js not found"
        exit 1
    fi

    CLI_SIZE=$(du -sh dist/ | cut -f1)
    echo "  Built: cli.js ($CLI_SIZE)"
    cd "$REPO_ROOT"
else
    echo "→ Step 1: Skipping TypeScript build (--skip-ts)"
fi

# Step 2: Bundle cli.js into Python package
echo ""
echo "→ Step 2: Bundling cli.js into Python package..."
mkdir -p "$REPO_ROOT/clawed/_cli_bundle"

if [ -d "$REPO_ROOT/cli/dist" ]; then
    cp -r "$REPO_ROOT/cli/dist/"* "$REPO_ROOT/clawed/_cli_bundle/"
    BUNDLE_SIZE=$(du -sh "$REPO_ROOT/clawed/_cli_bundle/" | cut -f1)
    echo "  Copied: clawed/_cli_bundle/ ($BUNDLE_SIZE)"
else
    echo "  WARNING: cli/dist/ not found. Python package will use fallback CLI."
fi
# Ensure ESM package.json always exists (needed by hatch force-include)
echo '{"type": "module"}' > "$REPO_ROOT/clawed/_cli_bundle/package.json"

# Step 3: Build Python wheel
echo ""
echo "→ Step 3: Building Python wheel..."
cd "$REPO_ROOT"

uv build --wheel --clear

if ls dist/*.whl 1>/dev/null 2>&1; then
    WHEEL=$(ls dist/*.whl | head -1)
    WHEEL_SIZE=$(du -h "$WHEEL" | cut -f1)
    echo ""
    echo "╔══════════════════════════════════════╗"
    echo "║    Build complete!                   ║"
    echo "╠══════════════════════════════════════╣"
    echo "║  Wheel: $WHEEL_SIZE                          ║"
    echo "║  Path:  dist/                        ║"
    echo "╚══════════════════════════════════════╝"
    echo ""
    echo "To install locally:  pip install dist/*.whl"
    echo "To upload to PyPI:   uv publish dist/*"
else
    echo "ERROR: Wheel build failed"
    exit 1
fi
