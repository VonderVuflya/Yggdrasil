#!/usr/bin/env python3
"""`ygg link` — join two of your machines into one memory.

The counterpart to `ygg sync`, which moves memory through a git repo you own.
This one is a direct link between your own machines: writes propagate in about a
second, deletions propagate too, and nothing leaves your network.

Pairing is deliberately a two-command ritual rather than autodiscovery. The
engine has no authorization levels — whoever authenticates can wipe the store —
so a machine becomes a peer only because you carried a one-time code to it.

    machine A:  ygg link                 # prints a code, valid 5 minutes, once
    machine B:  ygg link ygg://…#…       # paste it
    either:     ygg link --list
                ygg unlink <name>

Machines on different networks can link over Tailscale: `ygg link --tailscale`
puts this machine's tailnet address in the code.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlparse

try:  # package + flat-layout imports
    from .ygg import request_json
except ImportError:  # pragma: no cover
    from ygg import request_json


def _ui():
    try:
        from . import ygg_ui
    except ImportError:  # pragma: no cover
        import ygg_ui
    return ygg_ui, ygg_ui.palette()


def _active_firewall() -> str | None:
    """Which host firewall is switched on, as far as can be told without root."""
    system = platform.system()
    if system == "Windows":
        return "windows"

    def run(cmd: list[str]) -> str:
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            return ""

    if system == "Darwin":
        state = run(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"])
        return "macos" if "enabled" in state.lower() else None
    for name in ("ufw", "firewalld"):
        if run(["systemctl", "is-active", name]).strip() == "active":
            return name
    return None


def firewall_hint(port: int, peer_ip: str, *, firewall: str | None = "detect") -> str:
    """The one command that opens the sync port to that peer, for whichever
    firewall this machine runs. Scoped to the peer, never to the world."""
    if firewall == "detect":
        firewall = _active_firewall()
    if firewall == "ufw":
        return f"sudo ufw allow from {peer_ip} to any port {port} proto tcp"
    if firewall == "firewalld":
        return ("sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 "
                f"source address={peer_ip} port port={port} protocol=tcp accept' "
                "&& sudo firewall-cmd --reload")
    if firewall == "windows":
        return ('netsh advfirewall firewall add rule name="Yggdrasil sync" dir=in action=allow '
                f"protocol=TCP localport={port} remoteip={peer_ip}")
    if firewall == "macos":
        return ("System Settings → Network → Firewall → Options: allow incoming "
                "connections for python3")
    return (f"make sure nothing blocks inbound TCP {port} from {peer_ip} "
            "(a firewall, router client isolation, a VPN)")


def peer_state(health: dict[str, Any] | None) -> tuple[str, str]:
    """("ok" | "fail" | "idle", what to say). Only a confirmed delivery with
    nothing left waiting counts as ok — a quiet queue is not a healthy one."""
    if not health:
        return "idle", "not contacted since the engine started"
    backlog = int(health.get("backlog") or 0)
    waiting = f" · {backlog} waiting" if backlog else ""
    ok_at, error_at = health.get("ok_at"), health.get("error_at")
    if health.get("error") and (not ok_at or (error_at or 0) >= ok_at):
        return "fail", f"failing: {health['error']}{waiting}"
    if ok_at:
        return ("ok" if not backlog else "idle"), f"delivered {_ago(ok_at)}{waiting}"
    if backlog:
        return "idle", f"nothing delivered yet{waiting}"
    if health.get("heard_at"):
        return "ok", f"heard from {_ago(health['heard_at'])}"
    return "idle", "nothing to send yet"


def _ago(ts: float) -> str:
    try:
        from . import ygg_ui
    except ImportError:  # pragma: no cover
        import ygg_ui
    return ygg_ui.ago(ts) or time.strftime("%H:%M", time.localtime(ts))


def _status(args: argparse.Namespace) -> int:
    ui, p = _ui()
    data = request_json("GET", "/sync/peers")["data"]
    if data.get("error"):
        print(f"  {ui.mark_warn(p)} sync listener: {data['error']}", file=sys.stderr)
    if not data["peers"]:
        print("🔗 no linked machines yet\n"
              f"   {p.dim('on this machine:  ygg link            (prints a one-time code)')}\n"
              f"   {p.dim('on the other one: ygg link <code>')}")
        return 0
    where = ", ".join(data.get("urls") or []) or data.get("url") or "not listening"
    print(f"🔗 linked machines   {p.dim(where)}")
    failing = 0
    for peer in data["peers"]:
        kind, text = peer_state(peer.get("health"))
        mark = {"ok": ui.mark_ok, "fail": ui.mark_fail}.get(kind, ui.mark_warn)(p)
        failing += kind == "fail"
        model = peer.get("embed_model") or "no dense model"
        print(f"  {mark} {peer['name']:<16} {peer.get('url') or '?':<28} {text}")
        print(f"    {p.dim(model)}")
        error = ((peer.get("health") or {}).get("error") or "").lower()
        if kind == "fail" and any(w in error for w in ("timed out", "refused", "unreachable")):
            # The blocked side cannot see this — nothing fails over there — so
            # say here what to run there, scoped to this machine's address.
            port = urlparse(peer.get("url") or "").port or 42070
            mine = urlparse(peer.get("local_url") or "").hostname or "<this machine's address>"
            print(f"    {p.dim(peer['name'] + ' is not accepting connections from here. On ' + peer['name'] + ', for example:')}\n"
                  f"      {firewall_hint(port, mine, firewall='ufw')}")
    return 1 if failing else 0


def _issue(args: argparse.Namespace) -> int:
    ui, p = _ui()
    payload: dict[str, Any] = {}
    if args.tailscale:
        payload["via"] = "tailscale"
    elif args.host:
        payload["host"] = args.host
    try:
        data = request_json("POST", "/sync/link/issue", payload)["data"]
    except Exception as exc:  # noqa: BLE001 — surface the engine's message, not a traceback
        print(f"  {ui.mark_fail(p)} {exc}", file=sys.stderr)
        return 2
    print(f"🔗 pairing code   {p.dim('valid 5 minutes · single use')}\n")
    print(f"    {data['code']}\n")
    print(f"   {p.dim('on the OTHER machine run:  ygg link ' + data['code'])}")
    print(f"   {p.dim('this machine is listening on ' + data['url'])}")
    if data.get("tailscale"):
        print(f"   {p.dim('other machine on another network? ygg link --tailscale')}")
    return 0


def _redeem(args: argparse.Namespace) -> int:
    ui, p = _ui()
    try:
        peer = request_json("POST", "/sync/link/redeem",
                            {"code": args.code, "name": args.name})["data"]
    except Exception as exc:  # noqa: BLE001 — surface the engine's message, not a traceback
        print(f"  {ui.mark_fail(p)} pairing failed: {exc}", file=sys.stderr)
        return 2
    print(f"  {ui.mark_ok(p)} linked with {peer['name']}  {p.dim(peer.get('url') or '')}")
    if peer.get("reachable_back") is False:
        issuer = urlparse(args.code.strip()).hostname or "the other machine"
        print(f"  {ui.mark_warn(p)} {peer['name']} cannot reach this machine, so its writes will not\n"
              f"    arrive here ({peer.get('back_error') or 'no answer'}).\n"
              f"    Open the port here, then check with `ygg link --list`:\n"
              f"      {firewall_hint(int(peer.get('port') or 42070), issuer)}", file=sys.stderr)
    result = request_json("POST", "/sync/reconcile", {"force": True})["data"]
    if result.get("errors"):
        print(f"  {ui.mark_warn(p)} first sync: {result['errors'][0]}", file=sys.stderr)
    else:
        for line in result.get("detail") or []:
            print(f"  {ui.mark_ok(p)} {line}")
    return 0


def _sync_now(args: argparse.Namespace) -> int:
    ui, p = _ui()
    result = request_json("POST", "/sync/reconcile", {"force": True})["data"]
    for line in result.get("detail") or []:
        print(f"  {ui.mark_ok(p)} {line}")
    for line in result.get("errors") or []:
        print(f"  {ui.mark_fail(p)} {line}", file=sys.stderr)
    return 1 if result.get("errors") else 0


def _unlink(args: argparse.Namespace) -> int:
    ui, p = _ui()
    removed = request_json("POST", "/sync/peers/remove", {"name": args.name})["data"]["removed"]
    if not removed:
        print(f"  {ui.mark_warn(p)} no linked machine called {args.name!r}", file=sys.stderr)
        return 1
    print(f"  {ui.mark_ok(p)} unlinked {args.name}  "
          f"{p.dim('(its key is revoked here; run ygg unlink there too)')}")
    return 0


def main(cmd: str, rest: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=f"ygg {cmd}", add_help=True)
    if cmd == "unlink":
        parser.add_argument("name", help="name of the linked machine to forget")
        return _unlink(parser.parse_args(rest))
    parser.add_argument("code", nargs="?", default="",
                        help="pairing code from the other machine (omit to print one)")
    parser.add_argument("--name", default="", help="what to call the other machine locally")
    parser.add_argument("--list", action="store_true", help="show linked machines")
    parser.add_argument("--sync", action="store_true", help="reconcile with every peer now")
    parser.add_argument("--tailscale", action="store_true",
                        help="put this machine's Tailscale address in the code")
    parser.add_argument("--host", default="", help="put this local address in the code")
    args = parser.parse_args(rest)
    if args.list:
        return _status(args)
    if args.sync:
        return _sync_now(args)
    if args.code:
        return _redeem(args)
    return _issue(args)
