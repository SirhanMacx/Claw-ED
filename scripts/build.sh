#!/usr/bin/env bash
# Build the owned Python package. Node.js and Bun are not required.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m build
