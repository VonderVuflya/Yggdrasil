#!/usr/bin/env python3
"""Who this node trusts on the network, and what it proves itself with.

The engine has no authorization levels — whoever authenticates can call
/purge. That single fact drives every decision here:

  * The LAN listener does NOT reuse ~/.yggdrasil/token. That token sits in the
    config of every agent on this machine; turning it into a network credential
    would hand the whole store to anything that can read a dotfile.
  * Keys are per PAIR, not global, so revoking one machine leaves the others
    working and no secret is shared by three parties.
  * Transport is TLS with the certificate PINNED at pairing time. Pinning is what
    lets a self-signed certificate be strictly better than a CA here: there is no
    third party to trust and no name resolution to spoof.

The certificate is minted by shelling out to `openssl`. stdlib `ssl` can use
certificates but cannot create them, and the package promises zero runtime
dependencies — so the choice is an external binary that ships with macOS and
essentially every Linux, or breaking that promise for one file.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# A pairing code is meant to be carried between two terminals by hand. Long
# enough to do that unhurried, short enough that a shoulder-surfed screenshot
# stops being useful.
CODE_TTL = 300.0

CERT_NAME = "sync-cert.pem"
KEY_NAME = "sync-key.pem"


# --------------------------------------------------------------------------- #
# pairing codes
# --------------------------------------------------------------------------- #

def new_secret() -> str:
    return secrets.token_urlsafe(32)


def make_code(host: str, port: int, pairing_id: str, secret: str) -> str:
    """`ygg://host:port/pairing_id#secret` — the secret lives in the fragment so
    that pasting the code into anything URL-shaped keeps it out of request
    lines and access logs."""
    return f"ygg://{host}:{int(port)}/{pairing_id}#{secret}"


def parse_code(code: str) -> dict[str, Any]:
    parsed = urlparse((code or "").strip())
    if parsed.scheme != "ygg" or not parsed.hostname or not parsed.fragment:
        raise ValueError("not a pairing code — expected ygg://host:port/id#secret")
    try:
        port = parsed.port
    except ValueError as exc:  # non-numeric port
        raise ValueError(f"bad pairing code: {exc}") from exc
    pairing_id = (parsed.path or "").lstrip("/")
    if not port or not pairing_id:
        raise ValueError("bad pairing code: missing port or pairing id")
    return {"host": parsed.hostname, "port": int(port),
            "pairing_id": pairing_id, "secret": parsed.fragment}


class PendingPairings:
    """Codes this node has issued and not yet seen redeemed.

    Deliberately in memory only: an unredeemed code should not survive a restart,
    and a code that never gets used should leave nothing behind.
    """

    def __init__(self) -> None:
        self._open: dict[str, tuple[str, float]] = {}

    def issue(self, host: str, port: int, *, now: float | None = None) -> str:
        now = time.time() if now is None else now
        pairing_id, secret = uuid.uuid4().hex[:12], new_secret()
        self._open = {k: v for k, v in self._open.items() if now - v[1] < CODE_TTL}
        self._open[pairing_id] = (secret, now)
        return make_code(host, port, pairing_id, secret)

    def redeem(self, pairing_id: str, secret: str, *, now: float | None = None) -> bool:
        """One success per code. A WRONG secret does not consume it — otherwise
        anyone able to reach the port could burn a code the user is mid-way
        through typing."""
        now = time.time() if now is None else now
        entry = self._open.get(pairing_id)
        if entry is None or now - entry[1] >= CODE_TTL:
            return False
        if not hmac.compare_digest(entry[0], secret or ""):
            return False
        self._open.pop(pairing_id, None)
        return True


# --------------------------------------------------------------------------- #
# the peer registry
# --------------------------------------------------------------------------- #

def default_path() -> Path:
    home = os.environ.get("YGG_HOME") or str(Path.home() / ".yggdrasil")
    return Path(home) / "peers.json"


def blank_state() -> dict[str, Any]:
    return {"node_id": uuid.uuid4().hex[:16], "peers": {}}


def load(path: Path | None = None) -> dict[str, Any]:
    """Never raises. A registry this node cannot read means "no peers yet", not a
    dead engine — sync is a feature, not a precondition for remembering things."""
    path = Path(path or default_path())
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return blank_state()
    if not isinstance(state, dict) or not isinstance(state.get("peers"), dict):
        return blank_state()
    state.setdefault("node_id", uuid.uuid4().hex[:16])
    return state


def save(state: dict[str, Any], path: Path | None = None) -> None:
    path = Path(path or default_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(tmp, 0o600)  # set before the rename: never briefly world-readable
    tmp.replace(path)


def add_peer(state: dict[str, Any], *, node_id: str, name: str, url: str,
             key_out: str, key_in: str, fingerprint: str,
             embed_model: str | None = None) -> dict[str, Any]:
    peer = {"node_id": node_id, "name": name, "url": url, "key_out": key_out,
            "key_in": key_in, "fingerprint": fingerprint,
            "embed_model": embed_model, "last_seen": None}
    state["peers"][node_id] = peer
    return peer


def remove_peer(state: dict[str, Any], name_or_id: str) -> bool:
    for node_id, peer in list(state["peers"].items()):
        if name_or_id in (node_id, peer.get("name")):
            del state["peers"][node_id]
            return True
    return False


def authorized(state: dict[str, Any], presented: str) -> dict[str, Any] | None:
    """Which peer presented this key, if any. Constant-time compare — a plain ==
    leaks the key byte by byte to anything that can time the endpoint."""
    if not presented:
        return None
    for peer in state.get("peers", {}).values():
        if hmac.compare_digest(str(peer.get("key_in") or ""), presented):
            return peer
    return None


# --------------------------------------------------------------------------- #
# certificate
# --------------------------------------------------------------------------- #

def openssl_available() -> bool:
    return shutil.which("openssl") is not None


def ensure_cert(home: Path) -> tuple[Path, Path]:
    """Mint this node's self-signed certificate once; reuse it forever after.

    The subject is meaningless on purpose — nothing validates names, the peer
    pins the fingerprint it saw during pairing.
    """
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    cert, key = home / CERT_NAME, home / KEY_NAME
    if cert.exists() and key.exists():
        return cert, key
    if not openssl_available():
        raise RuntimeError(
            "openssl not found — needed once to mint this machine's sync certificate.\n"
            "  install it, or pair with --insecure to sync over plain HTTP on a LAN you trust")
    result = subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(key), "-out", str(cert), "-days", "3650",
         "-subj", "/CN=yggdrasil-sync"],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"openssl failed to mint a certificate:\n{result.stderr.strip()}")
    os.chmod(key, 0o600)
    return cert, key


def cert_fingerprint(cert_path: Path) -> str:
    """SHA-256 over the DER body of the PEM — the same number both sides can
    compute, and what gets pinned at pairing time."""
    import base64 as _b64
    pem = Path(cert_path).read_text(encoding="utf-8")
    body = pem.split("-----BEGIN CERTIFICATE-----")[1].split("-----END CERTIFICATE-----")[0]
    der = _b64.b64decode("".join(body.split()))
    return hashlib.sha256(der).hexdigest()
