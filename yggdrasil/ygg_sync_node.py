#!/usr/bin/env python3
"""The uplink node: a second listener, the sender, and reconcile.

Two paths, each doing what the other is bad at.

HOT — push on write. A mutation drops a reference in the outbox and returns;
this module's sender picks it up and ships it. The agent's write never waits for
the network, and a memory written on one machine shows up on the other in about
a second.

COLD — reconcile on read. Nodes trade digests and repair whatever the hot path
missed: a peer that was asleep, a dropped connection, an overflowed queue, a
restored backup. There is NO periodic poll. Yggdrasil is called a few times a
day, so a timer would spend all day discovering that nothing happened; instead a
reconcile is triggered by reads and short-circuits if a recent one succeeded.

The listener is separate from the engine's own. The main API stays on loopback
with the token every local agent already has; this one lives on the LAN with
per-peer keys, because the engine has no authorization levels and a single
shared secret on the network would put /purge one leaked dotfile away.
"""

from __future__ import annotations

import json
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:  # package + flat-layout imports
    from . import ygg_sync_peers as _peers
    from . import ygg_sync_protocol as _proto
    from .ygg_sync_client import PeerClient, SyncError
except ImportError:  # pragma: no cover
    import ygg_sync_peers as _peers
    import ygg_sync_protocol as _proto
    from ygg_sync_client import PeerClient, SyncError

# How long a successful reconcile is trusted before another read triggers one.
# Long enough that a burst of recalls costs a single exchange; short enough that
# a machine which missed a push is never stale for a working session.
RECONCILE_TTL = 60.0

# Ceiling on one push. Keeps a first sync of a large store off a single enormous
# request without needing a resumable protocol.
PUSH_BATCH = 500


class SyncHandler(BaseHTTPRequestHandler):
    """/sync/* only. Everything else is 404 — this socket must never become a
    second door to the full engine API."""

    server_version = "yggdrasil-sync"

    def __init__(self, node: "SyncNode", *args: Any) -> None:
        self.node = node
        super().__init__(*args)

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        pass  # the engine owns stdout; a chatty peer must not fill the log

    # ---- plumbing ---------------------------------------------------------

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        # Deliberately NO Access-Control-* headers, ever. A browser lured onto a
        # hostile page must not be able to turn into a peer.
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        try:
            parsed = json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _peer(self) -> dict[str, Any] | None:
        header = self.headers.get("Authorization", "")
        presented = header[7:] if header.startswith("Bearer ") else ""
        return _peers.authorized(self.node.peers_state, presented)

    # ---- routes -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in ("/sync/hello", "/sync/digest"):
            self._send(404, {"success": False, "error": "not found"})
            return
        if self._peer() is None:
            self._send(401, {"success": False, "error": "unpaired"})
            return
        if path == "/sync/hello":
            self._send(200, {"success": True, "data": self.node.hello_payload()})
        else:
            self._send(200, {"success": True, "data": self.node.local_digest()})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/sync/pair":
            # The only unauthenticated route: the one-time code IS the credential.
            try:
                self._send(200, {"success": True, "data": self.node.accept_pairing(self._body())})
            except PermissionError as exc:
                self._send(403, {"success": False, "error": str(exc)})
            return
        if path not in ("/sync/fetch", "/sync/push"):
            self._send(404, {"success": False, "error": "not found"})
            return
        if self._peer() is None:
            self._send(401, {"success": False, "error": "unpaired"})
            return
        body = self._body()
        if path == "/sync/fetch":
            ids = [str(i) for i in (body.get("ids") or []) if i]
            self._send(200, {"success": True,
                             "data": {"memories": self.node.export_records(ids)}})
            return
        self._send(200, {"success": True, "data": self.node.receive_push(body)})


class SyncNode:
    """Owns the LAN listener, the peer registry, the sender and reconcile."""

    def __init__(self, store: Any, *, home: Path | str, name: str,
                 host: str = "127.0.0.1", port: int = 0, insecure: bool = False) -> None:
        self.store = store
        self.home = Path(home)
        self.name = name
        self.host = host
        self.port = port
        self.insecure = insecure
        self.peers_path = self.home / "peers.json"
        self.peers_state = _peers.load(self.peers_path)
        self._pending = _peers.PendingPairings()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._sender: threading.Thread | None = None
        self._stopping = threading.Event()
        self._last_reconcile = 0.0
        self._lock = threading.Lock()
        if not self.peers_path.exists():
            _peers.save(self.peers_state, self.peers_path)

    # ---- identity ---------------------------------------------------------

    @property
    def node_id(self) -> str:
        return self.peers_state["node_id"]

    @property
    def url(self) -> str:
        scheme = "http" if self.insecure else "https"
        return f"{scheme}://{self.host}:{self.port}"

    @property
    def fingerprint(self) -> str:
        if self.insecure:
            return ""
        return _peers.cert_fingerprint(_peers.ensure_cert(self.home)[0])

    def reload_peers(self) -> None:
        self.peers_state = _peers.load(self.peers_path)

    def _save_peers(self) -> None:
        _peers.save(self.peers_state, self.peers_path)

    # ---- lifecycle --------------------------------------------------------

    def start(self) -> int:
        if self._httpd is not None:
            return self.port
        self._stopping.clear()
        httpd = ThreadingHTTPServer((self.host, self.port),
                                    lambda *args: SyncHandler(self, *args))
        if not self.insecure:
            cert, key = _peers.ensure_cert(self.home)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(str(cert), str(key))
            httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        self.port = httpd.server_address[1]
        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        self._stopping.set()
        self.store.outbox_signal.set()  # let a blocked sender notice and exit
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def start_sender(self) -> None:
        """Background push. Separate from start() so tests (and anything wanting
        deterministic behaviour) can drive flush_outbox() by hand."""
        if self._sender is not None:
            return

        def loop() -> None:
            delay = 1.0
            while not self._stopping.is_set():
                self.store.outbox_signal.wait(timeout=delay)
                self.store.outbox_signal.clear()
                if self._stopping.is_set():
                    return
                result = self.flush_outbox()
                # Exponential backoff to a five-minute ceiling: a peer that is off
                # should cost a handful of connection attempts an hour, not one a
                # second, and the queue survives regardless.
                delay = 1.0 if not result.get("errors") else min(delay * 2, 300.0)

        self._sender = threading.Thread(target=loop, daemon=True)
        self._sender.start()

    # ---- server-side handlers --------------------------------------------

    def hello_payload(self) -> dict[str, Any]:
        return {"proto": _proto.PROTOCOL_VERSION, "node": self.node_id, "name": self.name,
                "embed_model": getattr(self.store, "_embed_model", None),
                "memories": self.store.count()}

    def local_digest(self) -> dict[str, Any]:
        return _proto.build_digest(self.store.sync_export()["memories"],
                                   self.store.tombstones(), node_id=self.node_id)

    def export_records(self, ids: list[str]) -> list[dict[str, Any]]:
        return self._with_vectors(self.store.records_by_ids(ids))

    def receive_push(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.store.apply_remote(
            memories=body.get("memories") or [],
            tombstones=body.get("tombstones") or {},
            relations=body.get("relations") or [])

    def accept_pairing(self, body: dict[str, Any]) -> dict[str, Any]:
        """Redeem a code and record the caller as a peer.

        The caller's certificate fingerprint is taken from the payload rather
        than observed — it is the client here, so there is nothing to observe.
        That is safe because the one-time secret already authenticated this
        exchange; from the next request on, the pin does the work.
        """
        if not self._pending.redeem(str(body.get("pairing_id") or ""),
                                    str(body.get("secret") or "")):
            raise PermissionError("pairing code is unknown, expired, or already used")
        mine = _peers.new_secret()
        _peers.add_peer(self.peers_state,
                        node_id=str(body.get("node_id") or ""),
                        name=str(body.get("name") or "peer"),
                        url=str(body.get("url") or ""),
                        key_out=str(body.get("key") or ""),
                        key_in=mine,
                        fingerprint=str(body.get("fingerprint") or ""),
                        embed_model=body.get("embed_model"))
        self._save_peers()
        return {"node_id": self.node_id, "name": self.name, "url": self.url,
                "key": mine, "fingerprint": self.fingerprint,
                "embed_model": getattr(self.store, "_embed_model", None)}

    # ---- client-side ------------------------------------------------------

    def issue_pairing_code(self) -> str:
        return self._pending.issue(self.host, self.port)

    def pair_with(self, code: str, *, name: str | None = None) -> dict[str, Any]:
        parsed = _peers.parse_code(code)
        scheme = "http" if self.insecure else "https"
        url = f"{scheme}://{parsed['host']}:{parsed['port']}"
        mine = _peers.new_secret()
        client = PeerClient(url)
        try:
            answer = client.pair({
                "pairing_id": parsed["pairing_id"], "secret": parsed["secret"],
                "node_id": self.node_id, "name": self.name, "url": self.url,
                "key": mine, "fingerprint": self.fingerprint,
                "embed_model": getattr(self.store, "_embed_model", None)})
        except SyncError as exc:
            raise RuntimeError(str(exc)) from exc
        peer = _peers.add_peer(
            self.peers_state,
            node_id=str(answer.get("node_id") or ""),
            name=name or str(answer.get("name") or "peer"),
            url=str(answer.get("url") or url),
            key_out=str(answer.get("key") or ""),
            key_in=mine,
            fingerprint=client.observed_fingerprint or str(answer.get("fingerprint") or ""),
            embed_model=answer.get("embed_model"))
        self._save_peers()
        return peer

    def probe(self, url: str, *, key: str = "") -> dict[str, Any]:
        """Raw, unpinned request — for diagnostics and for asserting what an
        unpaired caller gets."""
        try:
            return PeerClient(url, key=key).request("GET", "/sync/hello")
        except SyncError as exc:
            return {"status": 0, "headers": [], "body": {"error": str(exc)}}

    def _client(self, peer: dict[str, Any]) -> PeerClient:
        return PeerClient(peer.get("url") or "", key=peer.get("key_out") or "",
                          fingerprint=peer.get("fingerprint") or None)

    def _with_vectors(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Attach the embedding when we have one. The receiver keeps it only if
        its own model matches — which is what makes one machine able to do the
        embedding for both."""
        out = []
        for rec in records:
            enriched = dict(rec)
            vector = self.store.export_vector(rec["id"])
            if vector:
                enriched.update(vector)
            out.append(enriched)
        return out

    # ---- the two paths ----------------------------------------------------

    def flush_outbox(self) -> dict[str, Any]:
        """Send everything queued. Acks only when EVERY peer took it — a partial
        ack would silently strand a change on one machine."""
        pending = self.store.outbox_pending()
        if not pending:
            return {"sent": 0, "errors": []}
        targets = list(self.peers_state.get("peers", {}).values())
        if not targets:
            # Nothing to deliver to. Dropping beats letting the queue grow until
            # it overflows and pointlessly demands a reconcile.
            self.store.outbox_ack([row["seq"] for row in pending])
            return {"sent": 0, "errors": []}

        memory_ids = [r["ref_id"] for r in pending if r["kind"] == "memory"]
        tombstone_ids = {r["ref_id"] for r in pending if r["kind"] == "tombstone"}
        graveyard = self.store.tombstones()
        payload_memories = self._with_vectors(self.store.records_by_ids(memory_ids))
        payload_tombs = {mid: graveyard[mid] for mid in tombstone_ids if mid in graveyard}

        errors: list[str] = []
        for peer in targets:
            try:
                client = self._client(peer)
                for i in range(0, max(len(payload_memories), 1), PUSH_BATCH):
                    client.push(memories=payload_memories[i:i + PUSH_BATCH],
                                tombstones=payload_tombs if i == 0 else {})
            except SyncError as exc:
                errors.append(f"{peer.get('name')}: {exc}")
        if not errors:
            self.store.outbox_ack([row["seq"] for row in pending])
        return {"sent": len(payload_memories) + len(payload_tombs), "errors": errors}

    def reconcile(self, *, force: bool = False) -> dict[str, Any]:
        """Digest exchange and repair. Skipped while a recent one still holds,
        unless the outbox overflowed and asked for a full pass."""
        now = time.time()
        with self._lock:
            fresh = (now - self._last_reconcile) < RECONCILE_TTL
            if not force and fresh and not self.store.needs_reconcile:
                return {"ran": False, "reason": "recent", "errors": []}

            targets = list(self.peers_state.get("peers", {}).values())
            errors: list[str] = []
            summary: list[str] = []
            for peer in targets:
                try:
                    summary.append(self._reconcile_one(peer))
                except SyncError as exc:
                    errors.append(f"{peer.get('name')}: {exc}")
            if not errors:
                self._last_reconcile = now
                self.store.needs_reconcile = False
            return {"ran": True, "peers": len(targets), "errors": errors, "detail": summary}

    def _reconcile_one(self, peer: dict[str, Any]) -> str:
        client = self._client(peer)
        greeting = client.hello()
        if not _proto.compatible(greeting.get("proto")):
            raise SyncError(
                f"protocol {greeting.get('proto')} != {_proto.PROTOCOL_VERSION} — "
                "upgrade Yggdrasil on both machines")

        remote = client.digest()
        plan = _proto.plan(self.local_digest(), remote)
        if not plan:
            return f"{peer.get('name')}: in sync"

        if plan.delete_local:
            self.store.apply_remote(
                tombstones={mid: remote["tombstones"][mid] for mid in plan.delete_local})

        merged_back: list[dict[str, Any]] = []
        if plan.fetch:
            incoming = client.fetch(plan.fetch)
            self.store.apply_remote(memories=incoming)
            # Send the merge back rather than making the peer redo it.
            merged_back = self.store.records_by_ids([r["id"] for r in incoming if r.get("id")])

        outgoing = self.store.records_by_ids(plan.push) + merged_back
        graveyard = self.store.tombstones()
        tombs = {mid: graveyard[mid] for mid in plan.push_tombstones if mid in graveyard}
        if outgoing or tombs:
            # Relations ride along whole: there are few of them in a personal
            # store, the upsert is idempotent, and giving edges their own digest
            # would double the protocol for no measured gain.
            edges = self.store.sync_export()["relations"] if outgoing else []
            payload = self._with_vectors(outgoing)
            for i in range(0, max(len(payload), 1), PUSH_BATCH):
                client.push(memories=payload[i:i + PUSH_BATCH],
                            tombstones=tombs if i == 0 else {},
                            relations=edges if i == 0 else [])
        return f"{peer.get('name')}: {plan.summary()}"
