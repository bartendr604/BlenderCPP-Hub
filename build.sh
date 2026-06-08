#!/bin/bash
# =============================================================================
# build.sh — compile hub_core.dylib for the Blender CPP Hub
# Copyright © 2025–2026 Eternal Path Media / D. Chow / Claude Sonnet / Llammy
# =============================================================================
set -e
cd "$(dirname "$0")"

echo "=== Blender CPP Hub — build ==="
echo "Target: Apple Silicon / macOS"

mkdir -p build && cd build

cmake .. -DCMAKE_BUILD_TYPE=Release \
         -DCMAKE_OSX_ARCHITECTURES="arm64;x86_64" \
         -DCMAKE_INSTALL_PREFIX=".."

cmake --build . --parallel 4
cmake --install .

echo ""
echo "Built: $(ls -lh ../hub_core.dylib)"
echo "=== Done ==="
