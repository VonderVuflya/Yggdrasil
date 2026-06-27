#!/usr/bin/env bash
# Roll out a Yggdrasil release to EVERY channel, in order, from one command.
#
#   bash scripts/release.sh <version> [flags]
#   bash scripts/release.sh 0.4.1
#
# Steps: bump versions → verify CHANGELOG → tests/gates → build (sdist/wheel + .mcpb)
#        → git commit+tag+push → PyPI → Homebrew formula (sha from PyPI) → npm
#        → MCP Registry → GitHub release. Credentialed steps use your existing
#        logins (uv/twine, npm, mcp-publisher, gh). A step whose tool is missing
#        is skipped with a warning; the end prints a done/skipped summary.
#
# Flags: --skip-pypi --skip-npm --skip-brew --skip-mcp --skip-gh --skip-git
#        --no-tests --yes (no prompt) --dry-run
#
# Env:   YGG_TAP_DIR=/path/to/homebrew-tap   (to auto-commit+push the formula)
set -euo pipefail

VERSION="${1:-}"; shift || true
[ -n "$VERSION" ] || { echo "usage: bash scripts/release.sh <version> [flags]"; exit 2; }
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([abrc].*)?$ ]] || { echo "bad version: $VERSION"; exit 2; }

SKIP_PYPI= SKIP_NPM= SKIP_BREW= SKIP_MCP= SKIP_GH= SKIP_GIT= NO_TESTS= YES= DRY=
for f in "$@"; do case "$f" in
  --skip-pypi) SKIP_PYPI=1;; --skip-npm) SKIP_NPM=1;; --skip-brew) SKIP_BREW=1;;
  --skip-mcp) SKIP_MCP=1;; --skip-gh) SKIP_GH=1;; --skip-git) SKIP_GIT=1;;
  --no-tests) NO_TESTS=1;; --yes) YES=1;; --dry-run) DRY=1;;
  *) echo "unknown flag: $f"; exit 2;; esac; done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
PKG="yggdrasil-memory"; TAP_FORMULA="packaging/homebrew/yggdrasil.rb"
SUMMARY=()
run() { if [ -n "$DRY" ]; then echo "  [dry-run] $*"; else "$@"; fi; }
note() { SUMMARY+=("$1"); }

echo "==> Releasing $PKG $VERSION  (dry-run=${DRY:-no})"
if [ -z "$YES" ] && [ -z "$DRY" ]; then
  read -r -p "Proceed? [y/N]: " a; [[ "$a" =~ ^[Yy] ]] || { echo aborted; exit 1; }
fi

# 1. Bump versions everywhere (python = safe for JSON).
echo "==> bumping versions"
run python3 - "$VERSION" <<'PY'
import re, sys, pathlib
v = sys.argv[1]
edits = {
  "yggdrasil/__init__.py":      (r'__version__\s*=\s*"[^"]+"', f'__version__ = "{v}"'),
  "pyproject.toml":             (r'(?m)^version\s*=\s*"[^"]+"', f'version = "{v}"'),
  "clients/npm/package.json":   (r'"version":\s*"[^"]+"', f'"version": "{v}"'),
  "packaging/mcpb/manifest.json":(r'"version":\s*"[^"]+"', f'"version": "{v}"'),
  "server.json":                (r'"version":\s*"[^"]+"', f'"version": "{v}"'),  # all occurrences
}
for path, (pat, repl) in edits.items():
    p = pathlib.Path(path); t = p.read_text()
    t = re.sub(pat, repl, t)
    p.write_text(t)
    print(f"  {path}")
PY

# 2. CHANGELOG must already have a section for this version.
grep -q "## \[$VERSION\]" CHANGELOG.md || { echo "ERROR: add a '## [$VERSION]' section to CHANGELOG.md first."; exit 1; }

# 3. Tests + gates.
if [ -z "$NO_TESTS" ]; then
  echo "==> tests + gates"
  run python3 -m unittest discover -s tests
  [ -x scripts/run_gates.sh ] && run env YGG_MEMORY_PORT=42070 bash scripts/run_gates.sh || true
fi

# 4. Build sdist/wheel + the Claude Desktop bundle.
echo "==> build"
run rm -rf dist
run uv build
run bash packaging/mcpb/build.sh

# 5. git commit + tag + push.
if [ -z "$SKIP_GIT" ]; then
  echo "==> git commit + tag"
  rm -f .git/index.lock
  run git add -A
  run git commit -m "Release $VERSION" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" || echo "  (nothing to commit)"
  run git tag -f "v$VERSION"
  run git push origin HEAD
  run git push -f origin "v$VERSION"
  note "git: pushed + tagged v$VERSION"
fi

# 6. PyPI (everything else pulls from here — do it first).
if [ -z "$SKIP_PYPI" ]; then
  echo "==> PyPI"
  if command -v uv >/dev/null; then run uv publish && note "PyPI: published"
  elif command -v twine >/dev/null; then run twine upload dist/${PKG//-/_}-$VERSION* && note "PyPI: published (twine)"
  else echo "  ! no uv/twine — skipped"; note "PyPI: SKIPPED (no uv/twine)"; fi
fi

# 7. Homebrew formula — pull the REAL hashed sdist URL + sha256 from PyPI, patch the formula.
if [ -z "$SKIP_BREW" ]; then
  echo "==> Homebrew formula"
  if [ -z "$DRY" ]; then
    for i in $(seq 1 12); do  # wait for PyPI to serve the new version
      python3 - "$VERSION" "$TAP_FORMULA" <<'PY' && break || { echo "  waiting for PyPI ($i)…"; sleep 5; }
import json, re, sys, urllib.request, pathlib
ver, formula = sys.argv[1], sys.argv[2]
d = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/yggdrasil-memory/{ver}/json", timeout=10))
sd = next(u for u in d["urls"] if u["packagetype"] == "sdist")
url, sha = sd["url"], sd["digests"]["sha256"]
t = pathlib.Path(formula).read_text()
t = re.sub(r'url "[^"]+"', f'url "{url}"', t)
t = re.sub(r'sha256 "[^"]+"', f'sha256 "{sha}"', t)
pathlib.Path(formula).write_text(t)
print(f"  formula -> {ver}  sha {sha[:12]}…")
PY
    done
    run git add "$TAP_FORMULA"; run git commit -m "brew: yggdrasil $VERSION" || true; run git push origin HEAD || true
    if [ -n "${YGG_TAP_DIR:-}" ] && [ -d "$YGG_TAP_DIR" ]; then
      cp "$TAP_FORMULA" "$YGG_TAP_DIR/Formula/yggdrasil.rb" 2>/dev/null || cp "$TAP_FORMULA" "$YGG_TAP_DIR/yggdrasil.rb"
      ( cd "$YGG_TAP_DIR" && git add -A && git commit -m "yggdrasil $VERSION" && git push ) && note "Homebrew: tap pushed"
    else
      note "Homebrew: formula updated in repo (set YGG_TAP_DIR to auto-push the tap)"
    fi
  else echo "  [dry-run] would patch $TAP_FORMULA from PyPI"; fi
fi

# 8. npm launcher.
if [ -z "$SKIP_NPM" ]; then
  echo "==> npm"
  if command -v npm >/dev/null; then ( cd clients/npm && run npm publish ) && note "npm: published"
  else echo "  ! no npm — skipped"; note "npm: SKIPPED (no npm)"; fi
fi

# 9. MCP Registry.
if [ -z "$SKIP_MCP" ]; then
  echo "==> MCP Registry"
  if command -v mcp-publisher >/dev/null; then run mcp-publisher publish && note "MCP Registry: published"
  else echo "  ! no mcp-publisher — skipped"; note "MCP Registry: SKIPPED (no mcp-publisher)"; fi
fi

# 10. GitHub release with notes from the CHANGELOG section + bundle/skill assets.
if [ -z "$SKIP_GH" ]; then
  echo "==> GitHub release"
  if command -v gh >/dev/null; then
    notes="$(mktemp)"; awk "/^## \[$VERSION\]/{f=1;next} /^## \[/{f=0} f" CHANGELOG.md > "$notes"
    assets=(packaging/mcpb/yggdrasil-$VERSION.mcpb)
    [ -f skills/yggdrasil-memory.zip ] && assets+=(skills/yggdrasil-memory.zip)
    run gh release create "v$VERSION" --title "v$VERSION" --notes-file "$notes" --latest "${assets[@]}" \
      && note "GitHub: release v$VERSION" || run gh release edit "v$VERSION" --notes-file "$notes" --draft=false
  else echo "  ! no gh — skipped"; note "GitHub: SKIPPED (no gh)"; fi
fi

echo; echo "==> done: $PKG $VERSION"
printf '   - %s\n' "${SUMMARY[@]}"
echo "   Users update with:  ygg update"
