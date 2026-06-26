#!/usr/bin/env python3
"""`ygg` — the single entry point for Yggdrasil.

A thin dispatcher over the package modules. The Python components
(serve / mcp / setup / memory ops) run in-process; service lifecycle
(install / start / ...) delegates to the bundled ``install.sh``, which copies
the engine into ``~/.yggdrasil`` and wires up the launchd service + MCP
registration. Default install is zero-config and lexical-only — picking a local
model is an optional upgrade in ``ygg setup``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from shutil import which

from . import __version__

HERE = Path(__file__).resolve().parent
INSTALL_SH = HERE / "install.sh"
YGG_HOME = Path(os.environ.get("YGG_HOME", str(Path.home() / ".yggdrasil")))

USAGE = """\
ygg — one shared, durable memory for your AI coding agents

Setup & service:
  ygg install            Guided setup: hardware-aware models, background service, MCP registration
  ygg recommend          Show the hardware-aware model catalog
  ygg setup              Re-run the interactive setup wizard
  ygg doctor             Diagnose the installation (engine, models, MCP, hook)
  ygg update             Redeploy the current code into the running service
  ygg status | start | stop | restart | logs | token | uninstall
  ygg hooks | unhooks    Enable/disable the SessionStart auto-bootstrap hook
  ygg consolidate | unconsolidate

Run components directly:
  ygg serve [...]        Run the memory engine (HTTP, SQLite + FTS5)
  ygg mcp                Run the stdio MCP facade

Memory ops:
  ygg health
  ygg bootstrap --project P [--query Q]
  ygg search   --project P --query Q [--type T] [--limit N] [--json]
  ygg recall   --query Q [--type T] [--limit N] [--json]
  ygg remember --project P --type T --content "..."
  ygg materialize --id ID --project P

  ygg version
"""

SERVICE_CMDS = {
    "status", "start", "stop", "restart", "logs", "token",
    "uninstall", "hooks", "unhooks", "consolidate", "unconsolidate",
}
MEMORY_CMDS = {"health", "bootstrap", "search", "recall", "remember", "materialize", "pin", "unpin", "supersede"}


def _port() -> int:
    return int(os.environ.get("YGG_PORT", "42069"))


def _config() -> dict:
    try:
        return json.loads((YGG_HOME / "config.json").read_text())
    except (OSError, ValueError):
        return {}


def _install(rest: list[str]) -> int:
    """`ygg install` — interactive wizard on a TTY, else a zero-config lexical setup."""
    from . import service
    embed = bg = ""
    it = iter(rest)
    for a in it:
        if a == "--embed-model":
            embed = next(it, "")
        elif a == "--bg-model":
            bg = next(it, "")
    interactive = (sys.stdin.isatty() and os.environ.get("YGG_NONINTERACTIVE") != "1"
                   and not embed and not bg)
    if interactive:
        from . import ygg_setup
        sys.argv = ["ygg", "wizard"]
        rc = ygg_setup.main()  # wizard collects models, then calls service.install
    else:
        rc = service.install(embed, bg)
    print("\n--- ygg doctor ---")
    _doctor()  # always end install with the diagnostic checklist
    return rc


def _service(cmd: str, rest: list[str]) -> int:
    """Cross-platform service lifecycle (macOS launchd / Linux systemd / Windows schtasks)."""
    from . import service
    simple = {
        "start": service.start, "stop": service.stop, "restart": service.restart,
        "status": service.status, "uninstall": service.uninstall,
        "hooks": service.enable_session_hook, "unhooks": service.disable_session_hook,
    }
    if cmd in simple:
        return simple[cmd]()
    if cmd == "logs":
        return service.logs(int(os.environ.get("LINES", "40")))
    if cmd == "token":
        print(service.token() or "(no token — run: ygg install)")
        return 0
    if cmd in ("consolidate", "unconsolidate"):
        import platform as _pf
        if _pf.system() != "Darwin" or not INSTALL_SH.exists():
            print(f"`ygg {cmd}` (scheduled consolidation) is currently macOS-only.",
                  file=sys.stderr)
            return 1
        return subprocess.call(["bash", str(INSTALL_SH), cmd, *rest])
    return 2


def _ollama_models() -> list[str]:
    try:
        out = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5).stdout
        return [line.split()[0] for line in out.splitlines()[1:] if line.strip()]
    except (OSError, subprocess.SubprocessError):
        return []


def _mcp_registered(agent: str) -> bool:
    if which(agent) is None:
        return False
    try:
        out = subprocess.run([agent, "mcp", "list"], capture_output=True, text=True, timeout=10)
        return "yggdrasil" in (out.stdout + out.stderr)
    except (OSError, subprocess.SubprocessError):
        return False


def _doctor() -> int:
    ok = True
    url = f"http://127.0.0.1:{_port()}"
    print("Yggdrasil doctor\n")

    try:
        with urllib.request.urlopen(f"{url}/health", timeout=3) as r:
            print(f"  [ok] engine up on {url} — {json.load(r)}")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"  [!!] engine not reachable on {url} ({exc}). Try: ygg start")

    tok = YGG_HOME / "token"
    print(f"  [{'ok' if tok.exists() else '--'}] auth token: "
          f"{tok if tok.exists() else 'not generated (run: ygg install)'}")

    cfg = _config()
    embed, bg = cfg.get("embed_model") or "", cfg.get("bg_model") or ""
    print(f"  [{'ok' if embed else '--'}] embedding model: {embed or 'none (lexical-only mode)'}")
    print(f"  [{'ok' if bg else '--'}] background model: {bg or 'none (manual write-path)'}")

    if embed or bg:
        if which("ollama"):
            pulled = _ollama_models()
            for m in (embed, bg):
                if not m:
                    continue
                have = any(p.split(":")[0] == m.split(":")[0] for p in pulled)
                ok = ok and have
                print(f"  [{'ok' if have else '!!'}] ollama model '{m}': "
                      f"{'present' if have else 'NOT pulled (run: ollama pull ' + m + ')'}")
        else:
            ok = False
            print("  [!!] a model is configured but `ollama` is missing — see https://ollama.com")

    print(f"  [{'ok' if _mcp_registered('claude') else '--'}] Claude Code MCP registration")
    print(f"  [{'ok' if _mcp_registered('codex') else '--'}] Codex MCP registration")

    print("\n" + ("All good." if ok else "Some checks need attention (see [!!] above)."))
    return 0 if ok else 1


def _update() -> int:
    """Redeploy the current package code into ~/.yggdrasil."""
    from . import service
    cfg = _config()
    print("redeploying current code into ~/.yggdrasil ...")
    return service.install(cfg.get("embed_model", ""), cfg.get("bg_model", ""))


def main() -> int:
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "help"
    rest = argv[1:]

    if cmd in ("version", "--version", "-V"):
        print(f"yggdrasil {__version__}")
        return 0
    if cmd in ("help", "-h", "--help"):
        print(USAGE)
        return 0
    if cmd == "serve":
        from . import ygg_memory_server as m
        sys.argv = ["ygg serve", *rest]
        return m.main()
    if cmd == "mcp":
        from . import service
        service.ensure_running()  # lazy-spawn the engine on first MCP connection
        from . import ygg_mcp_server as m
        sys.argv = ["ygg mcp", *rest]
        return m.main()
    if cmd in ("setup", "wizard"):
        from . import ygg_setup as m
        sys.argv = ["ygg setup", "wizard", *rest]
        return m.main()
    if cmd in ("recommend", "hw"):
        from . import ygg_setup as m
        sys.argv = ["ygg", cmd, *rest]
        return m.main()
    if cmd in MEMORY_CMDS:
        from . import ygg as m
        sys.argv = ["ygg", cmd, *rest]
        return m.main()
    if cmd == "install":
        return _install(rest)
    if cmd == "ensure":
        from . import service
        return 0 if service.ensure_running() else 1
    if cmd == "doctor":
        return _doctor()
    if cmd == "update":
        return _update()
    if cmd in SERVICE_CMDS:
        return _service(cmd, rest)

    print(f"unknown command: {cmd}\n", file=sys.stderr)
    print(USAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
