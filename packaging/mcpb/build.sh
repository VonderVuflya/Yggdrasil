#!/usr/bin/env bash
# Build the Claude Desktop extension bundle (.mcpb) for Yggdrasil.
#
# An .mcpb is just a ZIP of: manifest.json + server/ (the zero-dep payload).
# We stage the payload from the live package so there is no committed copy to
# drift. Output: packaging/mcpb/yggdrasil-<version>.mcpb
#
# Usage:  bash packaging/mcpb/build.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PKG="$REPO/yggdrasil"

VERSION="$(python3 -c "import re,pathlib;print(re.search(r'__version__\s*=\s*\"([^\"]+)\"',pathlib.Path('$PKG/__init__.py').read_text()).group(1))")"
OUT="$HERE/yggdrasil-$VERSION.mcpb"

# Keep the manifest version in lockstep with the package.
MANIFEST_VER="$(python3 -c "import json,pathlib;print(json.loads(pathlib.Path('$HERE/manifest.json').read_text())['version'])")"
if [ "$MANIFEST_VER" != "$VERSION" ]; then
  echo "ERROR: manifest.json version ($MANIFEST_VER) != package version ($VERSION). Bump manifest.json first." >&2
  exit 1
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/server"
cp "$HERE/manifest.json" "$STAGE/manifest.json"
# Minimal payload: the stdio facade + the CLI it shells out to + their shared core.
for f in ygg_mcp_server.py ygg.py ygg_core.py ygg_config.py ygg_ui.py __init__.py; do
  cp "$PKG/$f" "$STAGE/server/$f"
done

rm -f "$OUT"
( cd "$STAGE" && zip -q -r -X "$OUT" manifest.json server )

echo "built: $OUT"
unzip -l "$OUT"
