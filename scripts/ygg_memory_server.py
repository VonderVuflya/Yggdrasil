#!/usr/bin/env python3
"""Yggdrasil's own memory engine: a stdlib-only HTTP server over SQLite + FTS5.

This is the DEFAULT Yggdrasil backend. It speaks the same small REST contract
that the Yggdrasil workflow scripts already use, so the CLI (ygg.py), the MCP
facade, and every quality gate work against it unchanged — point YGG_MUNINN_URL
at this server instead of an external engine.

Design notes:
- Zero heavy dependencies: only the Python standard library (http.server,
  sqlite3, json, uuid). sqlite3 ships FTS5 on virtually all modern builds; if
  FTS5 is unavailable we transparently fall back to in-Python token ranking.
- Raw POST /add ALWAYS inserts a new record (no backend-side dedupe). Dedupe is
  intentionally a wrapper-layer concern (ygg.py), so the review/governance loop
  can still surface and archive duplicates. This mirrors the contract the rest
  of the system was written against.

Contract (all JSON):
  GET  /health                      -> {"status":"ok", "memory_count":N, ...}   (no auth)
  POST /add      {content,user_id,namespace,scope,metadata}  -> {"success":true,"data":{...}}
  POST /search   {query,user_id,limit,rerank,filters,namespaces,explain} -> {"data":[...]}
  GET  /get_all?user_id=&limit=&namespace=  -> {"data":[...]}
  PUT  /update   {memory_id,data?,metadata_patch?,archived?}  -> {"success":true,"data":{...}}

Auth: every endpoint except /health requires `Authorization: Bearer <token>`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


DEFAULT_HOST = os.environ.get("YGG_MEMORY_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("YGG_MEMORY_PORT", "42069"))
DEFAULT_TOKEN = (
    os.environ.get("YGG_MEMORY_TOKEN")
    or os.environ.get("YGG_MUNINN_TOKEN")
    or os.environ.get("MUNINN_AUTH_TOKEN")
    or "yggdrasil-demo-token"
)
DEFAULT_DB = os.environ.get("YGG_MEMORY_DB") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ygg-memory.sqlite"
)

# Small stopword set so natural-language paraphrase queries still match on the
# content words rather than being diluted by glue words.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "has",
    "have", "in", "into", "is", "it", "its", "of", "on", "or", "that", "the",
    "than", "to", "was", "were", "will", "with",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
# Split camelCase / PascalCase: "scrollWidth" -> [scroll, Width],
# "getBoundingClientRect" -> [get, Bounding, Client, Rect], "HTMLParser" -> [HTML, Parser].
_CAMEL_SPLIT_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= 2 and t not in STOPWORDS]


def expand_identifiers(text: str) -> str:
    """Append space-split forms of camelCase/PascalCase identifiers so code
    memory is searchable by words (e.g. 'scrollWidth' also matches 'scroll width').
    Original text is preserved; split forms are appended."""
    if not text:
        return text
    extra: list[str] = []
    for word in _WORD_RE.findall(text):
        parts = _CAMEL_SPLIT_RE.findall(word)
        if len(parts) > 1:
            extra.append(" ".join(parts))
    return text + (" " + " ".join(extra)) if extra else text


class MemoryStore:
    """SQLite-backed memory store with FTS5 (or in-Python fallback) search."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.use_fts = self._init_schema()

    def _init_schema(self) -> bool:
        cur = self._conn
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                seq           INTEGER PRIMARY KEY AUTOINCREMENT,
                id            TEXT UNIQUE NOT NULL,
                user_id       TEXT NOT NULL,
                namespace     TEXT,
                scope         TEXT,
                project       TEXT,
                type          TEXT,
                content       TEXT NOT NULL,
                content_hash  TEXT,
                source        TEXT,
                confidence    REAL,
                importance    REAL DEFAULT 0.5,
                created_at    REAL NOT NULL,
                access_count  INTEGER DEFAULT 0,
                archived      INTEGER DEFAULT 0,
                metadata_json TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_user ON memories(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_scope ON memories(user_id, namespace, project, scope)")
        use_fts = True
        try:
            cur.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(content, tokenize='porter unicode61')"
            )
        except sqlite3.OperationalError:
            use_fts = False
        self._conn.commit()
        return use_fts

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        try:
            metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        except (json.JSONDecodeError, TypeError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "id": row["id"],
            "memory": row["content"],
            "content": row["content"],
            "user_id": row["user_id"],
            "namespace": row["namespace"],
            "scope": row["scope"],
            "project": row["project"],
            "type": row["type"],
            "memory_type": row["type"],
            "source": row["source"],
            "confidence": row["confidence"],
            "importance": row["importance"],
            "created_at": row["created_at"],
            "access_count": row["access_count"],
            "archived": bool(row["archived"]),
            "metadata": metadata,
        }

    # ---- write path --------------------------------------------------------

    def add(self, *, content: str, user_id: str, namespace: str | None, scope: str | None, metadata: dict[str, Any]) -> dict[str, Any]:
        memory_id = "ygg_" + uuid.uuid4().hex
        created_at = time.time()
        project = metadata.get("project")
        mem_type = metadata.get("type")
        source = metadata.get("source")
        confidence = metadata.get("confidence")
        content_hash = metadata.get("content_hash")
        importance = float(metadata.get("importance", 0.5)) if metadata.get("importance") is not None else 0.5
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO memories
                    (id,user_id,namespace,scope,project,type,content,content_hash,source,confidence,importance,created_at,access_count,archived,metadata_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,0,?)
                """,
                (
                    memory_id, user_id, namespace, scope, project, mem_type, content,
                    content_hash, source, confidence, importance, created_at,
                    json.dumps(metadata, sort_keys=True),
                ),
            )
            seq = cur.lastrowid
            if self.use_fts:
                self._conn.execute("INSERT INTO mem_fts(rowid, content) VALUES (?, ?)", (seq, expand_identifiers(content)))
            self._conn.commit()
            row = self._conn.execute("SELECT * FROM memories WHERE seq=?", (seq,)).fetchone()
        record = self._row_to_record(row)
        record["event"] = "ADD"
        return record

    def update(self, memory_id: str, *, data: str | None, metadata_patch: dict[str, Any] | None, archived: bool | None) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            if row is None:
                return None
            seq = row["seq"]
            content = row["content"]
            try:
                metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            except (json.JSONDecodeError, TypeError):
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}

            if data is not None:
                content = data
            if metadata_patch:
                metadata.update(metadata_patch)
            archived_flag = row["archived"]
            if archived is not None:
                archived_flag = 1 if archived else 0
                if archived:
                    metadata["status"] = "archived"

            self._conn.execute(
                "UPDATE memories SET content=?, project=?, type=?, source=?, archived=?, metadata_json=? WHERE seq=?",
                (
                    content,
                    metadata.get("project", row["project"]),
                    metadata.get("type", row["type"]),
                    metadata.get("source", row["source"]),
                    archived_flag,
                    json.dumps(metadata, sort_keys=True),
                    seq,
                ),
            )
            if data is not None and self.use_fts:
                self._conn.execute("UPDATE mem_fts SET content=? WHERE rowid=?", (expand_identifiers(content), seq))
            self._conn.commit()
            row = self._conn.execute("SELECT * FROM memories WHERE seq=?", (seq,)).fetchone()
        return self._row_to_record(row)

    # ---- read path ---------------------------------------------------------

    def get_all(self, *, user_id: str, limit: int, namespace: str | None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM memories WHERE user_id=?"
        params: list[Any] = [user_id]
        if namespace:
            sql += " AND namespace=?"
            params.append(namespace)
        sql += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def search(
        self,
        *,
        query: str,
        user_id: str,
        limit: int,
        filters: dict[str, Any] | None,
        namespaces: list[str] | None,
    ) -> list[dict[str, Any]]:
        filters = filters or {}
        terms = tokenize(expand_identifiers(query))
        if not terms:
            return []

        where = ["m.user_id=?", "m.archived=0"]
        params: list[Any] = [user_id]
        if filters.get("project"):
            where.append("m.project=?")
            params.append(filters["project"])
        if filters.get("scope"):
            where.append("m.scope=?")
            params.append(filters["scope"])
        if filters.get("type"):
            where.append("m.type=?")
            params.append(filters["type"])
        if namespaces:
            placeholders = ",".join("?" for _ in namespaces)
            where.append(f"m.namespace IN ({placeholders})")
            params.extend(namespaces)
        where_sql = " AND ".join(where)

        now = time.time()
        with self._lock:
            if self.use_fts:
                match_query = " OR ".join(f'"{term}"' for term in terms)
                sql = (
                    "SELECT m.*, bm25(mem_fts) AS rank FROM mem_fts "
                    "JOIN memories m ON m.seq = mem_fts.rowid "
                    f"WHERE mem_fts MATCH ? AND {where_sql}"
                )
                rows = self._conn.execute(sql, [match_query, *params]).fetchall()
            else:
                sql = f"SELECT m.* FROM memories m WHERE {where_sql}"
                rows = self._conn.execute(sql, params).fetchall()

        # Composite ranking: lexical relevance + importance + recency boost.
        # (The architecture calls for a recency/importance boost on top of
        # BM25; without it single-match BM25 scores collapse toward 0.)
        term_set = set(terms)
        scored = []
        for row in rows:
            if self.use_fts:
                relevance = max(0.0, -float(row["rank"]))  # bm25: more negative = better
            else:
                doc_terms = tokenize(expand_identifiers(row["content"]))
                overlap = sum(1 for t in doc_terms if t in term_set) if doc_terms else 0
                if overlap <= 0:
                    continue  # FTS MATCH already filters; the fallback must too
                relevance = overlap / (len(doc_terms) ** 0.5)
            record = self._row_to_record(row)
            importance = float(record.get("importance") or 0.5)
            age_days = max(0.0, (now - float(record.get("created_at") or now)) / 86400.0)
            recency = 0.5 * (0.5 ** (age_days / 30.0))  # 30-day half-life, max 0.5
            record["score"] = round(relevance + 0.25 * importance + recency, 6)
            scored.append(record)
        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:limit]


class Handler(BaseHTTPRequestHandler):
    server_version = "YggMemory/0.1"
    store: MemoryStore = None  # type: ignore[assignment]
    token: str = DEFAULT_TOKEN

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter logs
        if os.environ.get("YGG_MEMORY_VERBOSE"):
            super().log_message(fmt, *args)

    # ---- plumbing ----------------------------------------------------------

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        return header == f"Bearer {self.token}"

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    # ---- routes ------------------------------------------------------------

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, {
                "status": "ok",
                "memory_count": self.store.count(),
                "graph_nodes": 0,
                "reranker": "inactive",
                "backend": "ygg-sqlite-fts5" if self.store.use_fts else "ygg-sqlite-fallback",
            })
            return
        if not self._authorized():
            self._send(401, {"success": False, "error": "unauthorized"})
            return
        if parsed.path == "/get_all":
            qs = parse_qs(parsed.query)
            user_id = (qs.get("user_id") or ["global_user"])[0]
            limit = int((qs.get("limit") or ["1000"])[0])
            namespace = (qs.get("namespace") or [None])[0]
            data = self.store.get_all(user_id=user_id, limit=limit, namespace=namespace)
            self._send(200, {"success": True, "data": data})
            return
        self._send(404, {"success": False, "error": f"not found: {parsed.path}"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(401, {"success": False, "error": "unauthorized"})
            return
        parsed = urlparse(self.path)
        body = self._read_json()
        if parsed.path == "/add":
            content = body.get("content")
            if not content:
                self._send(400, {"success": False, "error": "content is required"})
                return
            metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
            record = self.store.add(
                content=str(content),
                user_id=str(body.get("user_id") or "global_user"),
                namespace=body.get("namespace"),
                scope=body.get("scope") or metadata.get("scope"),
                metadata=metadata,
            )
            self._send(200, {"success": True, "data": record})
            return
        if parsed.path == "/search":
            data = self.store.search(
                query=str(body.get("query") or ""),
                user_id=str(body.get("user_id") or "global_user"),
                limit=int(body.get("limit") or 5),
                filters=body.get("filters") if isinstance(body.get("filters"), dict) else {},
                namespaces=body.get("namespaces") if isinstance(body.get("namespaces"), list) else None,
            )
            self._send(200, {"success": True, "data": data})
            return
        self._send(404, {"success": False, "error": f"not found: {parsed.path}"})

    def do_PUT(self) -> None:
        if not self._authorized():
            self._send(401, {"success": False, "error": "unauthorized"})
            return
        parsed = urlparse(self.path)
        if parsed.path == "/update":
            body = self._read_json()
            memory_id = body.get("memory_id")
            if not memory_id:
                self._send(400, {"success": False, "error": "memory_id is required"})
                return
            record = self.store.update(
                str(memory_id),
                data=body.get("data"),
                metadata_patch=body.get("metadata_patch") if isinstance(body.get("metadata_patch"), dict) else None,
                archived=body.get("archived"),
            )
            if record is None:
                self._send(404, {"success": False, "error": f"memory not found: {memory_id}"})
                return
            self._send(200, {"success": True, "data": record})
            return
        self._send(404, {"success": False, "error": f"not found: {parsed.path}"})


def main() -> int:
    parser = argparse.ArgumentParser(description="Yggdrasil's own SQLite+FTS5 memory engine (REST).")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    parser.add_argument("--reset", action="store_true", help="Delete the database file before starting (clean run).")
    args = parser.parse_args()

    if args.reset and os.path.exists(args.db):
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(args.db + suffix)
            except FileNotFoundError:
                pass

    store = MemoryStore(args.db)
    Handler.store = store
    Handler.token = args.token

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"ygg-memory: listening on http://{args.host}:{args.port}  db={args.db}  "
        f"fts5={'on' if store.use_fts else 'off (python fallback)'}",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
