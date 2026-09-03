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
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

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
    where = data.get("url") or "not listening"
    print(f"🔗 linked machines   {p.dim(where)}")
    for peer in data["peers"]:
        model = peer.get("embed_model") or "no dense model"
        print(f"  {ui.mark_ok(p)} {peer['name']:<16} {peer.get('url') or '?':<28} {p.dim(model)}")
    return 0


def _issue(args: argparse.Namespace) -> int:
    ui, p = _ui()
    data = request_json("POST", "/sync/link/issue", {})["data"]
    print(f"🔗 pairing code   {p.dim('valid 5 minutes · single use')}\n")
    print(f"    {data['code']}\n")
    print(f"   {p.dim('on the OTHER machine run:  ygg link ' + data['code'])}")
    print(f"   {p.dim('this machine is listening on ' + data['url'])}")
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
    args = parser.parse_args(rest)
    if args.list:
        return _status(args)
    if args.sync:
        return _sync_now(args)
    if args.code:
        return _redeem(args)
    return _issue(args)
