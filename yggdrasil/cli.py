#!/usr/bin/env python3
"""`ygg` — the single entry point for Yggdrasil.

A thin dispatcher over the package modules. The Python components
(serve / mcp / setup / memory ops) run in-process; service lifecycle
(install / start / ...) goes through ``service.py`` — cross-platform
(launchd / systemd / schtasks + lazy-spawn), deploys the engine into
``~/.yggdrasil`` and wires up MCP registration. Only the macOS-only
``consolidate`` schedule still shells out to the bundled ``install.sh``.
Default install is zero-config and lexical-only — picking a local model
is an optional upgrade in ``ygg setup``.
"""

from __future__ import annotations

import json
import os
import re
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
  ygg register           (Re)register the MCP server with Claude Code / Codex
  ygg reindex            Backfill embeddings for memories missing them (dense recall)
  ygg config             Show/set persistent settings (list [-v] | edit | get | set | unset)
  ygg update             Upgrade to the latest published version, then redeploy
  ygg redeploy           Redeploy the installed code into the daemon (no upgrade)
  ygg status | start | stop | restart | logs | token | uninstall
  ygg hooks | unhooks    Enable/disable the retrieval hooks (SessionStart bootstrap + per-prompt auto-recall)
  ygg stophooks | unstophooks  Enable/disable the Stop hook (auto-distill sessions → lessons)
  ygg consolidate | unconsolidate

Run components directly:
  ygg serve [...]        Run the memory engine (HTTP, SQLite + FTS5)
  ygg mcp                Run the stdio MCP facade (local CLI hosts)
  ygg mcp-http           Run the Streamable-HTTP MCP facade (remote / cross-surface)

Cold start (seed memory from your existing work):
  ygg stats              Overview of what's in memory (project × type × scope)
  ygg seed [--dry-run|--force]  Distill new/edited chats into memory (incremental, local)
  ygg seed --schedule 03:30     Nightly auto-distill (off/status to manage)
  ygg distill --source P Distill one dir/file into atomic lessons (local Ollama model)
  ygg sync [--repo R]    Sync memory across machines through YOUR git repo (no cloud)

Memory ops:
  ygg health
  ygg bootstrap --project P [--query Q]
  ygg search   --project P --query Q [--type T] [--limit N] [--json]
  ygg recall   --query Q [--type T] [--limit N] [--json]
  ygg remember --project P --type T --content "..."
  ygg materialize --id ID --project P
  ygg export-native --project P [--out AGENTS.md]   Write a curated digest into AGENTS.md/MEMORY.md (feeds the native memory)
  ygg import --from mcp-memory|basic-memory --path P   Migrate FROM another memory tool (then delete it)
  ygg review [--apply] [--project P]   Work the governance queue: consolidate duplicates, flag stale/conflicts (archives, reversible)
  ygg delete --id ID       Hard-delete ONE memory (irreversible; prefer supersede)
  ygg reset --project P | --source S | --all   Bulk hard-delete (undo a bad seed; confirms first)

  ygg version
"""

SERVICE_CMDS = {
    "status", "start", "stop", "restart", "logs", "token",
    "uninstall", "hooks", "unhooks", "stophooks", "unstophooks",
    "consolidate", "unconsolidate",
}
MEMORY_CMDS = {"health", "bootstrap", "search", "recall", "remember", "materialize",
               "pin", "unpin", "supersede", "delete", "reset", "export-native", "review",
               "import", "relate", "relations", "quality", "migrate"}


def _is_hosted(url: str) -> bool:
    """True when this endpoint is somebody else's server, so it needs a key.

    Anything on the loopback or a private LAN address is your own box (Ollama,
    llama.cpp, a desktop down the hall) and authenticates nothing.
    """
    host = (url or "").split("//")[-1].split("/")[0].split(":")[0].lower()
    if not host or host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):  # noqa: S104
        return False
    if host.endswith(".local") or host.startswith(("192.168.", "10.", "172.16.")):
        return False
    return "." in host          # a real hostname -> off-machine


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
        if not embed and not bg:
            # Non-TTY (piped / CI / `YGG_NONINTERACTIVE=1`) with no model flags:
            # we can't run the model-picker wizard, so this is a zero-config,
            # lexical-only install. Say so, so it isn't a silent surprise.
            print("ygg install: non-interactive — setting up zero-config, lexical-only "
                  "(no embedding model).\n  Add semantic search later with:  ygg setup   "
                  "(or:  ygg install --embed-model paraphrase-multilingual)")
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
        "stophooks": service.enable_stop_hook, "unstophooks": service.disable_stop_hook,
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
    try:
        from . import ygg_ui
    except ImportError:  # flat layout
        import ygg_ui
    import time as _time
    try:
        from . import ygg_config as C
    except ImportError:  # pragma: no cover — flat deploy
        import ygg_config as C  # type: ignore
    p = ygg_ui.palette()
    ok = True
    url = f"http://127.0.0.1:{_port()}"

    def check(state, label, detail="", fix=""):
        mark = (ygg_ui.mark_ok(p) if state is True
                else ygg_ui.mark_fail(p) if state is False else ygg_ui.mark_warn(p))
        print(f"  {mark} {label.ljust(16)}  {p.dim(detail)}".rstrip())
        if fix:
            print(f"     {p.dim('→ fix: ' + fix)}")

    t0 = _time.monotonic()
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=3) as r:
            h = json.load(r)
        ms = int((_time.monotonic() - t0) * 1000)
        print(f"🌳 {p.bold('Yggdrasil doctor')}   {p.dim(f'{__version__} · engine {ms}ms')}\n")
        check(True, "engine", f"{url} · {h.get('memory_count', '?')} memories · {h.get('storage', '?')}")
        if h.get("embeddings_missing"):
            ok = False
            check(False, "dense", f"{h['embeddings_missing']} memories have no current embedding", "ygg reindex")
        elif h.get("dense", "").startswith("active"):
            check(True, "dense", h["dense"])
        if h.get("scale_hint"):
            check(None, "scale", h["scale_hint"])
        # A hosted backend with no key fails at request time, deep inside the
        # daemon, where the user never sees it — dense just quietly stops
        # working. Catch the misconfiguration here, where they're already looking.
        for kind, url_key, key_key, cmd in (
            ("embeddings", "embed_url", "embed_api_key", "embed_api_key"),
            ("distill", "distill_url", "distill_api_key", "distill_api_key"),
        ):
            endpoint = C.resolve(url_key)
            if not _is_hosted(endpoint):
                continue
            if C.resolve(key_key):
                check(True, f"{kind} key", f"set for {endpoint}")
            else:
                ok = False
                check(False, f"{kind} key", f"{endpoint} is hosted but no key is set",
                      f"ygg config set {cmd} <key>")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"🌳 {p.bold('Yggdrasil doctor')}\n")
        check(False, "engine", f"not reachable on {url} ({exc})", "ygg start")

    tok = YGG_HOME / "token"
    check(tok.exists(), "token", str(tok) if tok.exists() else "not generated",
          "" if tok.exists() else "ygg install")

    cfg = _config()
    embed, bg = cfg.get("embed_model") or "", cfg.get("bg_model") or ""
    check(bool(embed), "embedding model", embed or "none (lexical-only)",
          "" if embed else "ygg setup")
    check(bool(bg), "background model", bg or "none (manual write-path)",
          "" if bg else "ygg setup")

    if embed or bg:
        if which("ollama"):
            pulled = _ollama_models()
            for m in (embed, bg):
                if not m:
                    continue
                have = any(x.split(":")[0] == m.split(":")[0] for x in pulled)
                ok = ok and have
                check(have, f"model {m}", "present" if have else "NOT pulled",
                      "" if have else f"ollama pull {m}")
        else:
            ok = False
            check(False, "ollama", "a model is configured but `ollama` is missing",
                  "install Ollama — https://ollama.com")

    claude_reg = _mcp_registered("claude")
    codex_reg = _mcp_registered("codex")
    check(claude_reg, "Claude Code MCP", "registered" if claude_reg else "not registered",
          "" if claude_reg else "ygg register")
    check(codex_reg, "Codex MCP", "registered" if codex_reg else "not registered",
          "" if codex_reg else "ygg register")
    if not claude_reg and not codex_reg:
        ok = False  # no agent has the ygg_* tools -> a failed install, not "All good."
        print(f"     {p.dim('(or install the plugin: /plugin marketplace add VonderVuflya/Yggdrasil → /plugin install yggdrasil)')}")

    verdict = p.green("✓ All good.") if ok else p.yellow("Some checks need attention (see above).")
    print("\n" + verdict)
    return 0 if ok else 1


def _register() -> int:
    """(Re)register the MCP server with every detected agent host (Claude Code / Codex)."""
    from . import service
    service.deploy_files()  # make sure the deployed MCP script exists to point at
    agents = service.register_mcp()
    if agents:
        print(f"registered MCP with: {', '.join(agents)}")
        return 0
    print("No agent host detected to register with.")
    print("If you use Claude Code (incl. the VSCode/Cursor extension), add this to the")
    print("\"mcpServers\" object in ~/.claude.json and restart the editor:")
    print(json.dumps({"yggdrasil": service.claude_json_entry()}, indent=2))
    return 1


def _reindex() -> int:
    """Backfill embeddings for any memories missing one (restores dense recall)."""
    from . import service
    tok = os.environ.get("YGG_ENGINE_TOKEN") or service.token()
    req = urllib.request.Request(
        f"http://127.0.0.1:{_port()}/reindex", data=b"{}", method="POST",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            healed = (json.load(r).get("data") or {}).get("healed", 0)
    except Exception as exc:  # noqa: BLE001
        print(f"reindex failed: {exc} (is the engine up? `ygg start`)", file=sys.stderr)
        return 1
    print(f"reindex: backfilled {healed} missing embedding(s).")
    return 0


def _wrap(text: str, width: int, indent: str) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width=width, initial_indent=indent, subsequent_indent=indent)


def _config_problems(C) -> dict[str, str]:
    """Settings that are wrong *in combination* -> what's wrong with them.

    A key is only missing relative to a backend chosen three rows earlier, so no
    single row can be judged on its own — and the un-set key renders dim, which
    made the one cell that mattered the quietest thing on screen. `ygg doctor`
    caught this; `ygg config`, where people actually configure it, did not.
    """
    bad: dict[str, str] = {}
    for url_key, key_key in (("embed_url", "embed_api_key"),
                             ("distill_url", "distill_api_key")):
        if _is_hosted(C.resolve(url_key)) and not C.resolve(key_key):
            bad[key_key] = "needed: the endpoint above is hosted"
    if C.resolve("embed_backend") == "openai" and not C.resolve("embed_model"):
        bad["embed_model"] = "needed: the openai backend has no default model"
    return bad


def _config_row(C, key: str, p, problem: str = "", width: int = 30) -> str:
    """One setting: name, effective value, where it came from. Secrets masked."""
    val = C.resolve(key)
    src = C.source(key)
    plain = C.display(key, val) or "—"
    if problem:
        shown = p.yellow(plain)          # the row that needs you, not the row that's dim
    else:
        shown = C.display(key, val) if val != "" else p.dim("—")
    # Colour by source, so "what did I actually change?" is answerable at a
    # glance instead of by reading the third column of every row. env: stays
    # distinct from config: one dies with the shell, the other is on disk.
    src_shown = (p.dim(src) if src == "default"
                 else p.yellow(src) if src.startswith("env:") else p.cyan(src))
    pad = " " * max(1, width - len(plain))
    row = f"    {key:<16} {shown}{pad}{src_shown}"
    return row + (f"\n      {p.yellow('↑ ' + problem)}" if problem else "")


def _config_list(C, verbose: bool = False) -> int:
    try:
        from . import ygg_ui
    except ImportError:  # pragma: no cover
        import ygg_ui  # type: ignore
    p = ygg_ui.palette()
    problems = _config_problems(C)
    print(f"\n🌳 {p.bold('Yggdrasil settings')}   {p.dim(str(C.CONFIG))}")
    for title, keys in C.grouped():
        if not keys:
            continue
        print(f"\n  {p.bold(title)}")
        for key in keys:
            print(_config_row(C, key, p, problems.get(key, "")))
            if verbose:
                for line in _wrap(C.SETTINGS[key][2], 74, " " * 6):
                    print(p.dim(line))
    print(f"\n  {p.dim('flag > env > config > default')}")
    if not verbose:
        print(f"  {p.dim('ygg config -v')}          what each setting does")
    print(f"  {p.dim('ygg config set <k> <v>')} change one"
          f"{'' if not ygg_ui.enabled() else p.dim('  ·  ygg config edit   pick from a menu')}")
    return 0


def _config_edit(C) -> int:
    """Pick a setting from a menu and change it — the discoverable path.

    `ygg config set embed_backend openai` only helps someone who already knows
    the key exists, which is the same gap the install wizard closes.
    """
    try:
        from . import ygg_prompt as _prompt
        from . import ygg_ui
    except ImportError:  # pragma: no cover
        import ygg_prompt as _prompt  # type: ignore
        import ygg_ui  # type: ignore
    p = ygg_ui.palette()
    opts = []
    for title, keys in C.grouped():
        for key in keys:
            val = C.resolve(key)
            shown = C.display(key, val) if val != "" else "—"
            opts.append(_prompt.Option(key, key, f"{shown}   [{title.split(' —')[0].lower()}]"))
    if not opts:
        return 0
    try:
        key = _prompt.select("Which setting?", opts)
    except KeyboardInterrupt:
        return 1
    print(f"\n  {p.bold(key)}")
    for line in _wrap(C.SETTINGS[key][2], 74, "  "):
        print(p.dim(line))
    current = C.resolve(key)
    secret = key in C.SECRET_FILES
    try:
        new = _prompt.text("New value (empty = leave as is)",
                           "" if secret else current, secret=secret)
    except KeyboardInterrupt:
        return 1
    if not new or new == current:
        print(p.dim("  unchanged"))
        return 0
    C.set_value(key, new)
    print(f"  {ygg_ui.mark_ok(p)} {key} = {C.display(key, new)}  {p.dim('in ' + C.stored_at(key))}")
    if key.startswith(("embed_", "distill_")):
        print(p.dim("  → these run in the daemon: `ygg redeploy` to apply"))
    return 0


def _config_cmd(rest: list[str]) -> int:
    """ygg config [list|edit|get <key>|set <key> <value>|unset <key>]."""
    from . import ygg_config as C
    verbose = "-v" in rest or "--verbose" in rest
    rest = [a for a in rest if a not in ("-v", "--verbose")]
    sub = rest[0] if rest else "list"

    if sub in ("edit", "menu"):
        return _config_edit(C)

    if sub in ("list", "ls", ""):
        return _config_list(C, verbose=verbose)

    if sub == "get":
        if len(rest) < 2 or rest[1] not in C.SETTINGS:
            print(f"usage: ygg config get <{'|'.join(C.SETTINGS)}>", file=sys.stderr)
            return 2
        # Deliberately UNmasked: `get` is the single-value accessor scripts pipe
        # (KEY=$(ygg config get embed_api_key)), same contract as `gh auth token`.
        # `config list` — the view people paste into issues — masks instead.
        print(C.resolve(rest[1]))
        return 0

    if sub == "set":
        if len(rest) < 3 or rest[1] not in C.SETTINGS:
            print(f"usage: ygg config set <{'|'.join(C.SETTINGS)}> <value>", file=sys.stderr)
            return 2
        key, value = rest[1], rest[2]
        C.set_value(key, value)
        print(f"set {key} = {C.display(key, value)}  (in {C.stored_at(key)})")
        if key in ("embed_model", "embed_url", "embed_backend", "embed_api_key"):
            print("  note: embeddings run in the daemon — run `ygg redeploy` for this to take effect.")
        return 0

    if sub == "unset":
        if len(rest) < 2 or rest[1] not in C.SETTINGS:
            print(f"usage: ygg config unset <{'|'.join(C.SETTINGS)}>", file=sys.stderr)
            return 2
        key = rest[1]
        if C.unset_value(key):
            print(f"unset {key} (now: {C.display(key, C.resolve(key))} via {C.source(key)})")
        else:
            print(f"{key} was not set in config")
        return 0

    print(f"unknown config subcommand: {sub}\nusage: ygg config [list|get|set|unset]", file=sys.stderr)
    return 2


def _pypi_latest() -> str | None:
    import time
    # Cache-bust: PyPI's JSON is CDN-cached and can briefly serve the PREVIOUS
    # version right after a publish — that's why `ygg update` sometimes only sees a
    # fresh release on a 2nd run. A unique query + no-cache headers force a miss.
    url = f"https://pypi.org/pypi/yggdrasil-memory/json?_={int(time.time())}"
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            return json.load(r)["info"]["version"]
    except Exception:  # noqa: BLE001
        return None


def _vtuple(v: str) -> tuple:
    return tuple(int("".join(c for c in p if c.isdigit()) or 0) for p in v.split("."))


def _deployed_version() -> str:
    try:
        txt = (YGG_HOME / "scripts" / "__init__.py").read_text()
        m = re.search(r'__version__\s*=\s*"([^"]+)"', txt)
        return m.group(1) if m else "?"
    except OSError:
        return "(none)"


def _install_method() -> str:
    p = str(HERE).lower()
    if "pipx" in p:
        return "pipx"
    if "/cellar/" in p or "/homebrew/" in p:
        return "brew"
    if "/uv/" in p or "/.cache/uv" in p or "/archive-v" in p:
        return "uvx"
    return "pip"


def _upgrade_argv(method: str) -> list[str] | None:
    return {
        "pipx": ["pipx", "upgrade", "yggdrasil-memory"],
        "pip": [sys.executable, "-m", "pip", "install", "-U", "yggdrasil-memory"],
        # tap-qualified: bare `brew upgrade yggdrasil` is mis-resolved as a cask.
        "brew": ["brew", "upgrade", "VonderVuflya/tap/yggdrasil"],
    }.get(method)


def _redeploy() -> int:
    """Redeploy the INSTALLED engine code into ~/.yggdrasil and restart the daemon.
    The plumbing step `update` calls after a package upgrade."""
    from . import service
    cfg = _config()
    print(f"redeploying yggdrasil {__version__} into {YGG_HOME} ...")
    return service.install(cfg.get("embed_model", ""), cfg.get("bg_model", ""))


def _redeploy_if_stale() -> int:
    dep = _deployed_version()
    if dep != __version__:
        print(f"  the daemon was running {dep}; redeploying {__version__} ...")
        return _redeploy()
    print(f"  daemon already running {__version__}. Nothing to do.")
    return 0


def _update() -> int:
    """Upgrade Yggdrasil to the latest published version, then redeploy.

    `update` means what you'd expect (like apt/npm): fetch the newest release and
    install it. It upgrades the installed `yggdrasil-memory` package via whatever
    installer you used, then redeploys the new engine into the daemon. If you're
    already on the latest, it says so.
    """
    latest = _pypi_latest()
    if latest is None:
        print(f"Yggdrasil {__version__} — couldn't reach PyPI to check for updates.")
        return _redeploy_if_stale()
    if _vtuple(latest) <= _vtuple(__version__):
        print(f"✓ Yggdrasil {__version__} is already the latest.")
        return _redeploy_if_stale()

    method = _install_method()
    print(f"upgrading yggdrasil-memory {__version__} → {latest} (installed via {method}) ...")
    if method == "uvx":
        print("  uvx fetches the latest on every run — just re-run your "
              "`uvx --from yggdrasil-memory ygg ...` command (it's already on a fresh env).")
        return 0
    argv = _upgrade_argv(method)
    if not argv or which(argv[0]) is None:
        print(f"  can't auto-upgrade a {method} install. Run this, then `ygg update` again:")
        print(f"    {' '.join(argv) if argv else 'pip install -U yggdrasil-memory'}")
        return 1
    rc = subprocess.call(argv)
    if rc != 0:
        print(f"  upgrade failed (exit {rc}). Run manually: {' '.join(argv)}")
        return rc
    # This process is still the OLD code; invoke the freshly-installed `ygg` to
    # redeploy the new engine into the daemon.
    ygg_bin = which("ygg")
    if ygg_bin:
        return subprocess.call([ygg_bin, "redeploy"])
    print(f"  upgraded to {latest}. Now run:  ygg redeploy")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "help"
    rest = argv[1:]

    # Surface a cached "newer version available" nudge on user-facing commands
    # (reads the cache the engine maintains — never hits the network here).
    if cmd not in ("version", "--version", "-V", "help", "-h", "--help",
                   "mcp", "mcp-http", "serve", "ensure", "update", "redeploy"):
        try:
            from . import ygg_update_check
            note = ygg_update_check.notice(__version__)
            if note:
                print(note, file=sys.stderr)
        except Exception:  # noqa: BLE001 — never let the nudge break a command
            pass

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
    if cmd == "mcp-http":
        from . import service
        service.ensure_running()
        from . import ygg_http_mcp as m
        return m.main()
    if cmd in ("setup", "wizard"):
        from . import ygg_setup as m
        sys.argv = ["ygg setup", "wizard", *rest]
        return m.main()
    if cmd in ("recommend", "hw"):
        from . import ygg_setup as m
        sys.argv = ["ygg", cmd, *rest]
        return m.main()
    if cmd in ("stats", "seed", "distill"):
        from . import service
        service.ensure_running()  # cold-start onboarding needs the engine up
        from . import ygg_seed
        return ygg_seed.main(cmd, rest)
    if cmd == "sync":
        from . import service
        service.ensure_running()
        from . import ygg_sync
        return ygg_sync.main(cmd, rest)
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
    if cmd == "register":
        return _register()
    if cmd == "reindex":
        return _reindex()
    if cmd == "config":
        return _config_cmd(rest)
    if cmd == "update":
        return _update()
    if cmd == "redeploy":
        return _redeploy()
    if cmd in SERVICE_CMDS:
        return _service(cmd, rest)

    print(f"unknown command: {cmd}\n", file=sys.stderr)
    print(USAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
