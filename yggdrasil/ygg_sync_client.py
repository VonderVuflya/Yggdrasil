#!/usr/bin/env python3
"""Talking to the other end of the uplink.

The far end is deliberately anonymous: this client speaks the /sync/* protocol
and does not care whether a peer engine or something else answers it.

http.client rather than urllib, for one reason — certificate PINNING. urllib
gives no access to the peer certificate before the body is read, and CA
validation is meaningless for a self-signed cert on a LAN. Here the socket is
opened, the certificate's SHA-256 is compared to the one recorded at pairing
time, and anything else drops the connection before a single byte of memory
crosses it.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import ssl
from typing import Any
from urllib.parse import urlparse


# Ceiling on one response body. A digest of a 10k-memory store is ~400 KB and a
# push batch with vectors a few MB; anything past this is a broken or hostile
# peer, and reading it whole would let that peer exhaust our memory.
MAX_RESPONSE = 64 * 1024 * 1024


class SyncError(RuntimeError):
    """Anything that stopped an exchange: unreachable, unauthorised, wrong
    certificate, incompatible protocol."""


def _unverified_context() -> ssl.SSLContext:
    """Certificate chain checks off — the pin replaces them. Order matters:
    check_hostname must go before verify_mode or ssl raises."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class PeerClient:
    def __init__(self, url: str, *, key: str = "", fingerprint: str | None = None,
                 pin_prefix: str | None = None, timeout: float = 10.0,
                 advertise: str | None = None) -> None:
        self.url = url.rstrip("/")
        # Where we listen as seen from this peer; sent with every request so
        # it can follow us to a new address.
        self.advertise = advertise
        self.key = key
        self.fingerprint = fingerprint
        # The leading part of the fingerprint carried in a pairing code — what
        # the very first connection is checked against, before any pin exists.
        self.pin_prefix = (pin_prefix or "").lower() or None
        self.timeout = timeout
        self.observed_fingerprint: str | None = None

    def _connect(self):
        parsed = urlparse(self.url)
        host, port = parsed.hostname, parsed.port
        if not host or not port:
            raise SyncError(f"peer url is not host:port shaped: {self.url}")
        if parsed.scheme != "https":
            return http.client.HTTPConnection(host, port, timeout=self.timeout)
        conn = http.client.HTTPSConnection(host, port, timeout=self.timeout,
                                           context=_unverified_context())
        conn.connect()
        der = conn.sock.getpeercert(binary_form=True) if conn.sock else None
        if not der:
            conn.close()
            raise SyncError("peer offered no certificate")
        self.observed_fingerprint = hashlib.sha256(der).hexdigest()
        if self.fingerprint and not hmac.compare_digest(self.observed_fingerprint, self.fingerprint):
            conn.close()
            raise SyncError(
                "certificate fingerprint does not match the one pinned at pairing.\n"
                "  either the peer was reinstalled (re-pair it) or something is impersonating it")
        if self.pin_prefix and not hmac.compare_digest(
                self.observed_fingerprint[:len(self.pin_prefix)], self.pin_prefix):
            conn.close()
            raise SyncError(
                "the machine that answered is not the one that issued this pairing code.\n"
                "  nothing was sent. check the address, or something on the network is "
                "intercepting the connection")
        return conn

    def request(self, method: str, path: str, body: dict[str, Any] | None = None,
                *, key: str | None = None) -> dict[str, Any]:
        payload = json.dumps(body or {}).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        token = self.key if key is None else key
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if self.advertise:
            headers["X-Ygg-Url"] = self.advertise
        # The connect belongs inside the try: over TLS it runs eagerly in
        # _connect, and a refused or timed-out handshake escaping as a raw
        # OSError used to kill the background sender thread.
        conn = None
        try:
            conn = self._connect()
            conn.request(method, path, body=payload, headers=headers)
            response = conn.getresponse()
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise SyncError(f"{self.url}: response larger than {MAX_RESPONSE} bytes")
            status, header_items = response.status, response.getheaders()
        except (OSError, http.client.HTTPException) as exc:
            raise SyncError(f"{self.url}: {exc}") from exc
        finally:
            if conn is not None:
                conn.close()
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            parsed = {}
        return {"status": status, "headers": [h for h, _ in header_items], "body": parsed}

    def _ok(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        out = self.request(method, path, body)
        if out["status"] != 200:
            detail = out["body"].get("error") if isinstance(out["body"], dict) else None
            raise SyncError(f"{path} -> HTTP {out['status']}" + (f": {detail}" if detail else ""))
        return out["body"].get("data") or {}

    # ---- protocol ---------------------------------------------------------

    def hello(self) -> dict[str, Any]:
        return self._ok("GET", "/sync/hello")

    def digest(self) -> dict[str, Any]:
        return self._ok("GET", "/sync/digest")

    def fetch(self, ids: list[str]) -> list[dict[str, Any]]:
        return self._ok("POST", "/sync/fetch", {"ids": ids}).get("memories", [])

    def push(self, *, memories: list[dict[str, Any]] | None = None,
             tombstones: dict[str, float] | None = None,
             relations: list[dict[str, Any]] | None = None,
             relation_tombstones: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"memories": memories or [], "tombstones": tombstones or {},
                                "relations": relations or []}
        if relation_tombstones:  # 0.16.0 peers ignore it; omitted when empty all the same
            body["relation_tombstones"] = relation_tombstones
        return self._ok("POST", "/sync/push", body)

    def pair(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Redeem a pairing code. The pin is not known yet — the one-time secret
        in the code is what authenticates this exchange, and the certificate seen
        here becomes the pin for every request afterwards."""
        out = self.request("POST", "/sync/pair", payload, key="")
        if out["status"] != 200:
            detail = out["body"].get("error") if isinstance(out["body"], dict) else None
            raise SyncError(f"pairing refused (HTTP {out['status']})" + (f": {detail}" if detail else ""))
        return out["body"].get("data") or {}
