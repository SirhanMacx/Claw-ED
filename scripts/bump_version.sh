#!/bin/bash
set -euo pipefail

# Bump Claw-ED version in pyproject.toml and clawed/__init__.py
# Usage: ./scripts/bump_version.sh 4.25.2026

if [ $# -ne 1 ]; then
    echo "Usage: $0 <new-version>"
    echo "Example: $0 4.25.2026"
    exit 1
fi

NEW_VERSION="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Validate PEP 440-compatible numeric release format.
if ! echo "$NEW_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?$'; then
    echo "Error: Version must be numeric, e.g. 4.25.2026 or 4.25.2026.1"
    exit 1
fi

# Update pyproject.toml
sed -i.bak "s/^version = \".*\"/version = \"${NEW_VERSION}\"/" "$ROOT/pyproject.toml"

# Update __init__.py
sed -i.bak "s/^__version__ = \".*\"/__version__ = \"${NEW_VERSION}\"/" "$ROOT/clawed/__init__.py"
rm -f "$ROOT/pyproject.toml.bak" "$ROOT/clawed/__init__.py.bak"

echo "Bumped version to ${NEW_VERSION}"
echo "  - pyproject.toml"
echo "  - clawed/__init__.py"
