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
import socket
import ssl
import sys
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

# Request body ceilings. /sync/pair is the one route reachable without a key,
# so it gets a tiny one; authenticated pushes carry up to PUSH_BATCH records
# with vectors. Trusting Content-Length unbounded let anyone on the LAN make
# the engine allocate whatever they claimed.
MAX_PAIR_BODY = 64 * 1024
MAX_BODY = 64 * 1024 * 1024

# A peer that connects and then says nothing must cost one thread for a bounded
# time, not one forever.
CONNECTION_TIMEOUT = 30.0

# How long the issuer of a code waits when it calls the new peer back. A
# firewall that drops packets otherwise holds the pairing for a full TCP
# connect timeout, about a minute and a quarter.
CALLBACK_TIMEOUT = 4.0

# Every authenticated request says where its sender listens on the interface
# it used, so a machine that got a new address from DHCP is found again
# as soon as it makes contact.
ADVERTISE_HEADER = "X-Ygg-Url"


class _BodyTooLarge(Exception):
    pass


class _SyncServer(ThreadingHTTPServer):
    """Threaded server that does the TLS handshake per connection, in that
    connection's own thread.

    Wrapping the LISTENING socket instead runs every handshake inside accept(),
    on the single serve_forever thread, with no timeout — one idle TCP
    connection then froze the listener for every peer.
    """

    daemon_threads = True

    def __init__(self, address: Any, handler: Any, context: ssl.SSLContext | None) -> None:
        self.tls_context = context
        super().__init__(address, handler)

    def finish_request(self, request: Any, client_address: Any) -> None:
        request.settimeout(CONNECTION_TIMEOUT)
        if self.tls_context is None:
            super().finish_request(request, client_address)
            return
        try:
            tls = self.tls_context.wrap_socket(request, server_side=True)
        except (OSError, ValueError):
            return  # silent, slow or not speaking TLS: drop it, nothing to answer
        try:
            super().finish_request(tls, client_address)
        finally:
            tls.close()


class SyncHandler(BaseHTTPRequestHandler):
    """/sync/* only. Everything else is 404 — this socket must never become a
    second door to the full engine API."""

    server_version = "yggdrasil-sync"
    timeout = CONNECTION_TIMEOUT

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

    def _body(self, limit: int = MAX_BODY) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length > limit:
            raise _BodyTooLarge()
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
        peer = _peers.authorized(self.node.peers_state, presented)
        if peer is not None:
            self.node.note_inbound(peer, self.headers.get(ADVERTISE_HEADER))
        return peer

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
        try:
            self._post()
        except _BodyTooLarge:
            self.close_connection = True  # the unread body must not become the next request
            self._send(413, {"success": False, "error": "request body too large"})

    def _post(self) -> None:
        path = urlparse(self.path).path
        if path == "/sync/pair":
            # The only unauthenticated route: the one-time code IS the credential.
            try:
                body = self._body(MAX_PAIR_BODY)
                self._send(200, {"success": True, "data": self.node.accept_pairing(body)})
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
                 host: str = "127.0.0.1", port: int = 0, insecure: bool = False,
                 host_pinned: bool = True, extra_hosts: list[str] | None = None) -> None:
        self.store = store
        self.home = Path(home)
        self.name = name
        self.host = host
        # False when `host` was guessed: pairing may then move the listener to
        # the interface that demonstrably reaches the other machine.
        self.host_pinned = host_pinned
        # Further interfaces to listen on: one per route a peer is reached by,
        # when they differ (a LAN peer and a Tailscale peer, say). Never 0.0.0.0.
        self.extra_hosts = [h for h in (extra_hosts or []) if h and h != host]
        self.port = port
        self.insecure = insecure
        self.peers_path = self.home / "peers.json"
        self.peers_state = _peers.load(self.peers_path)
        self._pending = _peers.PendingPairings()
        self._servers: dict[str, tuple[ThreadingHTTPServer, threading.Thread]] = {}
        self._sender: threading.Thread | None = None
        self._stopping = threading.Event()
        self._last_reconcile = 0.0
        self._lock = threading.Lock()
        self._reconciling = threading.Event()
        self._save_lock = threading.Lock()
        # Runtime only: when each peer last took a delivery, last failed and
        # last called us. Lost on restart, which is fine — it describes now.
        self._health: dict[str, dict[str, Any]] = {}
        if not self.peers_path.exists():
            _peers.save(self.peers_state, self.peers_path)

    # ---- identity ---------------------------------------------------------

    @property
    def node_id(self) -> str:
        return self.peers_state["node_id"]

    @property
    def scheme(self) -> str:
        return "http" if self.insecure else "https"

    @property
    def url(self) -> str:
        return self.url_on(self.host)

    def url_on(self, host: str) -> str:
        return f"{self.scheme}://{host}:{self.port}"

    @property
    def hosts(self) -> list[str]:
        """Every address being listened on, the primary first."""
        return [self.host, *(h for h in self._servers if h != self.host)]

    @property
    def fingerprint(self) -> str:
        if self.insecure:
            return ""
        return _peers.cert_fingerprint(_peers.ensure_cert(self.home)[0])

    def reload_peers(self) -> None:
        self.peers_state = _peers.load(self.peers_path)

    def _save_peers(self) -> None:
        with self._save_lock:
            _peers.save(self.peers_state, self.peers_path)

    # ---- lifecycle --------------------------------------------------------

    def start(self) -> int:
        if self.host in self._servers:
            return self.port
        self._stopping.clear()
        self._listen(self.host)
        for host in self.extra_hosts:
            try:
                self._listen(host)
            except OSError:
                pass  # that interface is gone; the route to its peer will say where to go
        return self.port

    def _listen(self, host: str) -> None:
        context = None
        if not self.insecure:
            cert, key = _peers.ensure_cert(self.home)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(str(cert), str(key))
        httpd = _SyncServer((host, self.port), lambda *args: SyncHandler(self, *args), context)
        self.port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self._servers[host] = (httpd, thread)

    def listen_also(self, host: str) -> None:
        """Add a listener on another interface, same port."""
        if host in self._servers:
            return
        self._listen(host)
        if host != self.host and host not in self.extra_hosts:
            self.extra_hosts.append(host)

    def stop(self) -> None:
        self._stopping.set()
        self.store.outbox_signal.set()  # let a blocked sender notice and exit
        self._close_listener()

    def _close_listener(self, host: str | None = None) -> None:
        for name in ([host] if host is not None else list(self._servers)):
            entry = self._servers.pop(name, None)
            if entry is None:
                continue
            httpd, thread = entry
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

    def _rebind(self, host: str) -> None:
        """Move the primary listener to `host`, keeping the port. Restores the
        old address if the new one cannot be bound."""
        if self.host not in self._servers:
            self.host = host
            return
        old = self.host
        self._close_listener(old)
        self.host = host
        try:
            self._listen(host)
        except OSError:
            self.host = old
            self._listen(old)
            raise

    def _local_url_for(self, peer_host: str) -> str:
        """Our address as seen from `peer_host`: the interface the kernel routes
        to it. Starts listening there if an address appeared since boot."""
        if self.host_pinned or not peer_host:
            return self.url
        local = _peers.route_source(peer_host)
        if not local:
            return self.url
        if local not in self._servers:
            try:
                self.listen_also(local)
            except OSError:
                return self.url
        return self.url_on(local)

    # ---- health -----------------------------------------------------------

    def _mark(self, peer: dict[str, Any], **fields: Any) -> None:
        entry = self._health.setdefault(str(peer.get("node_id") or ""), {
            "ok_at": None, "error": None, "error_at": None, "heard_at": None})
        entry.update(fields)

    def _mark_ok(self, peer: dict[str, Any]) -> None:
        self._mark(peer, ok_at=time.time(), error=None)

    def _mark_error(self, peer: dict[str, Any], exc: Exception) -> None:
        self._mark(peer, error=str(exc), error_at=time.time())

    def peer_health(self) -> dict[str, dict[str, Any]]:
        """Per peer: last good contact, the error since (if any), when it last
        called us, and how many changes are still waiting for it."""
        out = {}
        for node_id, peer in self.peers_state.get("peers", {}).items():
            entry = dict(self._health.get(node_id) or {
                "ok_at": None, "error": None, "error_at": None, "heard_at": None})
            entry["backlog"] = self.store.outbox_count(after=int(peer.get("outbox_hwm") or 0))
            out[node_id] = entry
        return out

    def note_inbound(self, peer: dict[str, Any], advertised: str | None) -> None:
        """An authenticated peer called. Remember that, and where it says it
        listens now — the request is keyed, so only the peer itself can move
        its own entry."""
        self._mark(peer, heard_at=time.time())
        url = _clean_url(advertised, self.scheme)
        if url and url != peer.get("url"):
            peer["url"] = url
            self._save_peers()

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
                try:
                    result = self.flush_outbox()
                except Exception as exc:  # noqa: BLE001 — the sender must outlive any one bad flush
                    print(f"[ygg-sync] push failed: {exc}", file=sys.stderr, flush=True)
                    result = {"errors": [str(exc)]}
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
        node_id = str(body.get("node_id") or "")
        # Checked before the code is redeemed, so a malformed request cannot
        # burn it — and an empty or borrowed id would overwrite another peer.
        if not node_id or node_id == self.node_id:
            raise PermissionError("pairing request names no usable node id")
        if not self.insecure and not body.get("fingerprint"):
            raise PermissionError("pairing request carries no certificate to pin")
        if not self._pending.redeem(str(body.get("pairing_id") or ""),
                                    str(body.get("secret") or "")):
            raise PermissionError("pairing code is unknown, expired, or already used")
        mine = _peers.new_secret()
        peer = _peers.add_peer(self.peers_state,
                               node_id=node_id,
                               name=str(body.get("name") or "peer"),
                               url=str(body.get("url") or ""),
                               key_out=str(body.get("key") or ""),
                               key_in=mine,
                               fingerprint=str(body.get("fingerprint") or ""),
                               embed_model=body.get("embed_model"))
        self._save_peers()
        back_error = self._call_back(peer)
        return {"node_id": self.node_id, "name": self.name, "url": self.url,
                "key": mine, "fingerprint": self.fingerprint,
                "embed_model": getattr(self.store, "_embed_model", None),
                "reachable_back": back_error is None, "back_error": back_error}

    def _call_back(self, peer: dict[str, Any]) -> str | None:
        """Can we reach the machine that just paired with us? Pairing proves
        only the other direction — and a firewall on its side used to leave a
        link that looked fine while every write from here was dropped.

        Any HTTP answer counts, a 401 included (it has not stored us yet): the
        question is whether the port is open and the certificate is the pinned
        one. Returns the error, or None when it answered."""
        if not peer.get("url"):
            return "it did not say where it listens"
        try:
            PeerClient(peer["url"], fingerprint=peer.get("fingerprint") or None,
                       timeout=CALLBACK_TIMEOUT).request("GET", "/sync/hello")
        except SyncError as exc:
            return str(exc)
        return None

    # ---- client-side ------------------------------------------------------

    def issue_pairing_code(self, host: str | None = None) -> str:
        """A one-time code naming `host`, or the primary address. Naming another
        interface (`ygg link --tailscale`) also starts listening on it."""
        if host and host != self.host:
            if not _is_local_address(host):
                raise ValueError(f"{host} is not an address of this machine")
            try:
                self.listen_also(host)
            except OSError as exc:
                raise RuntimeError(f"cannot listen on {host}:{self.port}: {exc}") from exc
        return self._pending.issue(host or self.host, self.port, fingerprint=self.fingerprint)

    def pair_with(self, code: str, *, name: str | None = None) -> dict[str, Any]:
        parsed = _peers.parse_code(code)
        scheme = "http" if self.insecure else "https"
        url = f"{scheme}://{parsed['host']}:{parsed['port']}"
        if not self.insecure and not parsed["fingerprint"]:
            raise RuntimeError(
                "this pairing code does not name the issuing machine's certificate, so the\n"
                "  connection could not be verified. update Yggdrasil there and run `ygg link` again")
        advertise = self.url
        if not self.host_pinned:
            # A guessed address — a VPN, a VM bridge — is what the issuer would
            # store and push to forever. The interface the kernel routes this
            # very connection through is the one both machines share.
            local = _peers.route_source(parsed["host"])
            if local and local not in self._servers:
                if self.peers_state.get("peers"):
                    # Peers already reach us on the current address: add one
                    # rather than move, or they are cut off.
                    self.listen_also(local)
                else:
                    self._rebind(local)
            if local:
                advertise = self.url_on(local)
        mine = _peers.new_secret()
        # The secret is sent only after the certificate matches the code.
        client = PeerClient(url, pin_prefix=parsed["fingerprint"])
        try:
            answer = client.pair({
                "pairing_id": parsed["pairing_id"], "secret": parsed["secret"],
                "node_id": self.node_id, "name": self.name, "url": advertise,
                "key": mine, "fingerprint": self.fingerprint,
                "embed_model": getattr(self.store, "_embed_model", None)})
        except SyncError as exc:
            raise RuntimeError(str(exc)) from exc
        peer = _peers.add_peer(
            self.peers_state,
            node_id=str(answer.get("node_id") or ""),
            name=name or str(answer.get("name") or "peer"),
            # The address that just answered, not the one the issuer believes
            # it has: the former is proven reachable from here.
            url=url,
            key_out=str(answer.get("key") or ""),
            key_in=mine,
            fingerprint=client.observed_fingerprint or str(answer.get("fingerprint") or ""),
            embed_model=answer.get("embed_model"))
        self._save_peers()
        # Not stored: it describes the moment of pairing. None from an issuer
        # too old to check.
        return {**peer, "reachable_back": answer.get("reachable_back"),
                "back_error": answer.get("back_error")}

    def probe(self, url: str, *, key: str = "") -> dict[str, Any]:
        """Raw, unpinned request — for diagnostics and for asserting what an
        unpaired caller gets."""
        try:
            return PeerClient(url, key=key).request("GET", "/sync/hello")
        except SyncError as exc:
            return {"status": 0, "headers": [], "body": {"error": str(exc)}}

    def _client(self, peer: dict[str, Any]) -> PeerClient:
        url = peer.get("url") or ""
        if url.startswith("https://") and not peer.get("fingerprint"):
            # Fail closed: an empty pin used to mean "accept any certificate".
            raise SyncError(f"no pinned certificate for {peer.get('name')} — unlink and link it again")
        return PeerClient(url, key=peer.get("key_out") or "",
                          fingerprint=peer.get("fingerprint") or None,
                          advertise=self._local_url_for(urlparse(url).hostname or ""))

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
        """Send everything queued, tracking delivery PER PEER.

        Each peer carries a high-water mark: the last outbox seq it confirmed.
        Rows are dropped once every peer is past them. A single all-or-nothing
        ack used to let one sleeping machine stall the queue for the others —
        they re-received the same first batch on every backoff tick, and rows
        past it never moved. Seqs are AUTOINCREMENT and an edit re-enqueues
        with a fresh one, so "past the mark" really means "already delivered".
        """
        targets = list(self.peers_state.get("peers", {}).values())
        if not targets:
            # Nothing to deliver to. Dropping beats letting the queue grow until
            # it overflows and pointlessly demands a reconcile.
            while pending := self.store.outbox_pending():
                self.store.outbox_ack_through(pending[-1]["seq"])
            return {"sent": 0, "errors": []}

        errors: list[str] = []
        sent = 0
        marks_before = [peer.get("outbox_hwm") for peer in targets]
        for peer in targets:
            try:
                sent += self._flush_to(peer)
            except SyncError as exc:
                self._mark_error(peer, exc)
                errors.append(f"{peer.get('name')}: {exc}")
        floor = min(int(peer.get("outbox_hwm") or 0) for peer in targets)
        if floor:
            self.store.outbox_ack_through(floor)
        if [peer.get("outbox_hwm") for peer in targets] != marks_before:
            self._save_peers()
        return {"sent": sent, "errors": errors}

    def _flush_to(self, peer: dict[str, Any]) -> int:
        client = self._client(peer)
        sent = 0
        while True:
            rows = self.store.outbox_pending(after=int(peer.get("outbox_hwm") or 0),
                                             limit=PUSH_BATCH)
            if not rows:
                return sent
            memory_ids = [r["ref_id"] for r in rows if r["kind"] == "memory"]
            tombstone_ids = {r["ref_id"] for r in rows if r["kind"] == "tombstone"}
            graveyard = self.store.tombstones() if tombstone_ids else {}
            memories = self._with_vectors(self.store.records_by_ids(memory_ids))
            tombs = {mid: graveyard[mid] for mid in tombstone_ids if mid in graveyard}
            if memories or tombs:
                client.push(memories=memories, tombstones=tombs)
                self._mark_ok(peer)
            peer["outbox_hwm"] = rows[-1]["seq"]
            sent += len(memories) + len(tombs)

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
                    self._mark_ok(peer)
                except SyncError as exc:
                    self._mark_error(peer, exc)
                    errors.append(f"{peer.get('name')}: {exc}")
            if not errors:
                self._last_reconcile = now
                self.store.needs_reconcile = False
            if len(errors) < len(targets) and self.store.outbox_count():
                # Someone is reachable again: the queued pushes should not sit
                # out the sender's backoff (up to five minutes) to find out.
                self.store.outbox_signal.set()
            return {"ran": True, "peers": len(targets), "errors": errors, "detail": summary}

    def maybe_reconcile_async(self) -> bool:
        """Trigger a reconcile from a READ, without making the read wait for it.

        A downed peer must never add a network timeout to `ygg_recall` — freshness
        is not worth an unresponsive memory, and the hot push path is what
        actually keeps the two machines current. Returns whether one was started.
        """
        if self._reconciling.is_set() or self._stopping.is_set():
            return False
        if (time.time() - self._last_reconcile) < RECONCILE_TTL and not self.store.needs_reconcile:
            return False
        if not self.peers_state.get("peers"):
            return False
        self._reconciling.set()

        def run() -> None:
            try:
                self.reconcile()
            except Exception:  # noqa: BLE001 — a background repair must never take the engine down
                pass
            finally:
                self._reconciling.clear()

        threading.Thread(target=run, daemon=True).start()
        return True

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


def _clean_url(url: str | None, scheme: str) -> str | None:
    """`scheme://host:port` if `url` is exactly that shape, else None."""
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme != scheme or not parsed.hostname or not port:
        return None
    if parsed.username or parsed.password or parsed.path not in ("", "/"):
        return None
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return f"{scheme}://{host}:{port}"


def _is_local_address(host: str) -> bool:
    """Whether this machine owns `host` — binding to it succeeds only then."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, 0))
    except (OSError, UnicodeError):
        return False
    return True
