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
  if [ -t 0 ]; then
    read -r -p "Proceed? [y/N]: " a; [[ "$a" =~ ^[Yy] ]] || { echo aborted; exit 1; }
  else
    echo "Non-interactive shell — re-run with --yes to proceed (this publishes for real)."; exit 1
  fi
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
  # agent-plugin manifests (all occurrences of "version" bumped together):
  ".claude-plugin/marketplace.json": (r'"version":\s*"[^"]+"', f'"version": "{v}"'),
  ".claude-plugin/plugin.json":      (r'"version":\s*"[^"]+"', f'"version": "{v}"'),
  ".codex-plugin/plugin.json":       (r'"version":\s*"[^"]+"', f'"version": "{v}"'),
  ".cursor-plugin/marketplace.json": (r'"version":\s*"[^"]+"', f'"version": "{v}"'),
  ".cursor-plugin/plugin.json":      (r'"version":\s*"[^"]+"', f'"version": "{v}"'),
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
# build the uploadable skill zip (gitignored — built fresh each release)
run bash -c 'cd skills && rm -f yggdrasil-memory.zip && zip -q -r -X yggdrasil-memory.zip yggdrasil-memory'

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

# 6. PyPI (everything else pulls from here — do it first). A failure is noted,
#    not fatal, so the summary still prints; brew is gated on PyPI succeeding.
PYPI_OK=
if [ -z "$SKIP_PYPI" ]; then
  echo "==> PyPI"
  if command -v uv >/dev/null; then
    if run uv publish; then PYPI_OK=1; note "PyPI: published"; else note "PyPI: FAILED (set UV_PUBLISH_TOKEN)"; fi
  elif command -v twine >/dev/null; then
    if run twine upload dist/${PKG//-/_}-$VERSION*; then PYPI_OK=1; note "PyPI: published (twine)"; else note "PyPI: FAILED"; fi
  else echo "  ! no uv/twine — skipped"; note "PyPI: SKIPPED (no uv/twine)"; fi
fi

# 7. Homebrew formula — pull the REAL hashed sdist URL + sha256 from PyPI, patch the formula.
#    Only runs if PyPI actually published this version (it reads PyPI for the sha).
if [ -z "$SKIP_BREW" ] && { [ -n "$PYPI_OK" ] || [ -n "$DRY" ]; }; then
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
      ( cd "$YGG_TAP_DIR" && git add -A && git commit -m "yggdrasil $VERSION" && git push ) && note "Homebrew: tap pushed (YGG_TAP_DIR)"
    elif command -v gh >/dev/null; then
      # No local tap clone — push the formula straight to the tap repo via the API
      # (otherwise the tap goes stale and `brew upgrade` never sees the new version).
      if tsha="$(gh api repos/VonderVuflya/homebrew-tap/contents/Formula/yggdrasil.rb --jq .sha 2>/dev/null)"; then
        if gh api --method PUT repos/VonderVuflya/homebrew-tap/contents/Formula/yggdrasil.rb \
             -f message="yggdrasil $VERSION" \
             -f content="$(base64 < "$TAP_FORMULA" | tr -d '\n')" -f sha="$tsha" >/dev/null 2>&1; then
          note "Homebrew: tap updated to $VERSION (gh api)"
        else note "Homebrew: tap push FAILED (gh api) — update VonderVuflya/homebrew-tap by hand"; fi
      else note "Homebrew: couldn't read the tap via gh — formula updated in repo only"; fi
    else
      note "Homebrew: formula updated in repo only (set YGG_TAP_DIR or install gh to push the tap)"
    fi
  else echo "  [dry-run] would patch $TAP_FORMULA from PyPI"; fi
fi

[ -z "$SKIP_BREW" ] && [ -z "$PYPI_OK" ] && [ -z "$DRY" ] && note "Homebrew: SKIPPED (PyPI not published)"

# 8. npm launcher.
if [ -z "$SKIP_NPM" ]; then
  echo "==> npm"
  if command -v npm >/dev/null; then
    if ( cd clients/npm && run npm publish ); then note "npm: published"; else note "npm: FAILED (npm login)"; fi
  else echo "  ! no npm — skipped"; note "npm: SKIPPED (no npm)"; fi
fi

# 9. MCP Registry — auth-aware. Unlike npm, mcp-publisher won't log in on its own
#    and dies on an expired JWT. The publish attempt IS the auth check: if it's
#    rejected for auth (missing/expired token), run `mcp-publisher login github`
#    (its device-flow blocks until you finish), then retry publish once.
if [ -z "$SKIP_MCP" ]; then
  echo "==> MCP Registry"
  if ! command -v mcp-publisher >/dev/null; then
    echo "  ! no mcp-publisher — skipped"; note "MCP Registry: SKIPPED (no mcp-publisher)"
  elif [ -n "$DRY" ]; then
    echo "  [dry-run] mcp-publisher publish (logs in via 'mcp-publisher login github' first if the token is missing/expired)"
    note "MCP Registry: published"
  elif out="$(mcp-publisher publish 2>&1)"; then
    echo "$out"; note "MCP Registry: published"
  elif printf '%s' "$out" | grep -qiE '401|403|unauthorized|expired|invalid.*token|no.*token|not.*logged|login'; then
    echo "$out"
    echo "  → MCP token missing/expired. Running: mcp-publisher login github"
    if mcp-publisher login github; then
      if mcp-publisher publish; then note "MCP Registry: published (after re-login)"
      else note "MCP Registry: FAILED (publish after login)"; fi
    else
      note "MCP Registry: FAILED (mcp-publisher login github)"
    fi
  else
    echo "$out"; note "MCP Registry: FAILED"
  fi
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
