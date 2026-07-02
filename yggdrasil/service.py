#!/usr/bin/env python3
"""Cross-platform service lifecycle for the Yggdrasil engine.

One Python implementation for macOS (launchd), Linux (systemd --user) and
Windows (Task Scheduler), plus a universal **lazy-spawn** fallback so the daemon
comes up on demand even when no OS service manager is available.

Because the engine is pure stdlib (zero deps), the daemon is deployed as plain
``.py`` files under ``~/.yggdrasil/scripts`` and run by a stable system Python —
so it works identically whether Yggdrasil was installed via uvx, pipx, pip or
Homebrew (the ephemeral uvx env is never depended on at runtime).

Shared steps (deploy / token / config / MCP registration / health) are
platform-agnostic; only the autostart unit differs per OS. Pure generators
(``launchd_plist`` / ``systemd_unit`` / ``schtasks_create_argv``) are unit-tested.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

YGG_HOME = Path(os.environ.get("YGG_HOME", str(Path.home() / ".yggdrasil")))
PORT = int(os.environ.get("YGG_PORT", "42069"))
URL = f"http://127.0.0.1:{PORT}"
PKG = Path(__file__).resolve().parent
SCRIPTS = YGG_HOME / "scripts"
DATA = YGG_HOME / "data"
LOGS = YGG_HOME / "logs"
DB = DATA / "memory.sqlite"
TOKEN_FILE = YGG_HOME / "token"
PIDFILE = YGG_HOME / "daemon.pid"
MARKER = YGG_HOME / "service.json"  # records which manager set up autostart
ENGINE_LOG = LOGS / "engine.log"

LABEL = os.environ.get("YGG_LABEL", "com.yggdrasil.memory")   # launchd label
UNIT = os.environ.get("YGG_UNIT", "yggdrasil")                # systemd unit name
TASK = os.environ.get("YGG_TASK", "Yggdrasil")               # Windows scheduled-task name


def current_os() -> str:
    return platform.system()  # 'Darwin' | 'Linux' | 'Windows'


def _python() -> str:
    return sys.executable or shutil.which("python3") or "python3"


def _engine_py() -> Path:
    return SCRIPTS / "ygg_memory_server.py"


def _mcp_py() -> Path:
    return SCRIPTS / "ygg_mcp_server.py"


def _mkdirs() -> None:
    for d in (SCRIPTS, DATA, LOGS):
        d.mkdir(parents=True, exist_ok=True)


def _config() -> dict:
    try:
        return json.loads((YGG_HOME / "config.json").read_text())
    except (OSError, ValueError):
        return {}


def token() -> str:
    return TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""


def ensure_token() -> str:
    YGG_HOME.mkdir(parents=True, exist_ok=True)
    if not TOKEN_FILE.exists():
        import secrets

        TOKEN_FILE.write_text(secrets.token_hex(24))
        try:
            os.chmod(TOKEN_FILE, 0o600)
        except OSError:
            pass
    return token()


def deploy_files() -> None:
    """Copy the zero-dep engine into ~/.yggdrasil/scripts (stable runtime location)."""
    _mkdirs()
    for p in PKG.glob("*.py"):
        shutil.copy2(p, SCRIPTS / p.name)
    hooks = PKG / "hooks"
    if hooks.is_dir():
        (SCRIPTS / "hooks").mkdir(exist_ok=True)
        for p in hooks.glob("*.py"):
            shutil.copy2(p, SCRIPTS / "hooks" / p.name)


def engine_argv(tok: str, embed_model: str = "") -> list[str]:  # noqa: ARG001 — tok kept for API/callers
    # Pass the token by FILE path, never by value, so the secret never lands in
    # `ps` output or the launchd plist / systemd unit. The engine reads the 0600
    # token file itself. (`tok` is accepted for call-site compatibility.)
    argv = [_python(), str(_engine_py()), "--db", str(DB), "--port", str(PORT),
            "--token-file", str(TOKEN_FILE)]
    if embed_model:
        argv += ["--embed-model", embed_model]
    return argv


# --------------------------------------------------------------------------- #
# Health / lazy-spawn (universal — no OS service manager required)
# --------------------------------------------------------------------------- #

def health(timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"{URL}/health", timeout=timeout) as r:
            return json.load(r)
    except Exception:  # noqa: BLE001
        return None


def _spawn_detached(argv: list[str]) -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    logf = open(ENGINE_LOG, "a")  # noqa: SIM115 (kept open for the daemon's lifetime)
    kwargs: dict = {"stdout": logf, "stderr": logf, "stdin": subprocess.DEVNULL}
    if current_os() == "Windows":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        kwargs["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(argv, **kwargs)  # noqa: S603
    try:
        PIDFILE.write_text(str(proc.pid))
    except OSError:
        pass
    return proc.pid


def ensure_running(embed_model: str | None = None, wait: float = 12.0) -> bool:
    """Start the daemon if it isn't already reachable. The universal safety net:
    works on any OS, with or without a configured service. Idempotent."""
    if health():
        return True
    if not _engine_py().exists():
        deploy_files()
    tok = token() or ensure_token()
    embed = embed_model if embed_model is not None else _config().get("embed_model", "")
    _spawn_detached(engine_argv(tok, embed or ""))
    deadline = wait
    waited = 0.0
    while waited < deadline:
        if health():
            return True
        time.sleep(0.25)
        waited += 0.25
    return False


def _port_listening() -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Pure unit/command generators (unit-tested)
# --------------------------------------------------------------------------- #

def launchd_plist(argv: list[str]) -> str:
    args = "\n".join(f"    <string>{a}</string>" for a in argv)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n'
        f"  <key>Label</key><string>{LABEL}</string>\n"
        "  <key>ProgramArguments</key>\n  <array>\n"
        f"{args}\n  </array>\n"
        "  <key>RunAtLoad</key><true/>\n"
        "  <key>KeepAlive</key><true/>\n"
        f"  <key>StandardOutPath</key><string>{ENGINE_LOG}</string>\n"
        f"  <key>StandardErrorPath</key><string>{ENGINE_LOG}</string>\n"
        "</dict>\n</plist>\n"
    )


def systemd_unit(argv: list[str]) -> str:
    exec_start = " ".join(_sh_quote(a) for a in argv)
    return (
        "[Unit]\n"
        "Description=Yggdrasil memory engine\n"
        "After=network.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={exec_start}\n"
        "Restart=always\n"
        "RestartSec=2\n"
        f"StandardOutput=append:{ENGINE_LOG}\n"
        f"StandardError=append:{ENGINE_LOG}\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def schtasks_create_argv(argv: list[str]) -> list[str]:
    # /tr must be a single string; quote the whole command line for schtasks.
    tr = " ".join(_win_quote(a) for a in argv)
    return ["schtasks", "/create", "/tn", TASK, "/sc", "onlogon", "/rl", "limited", "/f", "/tr", tr]


def _sh_quote(s: str) -> str:
    import shlex

    return shlex.quote(s)


def _win_quote(s: str) -> str:
    return f'"{s}"' if (" " in s or "\\" in s) else s


def _win_pythonw(py: str) -> str:
    """Prefer pythonw.exe (no console window) next to the interpreter."""
    p = Path(py)
    cand = p.with_name("pythonw.exe")
    return str(cand) if cand.exists() else py


# --------------------------------------------------------------------------- #
# MCP registration (shared, OS-agnostic — uses the agent CLIs if present)
# --------------------------------------------------------------------------- #

def claude_json_entry() -> dict:
    """The MCP server entry as it should appear in ~/.claude.json.

    Deliberately NO token in the entry: ~/.claude.json is a world-readable-ish
    config other tools sync and back up. ygg_core resolves the token from the
    0600 ~/.yggdrasil/token file at call time — the secret stays in one place.
    """
    return {
        "type": "stdio",
        "command": _python(),
        "args": [str(_mcp_py())],
        "env": {"YGG_ENGINE_URL": URL},
    }


def _register_claude_json() -> bool:
    """Write the MCP server straight into ~/.claude.json.

    Covers Claude Code running as a **VSCode/Cursor extension**, where there is
    no ``claude`` binary on PATH for ``claude mcp add`` to use. Merges into the
    existing config (with a ``.ygg.bak`` backup) so other settings are preserved.
    Returns False when there's no sign Claude Code is installed.
    """
    path = Path.home() / ".claude.json"
    if not path.exists() and not (Path.home() / ".claude").is_dir():
        return False
    try:
        cfg = json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        return False
    if not isinstance(cfg, dict):
        return False
    if path.exists():
        try:
            shutil.copy2(path, str(path) + ".ygg.bak")
        except OSError:
            pass
    cfg.setdefault("mcpServers", {})["yggdrasil"] = claude_json_entry()
    try:
        path.write_text(json.dumps(cfg, indent=2))
    except OSError:
        return False
    return True


def register_mcp() -> list[str]:
    # No YGG_ENGINE_TOKEN in the registrations: the agent configs (~/.claude.json,
    # Codex config) would persist the secret in plaintext. ygg_core reads the
    # 0600 ~/.yggdrasil/token file itself when the env var is absent.
    mcp = str(_mcp_py())
    py = _python()
    done = []
    if shutil.which("claude"):
        subprocess.run(["claude", "mcp", "remove", "yggdrasil", "-s", "user"],
                       capture_output=True)
        r = subprocess.run(
            ["claude", "mcp", "add", "yggdrasil", "-s", "user",
             "-e", f"YGG_ENGINE_URL={URL}",
             "--", py, mcp],
            capture_output=True, text=True)
        if r.returncode == 0:
            done.append("Claude Code")
    # Binary-less Claude Code (VSCode/Cursor extension): write ~/.claude.json directly.
    if not any(d.startswith("Claude Code") for d in done) and _register_claude_json():
        done.append("Claude Code (~/.claude.json)")
    if shutil.which("codex"):
        subprocess.run(["codex", "mcp", "remove", "yggdrasil"], capture_output=True)
        r = subprocess.run(
            ["codex", "mcp", "add", "yggdrasil",
             "--env", f"YGG_ENGINE_URL={URL}",
             "--", py, mcp],
            capture_output=True, text=True)
        if r.returncode == 0:
            done.append("Codex")
    return done


def unregister_mcp() -> None:
    if shutil.which("claude"):
        subprocess.run(["claude", "mcp", "remove", "yggdrasil", "-s", "user"], capture_output=True)
    if shutil.which("codex"):
        subprocess.run(["codex", "mcp", "remove", "yggdrasil"], capture_output=True)
    # Drop the direct ~/.claude.json entry if we wrote one.
    path = Path.home() / ".claude.json"
    if path.exists():
        try:
            cfg = json.loads(path.read_text())
            if isinstance(cfg, dict) and "yggdrasil" in cfg.get("mcpServers", {}):
                del cfg["mcpServers"]["yggdrasil"]
                path.write_text(json.dumps(cfg, indent=2))
        except (OSError, ValueError):
            pass


# --------------------------------------------------------------------------- #
# Per-OS autostart install/start/stop
# --------------------------------------------------------------------------- #

def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def _install_launchd(argv: list[str]) -> str:
    p = _launchd_plist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["launchctl", "bootout", f"{_launchd_domain()}/{LABEL}"], capture_output=True)
    p.write_text(launchd_plist(argv))
    if subprocess.run(["launchctl", "bootstrap", _launchd_domain(), str(p)],
                      capture_output=True).returncode != 0:
        subprocess.run(["launchctl", "load", "-w", str(p)], capture_output=True)
    return "launchd"


def _install_systemd(argv: list[str]) -> str | None:
    if not shutil.which("systemctl"):
        return None
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / f"{UNIT}.service").write_text(systemd_unit(argv))
    env = dict(os.environ)
    r1 = subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, env=env)
    r2 = subprocess.run(["systemctl", "--user", "enable", "--now", f"{UNIT}.service"],
                        capture_output=True, env=env)
    if r1.returncode == 0 and r2.returncode == 0:
        return "systemd"
    return None  # caller falls back to lazy-spawn


def _install_schtasks(argv: list[str]) -> str | None:
    if not shutil.which("schtasks"):
        return None
    win_argv = [_win_pythonw(argv[0])] + argv[1:]
    r = subprocess.run(schtasks_create_argv(win_argv), capture_output=True, text=True)
    if r.returncode == 0:
        return "schtasks"
    return None


def _record_manager(manager: str) -> None:
    try:
        MARKER.write_text(json.dumps({"manager": manager}))
    except OSError:
        pass


def _manager() -> str:
    try:
        return json.loads(MARKER.read_text()).get("manager", "lazy")
    except (OSError, ValueError):
        return "lazy"


# --------------------------------------------------------------------------- #
# Public lifecycle
# --------------------------------------------------------------------------- #

def install(embed_model: str = "", bg_model: str = "", enable_hooks: bool = False,
            enable_stop: bool = False) -> int:
    print(f"==> installing into {YGG_HOME} ({current_os()})")
    deploy_files()
    tok = ensure_token()
    # Merge (don't clobber) — preserves the wizard's `features` block etc.
    cfg_path = YGG_HOME / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text())
        if not isinstance(cfg, dict):
            cfg = {}
    except (OSError, ValueError):
        cfg = {}
    cfg.update({"embed_model": embed_model, "bg_model": bg_model})
    cfg_path.write_text(json.dumps(cfg, indent=2))

    wanted = [m for m in (embed_model, bg_model) if m]
    if wanted:
        if shutil.which("ollama"):
            for m in wanted:
                print(f"    pulling model: {m} (this can take a while) ...")
                if subprocess.run(["ollama", "pull", m]).returncode != 0:
                    print(f"    WARNING: `ollama pull {m}` failed — semantic search stays "
                          f"lexical-only until it's pulled. Re-run: ollama pull {m} && ygg restart")
        else:
            print("    WARNING: models were selected but `ollama` is not installed,")
            print("    so they were NOT downloaded — Yggdrasil runs in lexical-only mode.")
            print("    Install Ollama (https://ollama.com), then:")
            for m in wanted:
                print(f"      ollama pull {m}")
            print("      ygg restart")

    argv = engine_argv(tok, embed_model)
    osname = current_os()
    manager = None
    if osname == "Darwin":
        manager = _install_launchd(argv)
    elif osname == "Linux":
        manager = _install_systemd(argv)
    elif osname == "Windows":
        manager = _install_schtasks(argv)

    if manager:
        _record_manager(manager)
        print(f"    autostart configured via {manager}")
    else:
        _record_manager("lazy")
        print("    no service manager available — using lazy-spawn (daemon starts on demand)")

    # Make sure it's actually running now. If a manager is active, give it a
    # moment to bring the daemon up before falling back to a lazy spawn (avoids
    # a second process racing for the port).
    started = False
    if manager:
        for _ in range(16):  # ~4s
            if health():
                started = True
                break
            time.sleep(0.25)
    if not started and not ensure_running(embed_model):
        print("    WARNING: engine did not become healthy; check logs:", ENGINE_LOG)

    agents = register_mcp()
    if agents:
        print(f"    registered MCP with: {', '.join(agents)}")
    else:
        print("    WARNING: no agent host found to register the MCP server with —")
        print("    the agent has no ygg_* tools yet. If you use Claude Code (incl. the")
        print("    VSCode/Cursor extension), add this to \"mcpServers\" in ~/.claude.json,")
        print("    then restart the editor:")
        print(json.dumps({"yggdrasil": claude_json_entry()}, indent=2))

    if enable_hooks:
        enable_session_hook()
    if enable_stop:
        enable_stop_hook()

    h = health()
    print(f"==> health: {h}")
    print(f"==> installed. Engine on {URL}; "
          + ("auto-starts at login + restarts on crash."
             if manager != "lazy" else "starts on demand (no boot service)."))
    return 0 if h else 1


def start() -> int:
    mgr = _manager()
    if mgr == "launchd":
        p = _launchd_plist_path()
        if subprocess.run(["launchctl", "bootstrap", _launchd_domain(), str(p)],
                          capture_output=True).returncode != 0:
            subprocess.run(["launchctl", "load", "-w", str(p)], capture_output=True)
    elif mgr == "systemd":
        subprocess.run(["systemctl", "--user", "start", f"{UNIT}.service"], capture_output=True)
    elif mgr == "schtasks":
        subprocess.run(["schtasks", "/run", "/tn", TASK], capture_output=True)
    ok = ensure_running()
    print("started" if ok else "failed to start (see logs)")
    return 0 if ok else 1


def stop() -> int:
    mgr = _manager()
    if mgr == "launchd":
        subprocess.run(["launchctl", "bootout", f"{_launchd_domain()}/{LABEL}"], capture_output=True)
    elif mgr == "systemd":
        subprocess.run(["systemctl", "--user", "stop", f"{UNIT}.service"], capture_output=True)
    elif mgr == "schtasks":
        subprocess.run(["schtasks", "/end", "/tn", TASK], capture_output=True)
    _kill_pidfile()
    print("stopped")
    return 0


def _kill_pidfile() -> None:
    try:
        pid = int(PIDFILE.read_text().strip())
    except (OSError, ValueError):
        return
    try:
        if current_os() == "Windows":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        else:
            os.kill(pid, 15)
    except (OSError, ProcessLookupError):
        pass


def restart() -> int:
    stop()
    time.sleep(1)
    return start()


def status() -> int:
    h = health()
    print(f"manager: {_manager()}")
    print(f"port {PORT} listening: {_port_listening()}")
    print(f"health: {h if h else 'down'}")
    return 0 if h else 1


def logs(lines: int = 40) -> int:
    if not ENGINE_LOG.exists():
        print("(no log yet)")
        return 0
    tail = ENGINE_LOG.read_text(errors="replace").splitlines()[-lines:]
    print("\n".join(tail))
    return 0


def uninstall() -> int:
    mgr = _manager()
    if mgr == "launchd":
        subprocess.run(["launchctl", "bootout", f"{_launchd_domain()}/{LABEL}"], capture_output=True)
        _launchd_plist_path().unlink(missing_ok=True)
    elif mgr == "systemd":
        subprocess.run(["systemctl", "--user", "disable", "--now", f"{UNIT}.service"],
                       capture_output=True)
        (Path.home() / ".config" / "systemd" / "user" / f"{UNIT}.service").unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    elif mgr == "schtasks":
        subprocess.run(["schtasks", "/delete", "/tn", TASK, "/f"], capture_output=True)
    _kill_pidfile()
    unregister_mcp()
    print(f"uninstalled service + MCP registration. Data kept at {YGG_HOME} (rm -rf to remove).")
    return 0


# --------------------------------------------------------------------------- #
# SessionStart hook (Claude Code) — cross-platform, edits ~/.claude/settings.json
# --------------------------------------------------------------------------- #

def _hook_command() -> str:
    return f"{_python()} {SCRIPTS / 'hooks' / 'ygg_session_start.py'}"


# The two retrieval hooks installed by `ygg hooks`: SessionStart injects this
# project's memory at the top of a session; UserPromptSubmit auto-recalls
# relevant memory for EVERY request (so the agent can't forget to look it up).
_RETRIEVAL_HOOKS = [
    ("SessionStart", "ygg_session_start.py"),
    ("UserPromptSubmit", "ygg_user_prompt.py"),
]


def enable_session_hook() -> int:
    path = Path.home() / ".claude" / "settings.json"
    cfg = {}
    if path.exists():
        try:
            cfg = json.loads(path.read_text())
        except ValueError:
            cfg = {}
        shutil.copy2(path, str(path) + ".ygg.bak")
    added = []
    for event, script in _RETRIEVAL_HOOKS:
        cmd = f"{_python()} {SCRIPTS / 'hooks' / script}"
        groups = cfg.setdefault("hooks", {}).setdefault(event, [])
        if any(h.get("command") == cmd for g in groups for h in g.get("hooks", [])):
            continue
        groups.append({"hooks": [{"type": "command", "command": cmd}]})
        added.append(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2))
    print(f"enabled Yggdrasil hooks: {', '.join(added)}" if added
          else "Yggdrasil hooks already enabled")
    return 0


def disable_session_hook() -> int:
    path = Path.home() / ".claude" / "settings.json"
    if not path.exists():
        print("no settings.json")
        return 0
    try:
        cfg = json.loads(path.read_text())
    except ValueError:
        return 0
    for event, script in _RETRIEVAL_HOOKS:
        marker = str(SCRIPTS / "hooks" / script)
        groups = cfg.get("hooks", {}).get(event, [])
        cfg.setdefault("hooks", {})[event] = [
            g for g in groups if not any(marker in h.get("command", "") for h in g.get("hooks", []))
        ]
    path.write_text(json.dumps(cfg, indent=2))
    print("removed Yggdrasil hooks (SessionStart + UserPromptSubmit)")
    return 0


def _stop_hook_command() -> str:
    return f"{_python()} {SCRIPTS / 'hooks' / 'ygg_stop.py'}"


def enable_stop_hook() -> int:
    """Auto-distill each finished session into durable lessons (opt-in, local)."""
    path = Path.home() / ".claude" / "settings.json"
    cfg = {}
    if path.exists():
        try:
            cfg = json.loads(path.read_text())
        except ValueError:
            cfg = {}
        shutil.copy2(path, str(path) + ".ygg.bak")
    cmd = _stop_hook_command()
    grp = cfg.setdefault("hooks", {}).setdefault("Stop", [])
    if any(h.get("command") == cmd for g in grp for h in g.get("hooks", [])):
        print("Stop hook already enabled")
        return 0
    grp.append({"hooks": [{"type": "command", "command": cmd}]})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2))
    print("enabled Yggdrasil Stop hook — each session is distilled into lessons locally")
    return 0


def disable_stop_hook() -> int:
    path = Path.home() / ".claude" / "settings.json"
    if not path.exists():
        print("no settings.json")
        return 0
    try:
        cfg = json.loads(path.read_text())
    except ValueError:
        return 0
    marker = str(SCRIPTS / "hooks" / "ygg_stop.py")
    grp = cfg.get("hooks", {}).get("Stop", [])
    cfg.setdefault("hooks", {})["Stop"] = [
        g for g in grp if not any(marker in h.get("command", "") for h in g.get("hooks", []))
    ]
    path.write_text(json.dumps(cfg, indent=2))
    print("removed Yggdrasil Stop hook")
    return 0
