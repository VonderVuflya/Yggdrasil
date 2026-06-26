#!/usr/bin/env python3
"""Streamable-HTTP MCP facade — Yggdrasil's tools over HTTP(S).

The stdio facade (``ygg mcp``) only reaches LOCAL CLI hosts (Claude Code, Codex).
This exposes the SAME tools over the MCP **Streamable HTTP** transport so remote
MCP clients can connect by URL — and, behind a public HTTPS tunnel + OAuth, so
can Claude / ChatGPT on the web and mobile (cross-surface). See
``docs/cross-surface.md`` for the full deployment (tunnel + OAuth).

Transport: a single ``/mcp`` endpoint. ``POST /mcp`` carries one JSON-RPC message
(or a batch); the response is returned as a single ``application/json`` body
(this server has no server-initiated messages, so it does not open an SSE stream
and answers ``GET /mcp`` with 405, which is spec-compliant). Bearer-token auth
guards ``/mcp``; ``/health`` is open.

Tool handling is REUSED verbatim from the stdio facade (``ygg_mcp_server.handle``),
so the two transports always expose an identical tool surface.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:  # package + flat-layout (deployed scripts dir) imports
    from . import ygg_mcp_server as mcp
except ImportError:  # pragma: no cover
    import ygg_mcp_server as mcp

PORT = int(os.environ.get("YGG_MCP_HTTP_PORT", "42071"))
HOST = os.environ.get("YGG_MCP_HTTP_HOST", "127.0.0.1")  # bind localhost; a tunnel exposes it


def _transport_token() -> str:
    """Bearer token a client must present to reach /mcp.

    Defaults to the engine token written by ``ygg install`` so there's one secret;
    override with ``YGG_MCP_TOKEN``. Empty means auth is DISABLED (local testing
    only — never expose an unauthenticated facade through a tunnel).
    """
    tok = os.environ.get("YGG_MCP_TOKEN")
    if tok:
        return tok
    home = os.environ.get("YGG_HOME") or str(Path.home() / ".yggdrasil")
    try:
        return (Path(home) / "token").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


TOKEN = _transport_token()


class Handler(BaseHTTPRequestHandler):
    server_version = "yggdrasil-http-mcp/0.1"

    def _auth_ok(self) -> bool:
        if not TOKEN:
            return True  # open mode (no token configured)
        return self.headers.get("Authorization", "") == f"Bearer {TOKEN}"

    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._json(200, {"status": "ok", "transport": "streamable-http",
                             "auth": "bearer" if TOKEN else "open"})
            return
        # No server-initiated stream for a pure tool server -> 405 (spec-compliant).
        self.send_response(405)
        self.send_header("Allow", "POST")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/mcp":
            self._json(404, {"error": "not found"})
            return
        if not self._auth_ok():
            self.send_response(401)
            self.send_header("WWW-Authenticate", "Bearer")
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            message = json.loads(raw.decode("utf-8")) if raw.strip() else {}
        except ValueError as exc:
            self._json(400, {"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": f"parse error: {exc}"}})
            return
        if isinstance(message, list):  # JSON-RPC batch
            responses = [r for r in (mcp.handle(m) for m in message) if r is not None]
            if not responses:
                self.send_response(202)
                self.end_headers()
                return
            self._json(200, responses)
            return
        response = mcp.handle(message)
        if response is None:  # a notification (e.g. notifications/initialized)
            self.send_response(202)
            self.end_headers()
            return
        self._json(200, response)

    def log_message(self, *_args) -> None:  # keep stdout/stderr clean
        pass


def main() -> int:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    auth = "bearer-protected" if TOKEN else "OPEN (no token — local only!)"
    print(f"ygg mcp-http: Streamable-HTTP MCP on http://{HOST}:{PORT}/mcp  [{auth}]",
          file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
