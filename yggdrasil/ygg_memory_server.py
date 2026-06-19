#!/usr/bin/env python3
"""Yggdrasil's own memory engine: a stdlib-only HTTP server over SQLite + FTS5.

This is the DEFAULT Yggdrasil backend. It speaks the same small REST contract
that the Yggdrasil workflow scripts already use, so the CLI (ygg.py), the MCP
facade, and every quality gate work against it unchanged — point YGG_ENGINE_URL
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

try:
    from .ygg_embeddings import OllamaEmbedder, cosine
except ImportError:  # flat layout (deployed scripts dir / tests / direct run)
    from ygg_embeddings import OllamaEmbedder, cosine


DEFAULT_HOST = os.environ.get("YGG_MEMORY_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("YGG_MEMORY_PORT", "42069"))
DEFAULT_TOKEN = (
    os.environ.get("YGG_MEMORY_TOKEN")
    or os.environ.get("YGG_ENGINE_TOKEN")
    or os.environ.get("YGG_ENGINE_TOKEN")
    or "yggdrasil-demo-token"
)
DEFAULT_DB = os.environ.get("YGG_MEMORY_DB") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ygg-memory.sqlite"
)

# Hybrid fusion for dense search. "score" = normalized weighted sum (vector
# weighted above lexical, so a strong semantic / cross-lingual match can outrank
# a coincidental keyword hit); "rrf" = classic reciprocal rank fusion. Tuned
# against eval/ygg_eval.py. Overridable for A/B and operator tuning.
FUSION_MODE = os.environ.get("YGG_FUSION", "score")
FUSION_W_LEX = float(os.environ.get("YGG_FUSION_W_LEX", "0.3"))
FUSION_W_VEC = float(os.environ.get("YGG_FUSION_W_VEC", "1.0"))

# Usage-weighted ranking: how strongly a memory's access frequency boosts its
# score. Saturating (access/(access+scale)) so frequently-recalled memories rise
# but can't run away; exactly 0 for never-accessed memories, so a fresh DB (and
# the eval harness, which never logs access) is never perturbed.
W_USAGE = float(os.environ.get("YGG_W_USAGE", "0.3"))
USAGE_SCALE = float(os.environ.get("YGG_USAGE_SCALE", "5"))

# Pinned memories ("always remember this") get a strong fixed boost so they
# reliably surface near the top of relevant results.
W_PIN = float(os.environ.get("YGG_W_PIN", "0.5"))

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

    def __init__(self, db_path: str, embedder: Any = None):
        self.db_path = db_path
        self.embedder = embedder
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
                metadata_json TEXT,
                embedding     TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_user ON memories(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_scope ON memories(user_id, namespace, project, scope)")
        # Lazy migration for pre-existing DBs created before the embedding column.
        existing_cols = {r[1] for r in cur.execute("PRAGMA table_info(memories)").fetchall()}
        if "embedding" not in existing_cols:
            cur.execute("ALTER TABLE memories ADD COLUMN embedding TEXT")
        if "last_accessed_at" not in existing_cols:
            cur.execute("ALTER TABLE memories ADD COLUMN last_accessed_at REAL")
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
            "last_accessed_at": row["last_accessed_at"] if "last_accessed_at" in row.keys() else None,
            "pinned": bool(metadata.get("pinned")),
            "archived": bool(row["archived"]),
            "metadata": metadata,
        }

    def _embed_raw(self, text: str) -> list[float] | None:
        if self.embedder is None:
            return None
        try:
            return self.embedder.embed(text)
        except Exception:
            return None

    def _embed_json(self, text: str) -> str | None:
        vec = self._embed_raw(text)
        return json.dumps(vec) if vec else None

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
        embedding_json = self._embed_json(content)  # network call outside the lock
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO memories
                    (id,user_id,namespace,scope,project,type,content,content_hash,source,confidence,importance,created_at,access_count,archived,metadata_json,embedding)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?)
                """,
                (
                    memory_id, user_id, namespace, scope, project, mem_type, content,
                    content_hash, source, confidence, importance, created_at,
                    json.dumps(metadata, sort_keys=True), embedding_json,
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
        if data is not None and self.embedder is not None:
            emb_json = self._embed_json(content)  # network call outside the lock
            with self._lock:
                self._conn.execute("UPDATE memories SET embedding=? WHERE seq=?", (emb_json, seq))
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
        if filters.get("tag"):
            where.append(
                "m.metadata_json IS NOT NULL AND EXISTS "
                "(SELECT 1 FROM json_each(m.metadata_json, '$.tags') WHERE json_each.value = ?)"
            )
            params.append(str(filters["tag"]))
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
                rows = self._conn.execute(f"SELECT m.* FROM memories m WHERE {where_sql}", params).fetchall()
            vec_rows = []
            if self.embedder is not None:
                vec_rows = self._conn.execute(
                    f"SELECT m.* FROM memories m WHERE {where_sql} AND m.embedding IS NOT NULL", params
                ).fetchall()

        # Lexical ranking: BM25/overlap relevance + importance + recency boost.
        term_set = set(terms)
        records: dict[str, dict[str, Any]] = {}
        lex_scored: list[dict[str, Any]] = []
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
            access = float(record.get("access_count") or 0.0)
            usage = W_USAGE * (access / (access + USAGE_SCALE)) if access > 0 else 0.0
            pin = W_PIN if (record.get("metadata") or {}).get("pinned") else 0.0
            record["lexical_score"] = round(relevance + 0.25 * importance + recency + usage + pin, 6)
            records[record["id"]] = record
            lex_scored.append(record)
        lex_scored.sort(key=lambda r: r["lexical_score"], reverse=True)

        # Pure-lexical mode (dense disabled): composite ranking is the result.
        if self.embedder is None:
            for r in lex_scored:
                r["score"] = r["lexical_score"]
            return lex_scored[:limit]

        # Dense ranking: cosine of the query vs stored embeddings over the scoped set.
        query_vec = self._embed_raw(query)
        vec_scored: list[dict[str, Any]] = []
        if query_vec:
            for row in vec_rows:
                try:
                    emb = json.loads(row["embedding"])
                except (json.JSONDecodeError, TypeError):
                    continue
                sim = cosine(query_vec, emb)
                if sim <= 0:
                    continue
                record = records.get(row["id"]) or self._row_to_record(row)
                record["vector_score"] = round(sim, 6)
                records[record["id"]] = record
                vec_scored.append(record)
            vec_scored.sort(key=lambda r: r["vector_score"], reverse=True)

        fused: dict[str, float] = {}
        if FUSION_MODE == "rrf":
            # Classic reciprocal rank fusion (rank-only).
            K = 60
            lex_rank = {r["id"]: i + 1 for i, r in enumerate(lex_scored)}
            vec_rank = {r["id"]: i + 1 for i, r in enumerate(vec_scored)}
            for mid in set(lex_rank) | set(vec_rank):
                fused[mid] = (1.0 / (K + lex_rank[mid]) if mid in lex_rank else 0.0) \
                    + (1.0 / (K + vec_rank[mid]) if mid in vec_rank else 0.0)
        else:
            # Score-normalized weighted sum: normalize each signal to its
            # in-result max, then weight (vector higher). Lets a strong vector
            # match — e.g. a cross-lingual hit with no lexical overlap — outrank
            # a coincidental keyword match, which rank-only RRF cannot.
            max_lex = max((r["lexical_score"] for r in lex_scored), default=0.0) or 1.0
            max_vec = max((r["vector_score"] for r in vec_scored), default=0.0) or 1.0
            for mid, rec in records.items():
                lex_norm = (rec.get("lexical_score") or 0.0) / max_lex
                vec_norm = (rec.get("vector_score") or 0.0) / max_vec
                fused[mid] = FUSION_W_LEX * lex_norm + FUSION_W_VEC * vec_norm
        result = []
        for mid, score in sorted(fused.items(), key=lambda kv: kv[1], reverse=True):
            rec = records[mid]
            rec["score"] = round(score, 6)
            result.append(rec)
        return result[:limit]

    def record_access(self, ids: list[str]) -> None:
        """Log that these memories were surfaced (the usage signal feeding
        usage-weighted ranking). Called by the HTTP /search route, NOT by
        search() itself — so direct callers (e.g. the eval harness) stay
        side-effect-free and deterministic."""
        ids = [i for i in (ids or []) if i]
        if not ids:
            return
        now = time.time()
        with self._lock:
            self._conn.executemany(
                "UPDATE memories SET access_count = access_count + 1, last_accessed_at = ? WHERE id = ?",
                [(now, i) for i in ids],
            )
            self._conn.commit()

    def reindex_embeddings(self) -> int:
        """Embed any rows missing an embedding — self-heals after a cold-start
        timeout, or when dense is enabled after content already exists."""
        if self.embedder is None:
            return 0
        with self._lock:
            rows = self._conn.execute("SELECT seq, content FROM memories WHERE embedding IS NULL").fetchall()
        healed = 0
        for row in rows:
            emb_json = self._embed_json(row["content"])
            if emb_json:
                with self._lock:
                    self._conn.execute("UPDATE memories SET embedding=? WHERE seq=?", (emb_json, row["seq"]))
                    self._conn.commit()
                healed += 1
        return healed


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
            self.store.record_access([r.get("id") for r in data])
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
    parser.add_argument("--embed-model", default=os.environ.get("YGG_EMBED_MODEL"),
                        help="Embedding model for dense search (e.g. all-minilm). Default: off (lexical).")
    parser.add_argument("--embed-url", default=os.environ.get("YGG_EMBED_URL", "http://127.0.0.1:11434"),
                        help="Ollama base URL for embeddings.")
    args = parser.parse_args()

    if args.reset and os.path.exists(args.db):
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(args.db + suffix)
            except FileNotFoundError:
                pass

    embedder = OllamaEmbedder(args.embed_url, args.embed_model) if args.embed_model else None
    if embedder is not None:
        embedder.embed("warmup")  # load the model before serving so the first adds don't time out
    store = MemoryStore(args.db, embedder=embedder)
    if embedder is not None:
        healed = store.reindex_embeddings()
        if healed:
            print(f"ygg-memory: backfilled {healed} missing embeddings", flush=True)
    Handler.store = store
    Handler.token = args.token

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"ygg-memory: listening on http://{args.host}:{args.port}  db={args.db}  "
        f"fts5={'on' if store.use_fts else 'off (python fallback)'}  "
        f"dense={args.embed_model or 'off'}",
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
