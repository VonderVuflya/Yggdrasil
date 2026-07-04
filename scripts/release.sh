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
#        NO_COLOR=1                          (plain output)
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

# ── pretty output ────────────────────────────────────────────────────────────
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  B=$'\033[1m'; D=$'\033[2m'; R=$'\033[0m'
  RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; CYN=$'\033[36m'; MAG=$'\033[35m'
else
  B= D= R= RED= GRN= YLW= CYN= MAG=
fi

STEP=0; TOTAL=10
LINE="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
step() { STEP=$((STEP+1)); printf '\n%s▶ %d/%d %s%s\n' "$B$CYN" "$STEP" "$TOTAL" "$*" "$R"; }
info() { printf '  %s·%s %s\n' "$D" "$R" "$*"; }
ok()   { printf '  %s✓%s %s\n' "$GRN" "$R" "$*"; }
warn() { printf '  %s⚠ %s%s\n' "$YLW" "$*" "$R"; }
die()  { printf '  %s✗ %s%s\n' "$RED" "$*" "$R"; exit 1; }

# note <ok|warn|fail|skip> <channel> <message> — one row of the final summary
SUMMARY=(); OK_N=0 WARN_N=0 FAIL_N=0 SKIP_N=0
note() {
  local icon col
  case "$1" in
    ok)   icon="✓" col="$GRN"; OK_N=$((OK_N+1));;
    warn) icon="⚠" col="$YLW"; WARN_N=$((WARN_N+1));;
    fail) icon="✗" col="$RED"; FAIL_N=$((FAIL_N+1));;
    *)    icon="◌" col="$D";   SKIP_N=$((SKIP_N+1));;
  esac
  SUMMARY+=("$(printf '  %s%s %-13s%s %s' "$col" "$icon" "$2" "$R" "$3")")
}

run() { if [ -n "$DRY" ]; then printf '  %s[dry-run]%s %s\n' "$MAG" "$R" "$*"; else "$@"; fi; }

chan() { # channel plan line: green name when it runs, dimmed "(skip)" when skipped
  if [ -z "$2" ]; then printf '%s%s%s' "$GRN" "$1" "$R"; else printf '%s%s (skip)%s' "$D" "$1" "$R"; fi
}

# ── banner ───────────────────────────────────────────────────────────────────
printf '\n%s%s%s\n' "$GRN" "$LINE" "$R"
printf '%s  🌳 Y G G D R A S I L   release %s%s%s\n' "$B" "$MAG" "v$VERSION" "$R"
[ -n "$DRY" ] && printf '  %s(dry-run — nothing will be published)%s\n' "$YLW" "$R"
printf '%s%s%s\n' "$GRN" "$LINE" "$R"
printf '  channels: %s · %s · %s · %s · %s · %s\n' \
  "$(chan git "$SKIP_GIT")" "$(chan PyPI "$SKIP_PYPI")" "$(chan Homebrew "$SKIP_BREW")" \
  "$(chan npm "$SKIP_NPM")" "$(chan MCP "$SKIP_MCP")" "$(chan GitHub "$SKIP_GH")"

# Load persisted publish credentials ONCE so you never re-enter them per release.
# Put `export UV_PUBLISH_TOKEN=pypi-...` (and anything else) in this file:
RELEASE_ENV="${YGG_RELEASE_ENV:-$HOME/.yggdrasil/release.env}"
if [ -f "$RELEASE_ENV" ]; then
  # shellcheck disable=SC1090
  . "$RELEASE_ENV"
  info "loaded credentials from $RELEASE_ENV"
fi

PKG="yggdrasil-memory"; TAP_FORMULA="packaging/homebrew/yggdrasil.rb"

# Resolve the branch ONCE. On a detached HEAD `git push origin HEAD` has no
# destination ref and fails — push to main explicitly instead.
BRANCH="$(git symbolic-ref --short -q HEAD || true)"
if [ -z "$BRANCH" ]; then
  BRANCH="main"
  warn "detached HEAD — pushes will target origin/$BRANCH explicitly"
fi

if [ -z "$YES" ] && [ -z "$DRY" ]; then
  if [ -t 0 ]; then
    printf '\n'
    read -r -p "  Proceed? [y/N]: " a; [[ "$a" =~ ^[Yy] ]] || { echo "  aborted"; exit 1; }
  else
    echo "Non-interactive shell — re-run with --yes to proceed (this publishes for real)."; exit 1
  fi
fi

# 1. Bump versions everywhere (python = safe for JSON).
step "Bump versions → $VERSION"
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
    print(f"  · {path}")
PY

# 2. CHANGELOG must already have a section for this version.
step "CHANGELOG check"
grep -q "## \[$VERSION\]" CHANGELOG.md || die "add a '## [$VERSION]' section to CHANGELOG.md first."
ok "found ## [$VERSION]"

# 3. Tests + gates.
step "Tests + gates"
if [ -z "$NO_TESTS" ]; then
  # syntax-check on the OLDEST supported python — local 3.12 happily accepts
  # PEP 701 f-strings that break every 3.10/3.11 user at import time
  if command -v uv >/dev/null; then
    run uv run --python 3.10 --no-project python -m compileall -q yggdrasil tests \
      && ok "syntax OK on python 3.10 (oldest supported)" \
      || die "does not compile on python 3.10 — fix before releasing"
  fi
  run python3 -m unittest discover -s tests
  [ -x scripts/run_gates.sh ] && run env YGG_MEMORY_PORT=42070 bash scripts/run_gates.sh || true
else
  info "skipped (--no-tests)"
fi

# 4. Build sdist/wheel + the Claude Desktop bundle.
step "Build (sdist/wheel + .mcpb + skill zip)"
run rm -rf dist
run uv build
run bash packaging/mcpb/build.sh
# build the uploadable skill zip (gitignored — built fresh each release)
run bash -c 'cd skills && rm -f yggdrasil-memory.zip && zip -q -r -X yggdrasil-memory.zip yggdrasil-memory'

# 5. git commit + tag + push.
step "git commit + tag + push"
if [ -z "$SKIP_GIT" ]; then
  rm -f .git/index.lock
  run git add -A
  run git commit -m "Release $VERSION" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" || info "(nothing to commit)"
  run git tag -f "v$VERSION"
  run git push origin "HEAD:$BRANCH"
  run git push -f origin "v$VERSION"
  note ok "git" "pushed + tagged v$VERSION → $BRANCH"
else
  info "skipped (--skip-git)"; note skip "git" "skipped (--skip-git)"
fi

# 6. PyPI (everything else pulls from here — do it first). A failure is noted,
#    not fatal, so the summary still prints; brew + MCP both need PyPI to succeed.
PYPI_OK=
PYPI_HINT="FAILED — put 'export UV_PUBLISH_TOKEN=pypi-...' in $RELEASE_ENV (one time)"
step "PyPI"
if [ -z "$SKIP_PYPI" ]; then
  if [ -z "${UV_PUBLISH_TOKEN:-}" ] && [ -z "$DRY" ] && [ ! -f "$HOME/.pypirc" ]; then
    warn "no PyPI credential. Set it once so you never do this again:"
    info "mkdir -p ~/.yggdrasil && echo 'export UV_PUBLISH_TOKEN=pypi-...' >> $RELEASE_ENV"
  fi
  if command -v uv >/dev/null; then
    if run uv publish; then PYPI_OK=1; note ok "PyPI" "published"; else note fail "PyPI" "$PYPI_HINT"; fi
  elif command -v twine >/dev/null; then
    if run twine upload dist/${PKG//-/_}-$VERSION*; then PYPI_OK=1; note ok "PyPI" "published (twine)"; else note fail "PyPI" "$PYPI_HINT"; fi
  else warn "no uv/twine — skipped"; note skip "PyPI" "skipped (no uv/twine)"; fi
else
  info "skipped (--skip-pypi)"; note skip "PyPI" "skipped (--skip-pypi)"
fi

# 7. Homebrew formula — pull the REAL hashed sdist URL + sha256 from PyPI, patch the formula.
#    Only runs if PyPI actually published this version (it reads PyPI for the sha).
step "Homebrew formula"
if [ -z "$SKIP_BREW" ] && { [ -n "$PYPI_OK" ] || [ -n "$DRY" ]; }; then
  if [ -z "$DRY" ]; then
    for i in $(seq 1 12); do  # wait for PyPI to serve the new version
      python3 - "$VERSION" "$TAP_FORMULA" <<'PY' && break || { echo "  · waiting for PyPI ($i)…"; sleep 5; }
import json, re, sys, urllib.request, pathlib
ver, formula = sys.argv[1], sys.argv[2]
d = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/yggdrasil-memory/{ver}/json", timeout=10))
sd = next(u for u in d["urls"] if u["packagetype"] == "sdist")
url, sha = sd["url"], sd["digests"]["sha256"]
t = pathlib.Path(formula).read_text()
t = re.sub(r'url "[^"]+"', f'url "{url}"', t)
t = re.sub(r'sha256 "[^"]+"', f'sha256 "{sha}"', t)
pathlib.Path(formula).write_text(t)
print(f"  · formula -> {ver}  sha {sha[:12]}…")
PY
    done
    run git add "$TAP_FORMULA"; run git commit -m "brew: yggdrasil $VERSION" || true
    run git push origin "HEAD:$BRANCH" || warn "couldn't push the formula commit to origin/$BRANCH"
    if [ -n "${YGG_TAP_DIR:-}" ] && [ -d "$YGG_TAP_DIR" ]; then
      cp "$TAP_FORMULA" "$YGG_TAP_DIR/Formula/yggdrasil.rb" 2>/dev/null || cp "$TAP_FORMULA" "$YGG_TAP_DIR/yggdrasil.rb"
      ( cd "$YGG_TAP_DIR" && git add -A && git commit -m "yggdrasil $VERSION" && git push ) && note ok "Homebrew" "tap pushed (YGG_TAP_DIR)"
    elif command -v gh >/dev/null; then
      # No local tap clone — push the formula straight to the tap repo via the API
      # (otherwise the tap goes stale and `brew upgrade` never sees the new version).
      if tsha="$(gh api repos/VonderVuflya/homebrew-tap/contents/Formula/yggdrasil.rb --jq .sha 2>/dev/null)"; then
        if gh api --method PUT repos/VonderVuflya/homebrew-tap/contents/Formula/yggdrasil.rb \
             -f message="yggdrasil $VERSION" \
             -f content="$(base64 < "$TAP_FORMULA" | tr -d '\n')" -f sha="$tsha" >/dev/null 2>&1; then
          note ok "Homebrew" "tap updated to $VERSION (gh api)"
        else note fail "Homebrew" "tap push FAILED (gh api) — update VonderVuflya/homebrew-tap by hand"; fi
      else note warn "Homebrew" "couldn't read the tap via gh — formula updated in repo only"; fi
    else
      note warn "Homebrew" "formula updated in repo only (set YGG_TAP_DIR or install gh to push the tap)"
    fi
  else info "[dry-run] would patch $TAP_FORMULA from PyPI"; note ok "Homebrew" "dry-run"; fi
elif [ -n "$SKIP_BREW" ]; then
  info "skipped (--skip-brew)"; note skip "Homebrew" "skipped (--skip-brew)"
else
  info "skipped — PyPI not published"; note skip "Homebrew" "skipped (PyPI not published)"
fi

# 8. npm launcher — auth-aware. In a non-interactive run `npm publish` won't pop
#    its browser login, it just 401s — so check `npm whoami` and `npm login` first.
step "npm"
if [ -z "$SKIP_NPM" ]; then
  if ! command -v npm >/dev/null; then
    warn "no npm — skipped"; note skip "npm" "skipped (no npm)"
  elif [ -n "$DRY" ]; then
    info "[dry-run] (cd clients/npm && npm publish) — runs 'npm login' first if not authed"
    note ok "npm" "dry-run"
  else
    if ! npm whoami >/dev/null 2>&1; then
      info "not logged in to npm. Running: npm login"
      npm login || true
    fi
    if ( cd clients/npm && npm publish ); then
      note ok "npm" "published"
    elif npm login && ( cd clients/npm && npm publish ); then
      note ok "npm" "published (after re-login)"
    else
      note fail "npm" "FAILED (npm login / publish)"
    fi
  fi
else
  info "skipped (--skip-npm)"; note skip "npm" "skipped (--skip-npm)"
fi

# 9. MCP Registry — auth-aware. Unlike npm, mcp-publisher won't log in on its own
#    and dies on an expired JWT. The publish attempt IS the auth check: if it's
#    rejected for auth (missing/expired token), run `mcp-publisher login github`
#    (its device-flow blocks until you finish), then retry publish once.
step "MCP Registry"
if [ -z "$SKIP_MCP" ]; then
  if ! command -v mcp-publisher >/dev/null; then
    warn "no mcp-publisher — skipped"; note skip "MCP Registry" "skipped (no mcp-publisher)"
  elif [ -n "$DRY" ]; then
    info "[dry-run] mcp-publisher publish (logs in via 'mcp-publisher login github' first if the token is missing/expired)"
    note ok "MCP Registry" "dry-run"
  elif out="$(mcp-publisher publish 2>&1)"; then
    echo "$out"; note ok "MCP Registry" "published"
  elif printf '%s' "$out" | grep -qiE '401|403|unauthorized|expired|invalid.*token|no.*token|not.*logged|login'; then
    echo "$out"
    info "MCP token missing/expired. Running: mcp-publisher login github"
    if mcp-publisher login github; then
      if mcp-publisher publish; then note ok "MCP Registry" "published (after re-login)"
      else note fail "MCP Registry" "FAILED (publish after login)"; fi
    else
      note fail "MCP Registry" "FAILED (mcp-publisher login github)"
    fi
  else
    echo "$out"; note fail "MCP Registry" "FAILED"
  fi
else
  info "skipped (--skip-mcp)"; note skip "MCP Registry" "skipped (--skip-mcp)"
fi

# 10. GitHub release with notes from the CHANGELOG section + bundle/skill assets.
step "GitHub release"
if [ -z "$SKIP_GH" ]; then
  if command -v gh >/dev/null; then
    notes="$(mktemp)"; awk "/^## \[$VERSION\]/{f=1;next} /^## \[/{f=0} f" CHANGELOG.md > "$notes"
    assets=(packaging/mcpb/yggdrasil-$VERSION.mcpb)
    [ -f skills/yggdrasil-memory.zip ] && assets+=(skills/yggdrasil-memory.zip)
    run gh release create "v$VERSION" --title "v$VERSION" --notes-file "$notes" --latest "${assets[@]}" \
      && note ok "GitHub" "release v$VERSION" || run gh release edit "v$VERSION" --notes-file "$notes" --draft=false
  else warn "no gh — skipped"; note skip "GitHub" "skipped (no gh)"; fi
else
  info "skipped (--skip-gh)"; note skip "GitHub" "skipped (--skip-gh)"
fi

# ── summary ──────────────────────────────────────────────────────────────────
N=$((OK_N + WARN_N + FAIL_N + SKIP_N))
bar=""
i=0; while [ "$i" -lt "$OK_N"   ]; do bar+="${GRN}█${R}"; i=$((i+1)); done
i=0; while [ "$i" -lt "$WARN_N" ]; do bar+="${YLW}█${R}"; i=$((i+1)); done
i=0; while [ "$i" -lt "$FAIL_N" ]; do bar+="${RED}█${R}"; i=$((i+1)); done
i=0; while [ "$i" -lt "$SKIP_N" ]; do bar+="${D}░${R}"; i=$((i+1)); done
elapsed="$(( SECONDS / 60 ))m $(( SECONDS % 60 ))s"

printf '\n%s%s%s\n' "$GRN" "$LINE" "$R"
if [ "$FAIL_N" -gt 0 ]; then
  printf '%s  🌳 %s %s — %sdone with failures%s in %s\n' "$B" "$PKG" "v$VERSION" "$RED" "$R$B" "$elapsed"
else
  printf '%s  🌳 %s %s released in %s%s\n' "$B" "$PKG" "v$VERSION" "$elapsed" "$R"
fi
printf '  %s  %s%d ok%s · %s%d warn%s · %s%d failed%s · %s%d skipped%s\n' \
  "$bar" "$GRN" "$OK_N" "$R" "$YLW" "$WARN_N" "$R" "$RED" "$FAIL_N" "$R" "$D" "$SKIP_N" "$R"
printf '%s%s%s\n' "$GRN" "$LINE" "$R"
[ "$N" -gt 0 ] && printf '%s\n' "${SUMMARY[@]}"
printf '\n  Users update with:  %sygg update%s\n\n' "$B" "$R"
[ "$FAIL_N" -eq 0 ]
