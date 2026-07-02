#!/usr/bin/env bash
# Yggdrasil installer (macOS): run the memory engine as an always-on background
# service (launchd) and register the MCP facade with Claude Code and Codex, so
# any agent on this machine shares one durable memory — "install once, it just runs".
#
#   scripts/install.sh install [--embed-model all-minilm|paraphrase-multilingual] [--seed-db PATH]
#   scripts/install.sh status | start | stop | restart | logs | token | uninstall
#
# Layout: ~/.yggdrasil/{scripts,data,logs,token}. Token is generated, not hardcoded.
set -uo pipefail

YGG_HOME="${YGG_HOME:-$HOME/.yggdrasil}"
PORT="${YGG_PORT:-42069}"
LABEL="com.yggdrasil.memory"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
SRC_SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(command -v python3)"
URL="http://127.0.0.1:${PORT}"

cmd="${1:-install}"; shift || true
EMBED_MODEL=""; BG_MODEL=""; SEED_DB=""
while [ $# -gt 0 ]; do
  case "$1" in
    --embed-model) EMBED_MODEL="${2:-}"; shift 2;;
    --bg-model) BG_MODEL="${2:-}"; shift 2;;
    --seed-db) SEED_DB="${2:-}"; shift 2;;
    *) shift;;
  esac
done

domain="gui/$(id -u)"

_stop() {
  launchctl bootout "$domain/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
}

_start() {
  launchctl bootstrap "$domain" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST" 2>/dev/null || true
}

case "$cmd" in
  install)
    # Interactive, no model choice given -> run the guided wizard (which re-invokes
    # install with the chosen flags). Skipped when piped/non-interactive.
    if [ -t 0 ] && [ -z "$EMBED_MODEL" ] && [ -z "$BG_MODEL" ] && [ "${YGG_NONINTERACTIVE:-}" != "1" ]; then
      exec "$PYTHON" "$SRC_SCRIPTS/ygg_setup.py" wizard
    fi
    echo "==> installing into $YGG_HOME"
    mkdir -p "$YGG_HOME/scripts" "$YGG_HOME/data" "$YGG_HOME/logs"
    cp "$SRC_SCRIPTS"/*.py "$YGG_HOME/scripts/"
    [ -d "$SRC_SCRIPTS/hooks" ] && cp -R "$SRC_SCRIPTS/hooks" "$YGG_HOME/scripts/" 2>/dev/null || true

    if [ ! -f "$YGG_HOME/token" ]; then
      "$PYTHON" -c "import secrets;print(secrets.token_hex(24))" > "$YGG_HOME/token"
      chmod 600 "$YGG_HOME/token"
      echo "    generated auth token -> $YGG_HOME/token"
    fi

    # Pull chosen models (best-effort) and record the config for the write-path.
    for M in "$EMBED_MODEL" "$BG_MODEL"; do
      if [ -n "$M" ] && command -v ollama >/dev/null 2>&1; then
        echo "    pulling model: $M"
        ollama pull "$M" >/dev/null 2>&1 || echo "    (pull failed for $M — run 'ollama pull $M' later)"
      fi
    done
    "$PYTHON" - "$YGG_HOME/config.json" "$EMBED_MODEL" "$BG_MODEL" <<'PY'
import json, sys
path, embed, bg = sys.argv[1], sys.argv[2], sys.argv[3]
json.dump({"embed_model": embed, "bg_model": bg}, open(path, "w"), indent=2)
PY

    if [ -n "$SEED_DB" ] && [ -f "$SEED_DB" ]; then
      cp "$SEED_DB" "$YGG_HOME/data/memory.sqlite"
      echo "    seeded DB from $SEED_DB"
    fi

    # Build engine arguments (conditionally include the embedding model).
    EMBED_PLIST=""
    [ -n "$EMBED_MODEL" ] && EMBED_PLIST="    <string>--embed-model</string>
    <string>${EMBED_MODEL}</string>"

    _stop
    cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${YGG_HOME}/scripts/ygg_memory_server.py</string>
    <string>--db</string><string>${YGG_HOME}/data/memory.sqlite</string>
    <string>--port</string><string>${PORT}</string>
    <string>--token-file</string><string>${YGG_HOME}/token</string>
${EMBED_PLIST}
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${YGG_HOME}/logs/engine.log</string>
  <key>StandardErrorPath</key><string>${YGG_HOME}/logs/engine.log</string>
</dict>
</plist>
PLISTEOF
    _start
    sleep 2

    # Register the MCP facade with Claude Code and Codex (best-effort).
    # No YGG_ENGINE_TOKEN in the registrations: agent configs persist env vars in
    # plaintext; ygg_core reads the 0600 ~/.yggdrasil/token file itself.
    if command -v claude >/dev/null 2>&1; then
      claude mcp remove yggdrasil -s user >/dev/null 2>&1 || true
      claude mcp add yggdrasil -s user -e "YGG_ENGINE_URL=${URL}" \
        -- "$PYTHON" "$YGG_HOME/scripts/ygg_mcp_server.py" >/dev/null 2>&1 \
        && echo "    registered MCP with Claude Code" || echo "    (claude mcp add failed; register manually)"
    fi
    if command -v codex >/dev/null 2>&1; then
      codex mcp remove yggdrasil >/dev/null 2>&1 || true
      codex mcp add yggdrasil --env "YGG_ENGINE_URL=${URL}" \
        -- "$PYTHON" "$YGG_HOME/scripts/ygg_mcp_server.py" >/dev/null 2>&1 \
        && echo "    registered MCP with Codex" || echo "    (codex mcp add failed; register manually)"
    fi

    echo -n "==> health: "
    for _ in $(seq 1 60); do
      if "$PYTHON" -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('${URL}/health',timeout=2) else 1)" 2>/dev/null; then
        "$PYTHON" -c "import urllib.request,json;print(json.load(urllib.request.urlopen('${URL}/health')))"; break
      fi; sleep 0.5
    done
    echo "==> installed. Engine is on ${URL} and will auto-start at login + restart on crash."
    ;;

  status)
    launchctl print "$domain/$LABEL" 2>/dev/null | grep -E "state =|pid =" || echo "not loaded"
    "$PYTHON" -c "import urllib.request,json;print('health:',json.load(urllib.request.urlopen('${URL}/health',timeout=3)))" 2>/dev/null || echo "health: down"
    ;;
  start) _start; echo "started";;
  stop) _stop; echo "stopped";;
  restart) _stop; sleep 1; _start; echo "restarted";;
  logs) tail -n "${LINES:-40}" "$YGG_HOME/logs/engine.log";;
  token) cat "$YGG_HOME/token";;
  recommend) "$PYTHON" "$SRC_SCRIPTS/ygg_setup.py" recommend;;
  hooks)
    HOOK_CMD="${PYTHON} ${YGG_HOME}/scripts/hooks/ygg_session_start.py"
    "$PYTHON" - "$HOME/.claude/settings.json" "$HOOK_CMD" <<'PY'
import json, os, shutil, sys
path, cmd = sys.argv[1], sys.argv[2]
cfg = json.load(open(path)) if os.path.exists(path) else {}
ss = cfg.setdefault("hooks", {}).setdefault("SessionStart", [])
if any(h.get("command") == cmd for g in ss for h in g.get("hooks", [])):
    print("SessionStart hook already enabled"); sys.exit(0)
if os.path.exists(path):
    shutil.copy(path, path + ".ygg.bak")
ss.append({"hooks": [{"type": "command", "command": cmd}]})
json.dump(cfg, open(path, "w"), indent=2)
print("enabled Yggdrasil SessionStart hook (backup: ~/.claude/settings.json.ygg.bak)")
PY
    ;;
  unhooks)
    "$PYTHON" - "$HOME/.claude/settings.json" "${YGG_HOME}/scripts/hooks/ygg_session_start.py" <<'PY'
import json, os, sys
path, marker = sys.argv[1], sys.argv[2]
if not os.path.exists(path):
    print("no settings.json"); sys.exit(0)
cfg = json.load(open(path))
ss = cfg.get("hooks", {}).get("SessionStart", [])
cfg.setdefault("hooks", {})["SessionStart"] = [
    g for g in ss if not any(marker in h.get("command", "") for h in g.get("hooks", []))
]
json.dump(cfg, open(path, "w"), indent=2)
print("removed Yggdrasil SessionStart hook")
PY
    ;;
  consolidate)
    CLABEL="com.yggdrasil.consolidate"
    CPLIST="$HOME/Library/LaunchAgents/${CLABEL}.plist"
    INTERVAL="${YGG_CONSOLIDATE_INTERVAL:-86400}"
    CUSER="${YGG_CONS_USER:-demo-user}"
    CNS="${YGG_CONS_NS:-yggdrasil-demo}"
    # SAFE DEFAULT: propose only (detect + log candidates, archive nothing). A
    # small local model confidently mislabels distinct-but-similar lessons, so
    # auto-archiving is opt-in (YGG_CONSOLIDATE_APPLY=1) and best with a strong model.
    APPLY_ARG=""
    [ "${YGG_CONSOLIDATE_APPLY:-0}" = "1" ] && APPLY_ARG="    <string>--apply</string>"
    cat > "$CPLIST" <<PEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${CLABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${YGG_HOME}/scripts/ygg_writepath.py</string>
${APPLY_ARG}
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <!-- No YGG_ENGINE_TOKEN here: this plist is world-readable (644); the
         write-path resolves the token from the 0600 ~/.yggdrasil/token file. -->
    <key>YGG_ENGINE_URL</key><string>${URL}</string>
    <key>YGG_USER_ID</key><string>${CUSER}</string>
    <key>YGG_NAMESPACE</key><string>${CNS}</string>
  </dict>
  <key>StartInterval</key><integer>${INTERVAL}</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>${YGG_HOME}/logs/consolidate.log</string>
  <key>StandardErrorPath</key><string>${YGG_HOME}/logs/consolidate.log</string>
</dict>
</plist>
PEOF
    launchctl bootout "$domain/$CLABEL" 2>/dev/null || true
    launchctl bootstrap "$domain" "$CPLIST" 2>/dev/null || launchctl load -w "$CPLIST" 2>/dev/null || true
    echo "scheduled auto-consolidation every ${INTERVAL}s (logs: $YGG_HOME/logs/consolidate.log)"
    ;;
  unconsolidate)
    CLABEL="com.yggdrasil.consolidate"
    launchctl bootout "$domain/$CLABEL" 2>/dev/null || launchctl unload "$HOME/Library/LaunchAgents/${CLABEL}.plist" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/${CLABEL}.plist"
    echo "removed scheduled auto-consolidation"
    ;;
  uninstall)
    _stop; rm -f "$PLIST"
    launchctl bootout "$domain/com.yggdrasil.consolidate" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/com.yggdrasil.consolidate.plist"
    command -v claude >/dev/null 2>&1 && claude mcp remove yggdrasil -s user >/dev/null 2>&1 || true
    command -v codex  >/dev/null 2>&1 && codex mcp remove yggdrasil >/dev/null 2>&1 || true
    echo "uninstalled service + MCP registration. Data kept at $YGG_HOME (rm -rf to remove)."
    ;;
  *) echo "usage: install.sh {install|recommend|status|start|stop|restart|logs|token|hooks|unhooks|consolidate|unconsolidate|uninstall}"; exit 2;;
esac
