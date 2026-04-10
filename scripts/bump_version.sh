#!/bin/bash
set -euo pipefail

# Bump Claw-ED version in pyproject.toml and clawed/__init__.py.
# Accepts 3- or 4-part version numbers (the project uses 4-part
# year-based versions like 4.9.2026.16).
#
# Usage: ./scripts/bump_version.sh 4.9.2026.17

if [ $# -ne 1 ]; then
    echo "Usage: $0 <new-version>"
    echo "Example: $0 4.9.2026.17"
    exit 1
fi

NEW_VERSION="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Validate version format: at least 3 numeric dot-separated components,
# optionally a 4th (used by this project) and an optional pre-release suffix.
if ! echo "$NEW_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?([.-][A-Za-z0-9]+)*$'; then
    echo "Error: Version must look like 4.9.2026.17 or 1.2.3"
    exit 1
fi

# Portable in-place edit: write to a temp file and replace atomically.
# `sed -i` has incompatible syntax between GNU (Linux) and BSD (macOS),
# so we sidestep it entirely.
portable_sed_i() {
    local pattern="$1"
    local file="$2"
    local tmp
    tmp="$(mktemp)"
    sed "$pattern" "$file" > "$tmp"
    mv "$tmp" "$file"
}

portable_sed_i "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" "$ROOT/pyproject.toml"
portable_sed_i "s/^__version__ = \".*\"/__version__ = \"${NEW_VERSION}\"/" "$ROOT/clawed/__init__.py"

echo "Bumped version to ${NEW_VERSION}"
echo "  - pyproject.toml"
echo "  - clawed/__init__.py"
