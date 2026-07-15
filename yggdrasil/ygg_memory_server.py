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
import array
import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import sys
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

try:
    from . import ygg_config as _cfg
except ImportError:
    import ygg_config as _cfg


# Identity migration: rebrand legacy demo memory to the configured default once.
# Version-guarded via `PRAGMA user_version` so it runs exactly once per DB.
IDENTITY_MIGRATION_VERSION = 1


def rebrand_legacy_identity(user_id: str | None, ns: str | None) -> tuple[str | None, str | None]:
    """Map the legacy demo (user_id, namespace) pair to the configured default;
    pass anything else through unchanged. Used by both the one-time DB migration
    and the sync-import path, so a lagging demo-keyed peer auto-adopts on pull."""
    if user_id == _cfg.DEMO_USER_ID and ns == _cfg.DEMO_NAMESPACE:
        return _cfg.DEFAULT_USER_ID, _cfg.DEFAULT_NAMESPACE
    return user_id, ns


def migrate_identity(conn: sqlite3.Connection, *, dry_run: bool = False,
                     backup_path: str | None = None) -> dict[str, Any]:
    """Idempotent, user_version-guarded rebrand of legacy demo identity
    (demo-user / yggdrasil-demo) to the configured default. Only touches rows
    matching the exact legacy PAIR, so a user's custom identity is never moved.
    FTS mirrors content, not identity, so it needs no update. Returns a summary."""
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    if ver >= IDENTITY_MIGRATION_VERSION:
        return {"migrated": 0, "already": True, "backup": None}
    n = conn.execute("SELECT COUNT(*) FROM memories WHERE user_id=? AND namespace=?",
                     (_cfg.DEMO_USER_ID, _cfg.DEMO_NAMESPACE)).fetchone()[0]
    if dry_run:
        return {"migrated": n, "already": False, "backup": None, "dry_run": True}
    used_backup = None
    if n and backup_path:
        conn.commit()  # VACUUM INTO must run outside a transaction
        conn.execute("VACUUM INTO ?", (backup_path,))
        used_backup = backup_path
    with conn:  # one transaction: relabel + version bump commit or roll back together
        if n:
            conn.execute(
                "UPDATE memories SET user_id=?, namespace=? WHERE user_id=? AND namespace=?",
                (_cfg.DEFAULT_USER_ID, _cfg.DEFAULT_NAMESPACE, _cfg.DEMO_USER_ID, _cfg.DEMO_NAMESPACE))
            conn.execute("UPDATE relations SET user_id=? WHERE user_id=?",
                         (_cfg.DEFAULT_USER_ID, _cfg.DEMO_USER_ID))
        conn.execute(f"PRAGMA user_version={IDENTITY_MIGRATION_VERSION}")
    if n:
        # Convert the implicit default into an explicit config pin so no FUTURE
        # default change can ever strand this machine's memories again.
        try:
            _cfg.pin_default_identity()
        except OSError:
            pass
    return {"migrated": n, "already": False, "backup": used_backup}


DEFAULT_HOST = os.environ.get("YGG_MEMORY_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("YGG_MEMORY_PORT", "42069"))
# No hardcoded fallback: when neither env var nor --token/--token-file provides a
# secret, main() reuses (or generates) the ~/.yggdrasil/token file instead of a
# publicly-known demo constant — a bare `ygg serve` must never be open to every
# local process. Clients (ygg_core, hooks, doctor) already read the same file.
DEFAULT_TOKEN = (
    os.environ.get("YGG_MEMORY_TOKEN")
    or os.environ.get("YGG_ENGINE_TOKEN")
    or ""
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

# Dense (semantic) search scores cosine in pure Python over every scoped
# embedding — fine for personal scale, but it grows linearly with the store.
# Past this many memories WITH an embedding model active, suggest pointing
# YGG_ENGINE_URL at a dedicated vector backend (Qdrant/etc.). Lexical/FTS5 is
# indexed and scales fine, so the hint only fires when dense is on.
VECTOR_WARN_AT = int(os.environ.get("YGG_VECTOR_WARN_AT", "20000"))

# Small stopword set so natural-language paraphrase queries still match on the
# content words rather than being diluted by glue words.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "has",
    "have", "in", "into", "is", "it", "its", "of", "on", "or", "that", "the",
    "than", "to", "was", "were", "will", "with",
}

# Unicode-aware: [^\W_] matches letters/digits in ANY script (Cyrillic, Greek,
# CJK, …) but not underscore, so snake_case still splits into words. The FTS
# index side already tokenizes with unicode61 — both sides now agree on
# non-Latin text (an ASCII-only regex here made every non-Latin query match
# nothing in lexical mode).
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
# Split camelCase / PascalCase: "scrollWidth" -> [scroll, Width],
# "getBoundingClientRect" -> [get, Bounding, Client, Rect], "HTMLParser" -> [HTML, Parser].
_CAMEL_SPLIT_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= 2 and t not in STOPWORDS]


# Last-line-of-defense secret guard AT THE ENGINE, so a raw POST /add that bypasses
# the CLI's broader heuristic still can't persist an obvious credential. Deliberately
# only HIGH-CONFIDENCE *structured tokens* (not a generic "password: …" heuristic),
# so legitimate memories that merely mention a password aren't rejected.
_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
]


def looks_like_secret(text: str) -> str | None:
    """Return the matched secret snippet (truncated) if `text` contains an obvious
    credential, else None."""
    for pat in _SECRET_PATTERNS:
        m = pat.search(text or "")
        if m:
            return m.group(0)[:64]
    return None


# --- vector storage helpers -------------------------------------------------
# Embeddings are stored as packed float32 BLOBs (4 bytes/dim) rather than JSON
# text (~15 bytes/dim) — ~4× smaller on disk AND no json.loads on the hot path.
# The store keeps an in-process cache of UNIT-normalized vectors, so cosine
# collapses to a plain dot product and each row is parsed at most once.

def _vec_to_blob(vec) -> bytes:
    return array.array("f", vec).tobytes()


def _blob_to_array(blob: bytes) -> "array.array":
    a = array.array("f")
    a.frombytes(blob)
    return a


def _unit(vec) -> "array.array | None":
    """Unit-length float32 copy of vec, or None for an empty/zero vector."""
    norm = math.sqrt(sum(x * x for x in vec)) if vec else 0.0
    if not norm:
        return None
    return array.array("f", [x / norm for x in vec])


def _dot(a, b) -> float | None:
    """Dot product of two equal-length vectors; None if the dimensions differ
    (e.g. the embedding model changed and this row hasn't been reindexed)."""
    if len(a) != len(b):
        return None
    return sum(x * y for x, y in zip(a, b))


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
        # One-time identity migration: rebrand legacy demo memory to the default.
        # Guarded by user_version, backup-first; must never crash the engine, so a
        # failure just leaves user_version=0 and is retried on the next start.
        try:
            res = migrate_identity(
                self._conn,
                backup_path=f"{self.db_path}.pre-identity-v{IDENTITY_MIGRATION_VERSION}.{int(time.time())}.bak")
            if res.get("migrated"):
                sys.stderr.write(
                    f"[yggdrasil] identity migration: rebranded {res['migrated']} memories "
                    f"{_cfg.DEMO_USER_ID}/{_cfg.DEMO_NAMESPACE} -> "
                    f"{_cfg.DEFAULT_USER_ID}/{_cfg.DEFAULT_NAMESPACE}"
                    + (f" (backup: {res['backup']})" if res.get("backup") else "") + "\n")
        except sqlite3.Error as exc:
            sys.stderr.write(f"[yggdrasil] identity migration skipped (retried next start): {exc}\n")
        # Name of the embedding model this process produces vectors with — stored
        # per row so a model switch can be detected and reindexed (item: model
        # versioning), and so mixed-model rows are never silently cosine-compared.
        self._embed_model = getattr(self.embedder, "model", None) if self.embedder else None
        # seq -> unit vector. Built once at startup (single-threaded here) and
        # kept warm incrementally on every write; None-guarded so lexical-only
        # runs pay nothing.
        self._vec_cache: dict[int, "array.array"] = {}
        if self.embedder is not None:
            self._load_vec_cache()

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
        # Backs get_all's `WHERE user_id[,namespace] ORDER BY created_at` — the
        # session-start hook hits it every session; without it that's a full
        # scan + sort of the whole store per call.
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_created ON memories(user_id, namespace, created_at)")
        # Indexed dedup lookup — O(log n) content-hash check at any store size (no 1000-row cap).
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_hash ON memories(user_id, project, type, content_hash)")
        # Relation graph: typed edges between memories (SOLVES / SUPERSEDES /
        # CONTRADICTS). UNIQUE makes relate() idempotent; edges are hard-deleted
        # with their endpoints (an edge without a node answers no question).
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS relations (
                seq        INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id    TEXT NOT NULL,
                to_id      TEXT NOT NULL,
                rel_type   TEXT NOT NULL,
                user_id    TEXT NOT NULL,
                source     TEXT,
                created_at REAL NOT NULL,
                UNIQUE(from_id, to_id, rel_type)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rel_from ON relations(from_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rel_to ON relations(to_id)")
        # Lazy migration for pre-existing DBs created before these columns.
        existing_cols = {r[1] for r in cur.execute("PRAGMA table_info(memories)").fetchall()}
        if "embedding" not in existing_cols:
            cur.execute("ALTER TABLE memories ADD COLUMN embedding TEXT")
        if "last_accessed_at" not in existing_cols:
            cur.execute("ALTER TABLE memories ADD COLUMN last_accessed_at REAL")
        if "embedding_blob" not in existing_cols:
            cur.execute("ALTER TABLE memories ADD COLUMN embedding_blob BLOB")
        if "embed_model" not in existing_cols:
            cur.execute("ALTER TABLE memories ADD COLUMN embed_model TEXT")
        # One-time backfill: convert any legacy JSON-text embeddings to packed
        # float32 blobs (tagged '(legacy)' so a later reindex re-embeds them with
        # the real model name). Bounded, runs once — after it, only blobs matter.
        legacy = cur.execute(
            "SELECT seq, embedding FROM memories WHERE embedding IS NOT NULL AND embedding_blob IS NULL"
        ).fetchall()
        for r in legacy:
            try:
                vec = json.loads(r["embedding"])
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(vec, list) and vec:
                cur.execute("UPDATE memories SET embedding_blob=?, embed_model=COALESCE(embed_model, '(legacy)') WHERE seq=?",
                            (_vec_to_blob(vec), r["seq"]))
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

    def _load_vec_cache(self) -> None:
        """Parse every stored blob into a unit vector once (called single-threaded
        at startup, or under the lock when rebuilding)."""
        cache: dict[int, "array.array"] = {}
        for row in self._conn.execute(
            "SELECT seq, embedding_blob FROM memories WHERE embedding_blob IS NOT NULL"
        ):
            unit = _unit(_blob_to_array(row["embedding_blob"]))
            if unit is not None:
                cache[row["seq"]] = unit
        self._vec_cache = cache

    def _user_signal(self, record: dict[str, Any]) -> float:
        """The explicitly-earned ranking boosts: pin + usage. Applied on the
        vector-only path too, so a pinned / frequently-recalled memory surfaced
        purely by meaning gets the same lift a lexical hit does. Importance and
        recency are left to the lexical path (they're near-uniform and always
        present, so adding them to vector-only hits would perturb ranking without
        a user having asked for it)."""
        access = float(record.get("access_count") or 0.0)
        usage = W_USAGE * (access / (access + USAGE_SCALE)) if access > 0 else 0.0
        pin = W_PIN if (record.get("metadata") or {}).get("pinned") else 0.0
        return usage + pin

    def _row_unit(self, row) -> "array.array | None":
        """Unit vector for a row: cache hit, else parse its blob once and warm
        the cache. Keeps the cache an optimization, not a correctness requirement
        (rows added while dense was off, or inserted directly, still resolve)."""
        cv = self._vec_cache.get(row["seq"])
        if cv is not None:
            return cv
        blob = row["embedding_blob"] if "embedding_blob" in row.keys() else None
        if not blob:
            return None
        unit = _unit(_blob_to_array(blob))
        if unit is not None:
            self._vec_cache[row["seq"]] = unit
        return unit

    def _store_embedding_locked(self, seq: int, vec) -> None:
        """Persist vec as a float32 blob + model tag and refresh the warm cache.
        The caller must hold self._lock (and own the surrounding transaction)."""
        if vec:
            self._conn.execute("UPDATE memories SET embedding_blob=?, embed_model=? WHERE seq=?",
                               (_vec_to_blob(vec), self._embed_model, seq))
            unit = _unit(vec)
            if unit is not None:
                self._vec_cache[seq] = unit
            else:
                self._vec_cache.pop(seq, None)
        else:
            self._conn.execute("UPDATE memories SET embedding_blob=NULL, embed_model=NULL WHERE seq=?", (seq,))
            self._vec_cache.pop(seq, None)

    # ---- write path --------------------------------------------------------

    def add(self, *, content: str, user_id: str, namespace: str | None, scope: str | None,
            metadata: dict[str, Any], dedupe_threshold: float | None = None) -> dict[str, Any]:
        memory_id = "ygg_" + uuid.uuid4().hex
        created_at = time.time()
        project = metadata.get("project")
        mem_type = metadata.get("type")
        source = metadata.get("source")
        confidence = metadata.get("confidence")
        content_hash = metadata.get("content_hash")
        importance = float(metadata.get("importance", 0.5)) if metadata.get("importance") is not None else 0.5
        vec = self._embed_raw(content)  # network call outside the lock
        embedding_blob = _vec_to_blob(vec) if vec else None
        embed_model = self._embed_model if vec else None
        # Semantic dedup (only when dense is on): reuse this one embedding to skip
        # a write that's near-identical to an existing memory in the same scope.
        if dedupe_threshold is not None and vec:
            existing = self.find_similar(user_id=user_id, project=project, mem_type=mem_type,
                                         vec=vec, threshold=float(dedupe_threshold))
            if existing is not None:
                existing["event"] = "SEMANTIC_DUPLICATE"
                return existing
        with self._lock:
            # One transaction for row + FTS: an exception rolls BOTH back instead of
            # leaking a half-written memory the next commit would silently flush
            # (a memories row with no mem_fts row is invisible to lexical search).
            with self._conn:
                cur = self._conn.execute(
                    """
                    INSERT INTO memories
                        (id,user_id,namespace,scope,project,type,content,content_hash,source,confidence,importance,created_at,access_count,archived,metadata_json,embedding_blob,embed_model)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?,?)
                    """,
                    (
                        memory_id, user_id, namespace, scope, project, mem_type, content,
                        content_hash, source, confidence, importance, created_at,
                        json.dumps(metadata, sort_keys=True), embedding_blob, embed_model,
                    ),
                )
                seq = cur.lastrowid
                if self.use_fts:
                    self._conn.execute("INSERT INTO mem_fts(rowid, content) VALUES (?, ?)", (seq, expand_identifiers(content)))
            if vec:  # keep the warm cache in sync
                unit = _unit(vec)
                if unit is not None:
                    self._vec_cache[seq] = unit
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

            content_hash = row["content_hash"]
            if data is not None:
                content = data
                # Edited content gets a fresh hash — a stale one corrupts dedup both
                # ways (old text wrongly rejected, new text freely duplicable).
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                metadata["content_hash"] = content_hash
            if metadata_patch:
                metadata.update(metadata_patch)
            archived_flag = row["archived"]
            if archived is not None:
                archived_flag = 1 if archived else 0
                if archived:
                    metadata["status"] = "archived"

            with self._conn:  # row + FTS in one transaction (rollback on error)
                self._conn.execute(
                    "UPDATE memories SET content=?, content_hash=?, project=?, type=?, source=?, archived=?, metadata_json=? WHERE seq=?",
                    (
                        content,
                        content_hash,
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
            row = self._conn.execute("SELECT * FROM memories WHERE seq=?", (seq,)).fetchone()
        if data is not None and self.embedder is not None:
            vec = self._embed_raw(content)  # network call outside the lock
            with self._lock:
                with self._conn:
                    self._store_embedding_locked(seq, vec)
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

    def quality_report(self, *, user_id: str, namespace: str | None = None,
                       near_dup_threshold: float = 0.95, max_items: int = 50) -> dict[str, Any]:
        """Hard health metrics for the store: type/project distribution, exact +
        near-duplicate pairs (cosine >= threshold), cross-project leakage, and
        likely-truncated records. Vectors never leave the engine — only the
        derived report does. O(n^2) over embedded live memories; bounded and
        on-demand, so fine for a personal store (thousands, not millions)."""
        sql = ("SELECT id, project, type, content, content_hash, embedding_blob "
               "FROM memories WHERE user_id=? AND archived=0")
        params: list[Any] = [user_id]
        if namespace:
            sql += " AND namespace=?"
            params.append(namespace)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
            arch_sql = "SELECT COUNT(*) FROM memories WHERE user_id=? AND archived=1"
            arch_params: list[Any] = [user_id]
            if namespace:
                arch_sql += " AND namespace=?"
                arch_params.append(namespace)
            archived = self._conn.execute(arch_sql, arch_params).fetchone()[0]

        # Reuse the write-path truncation heuristic so "truncated" means the same
        # thing here as at ingest. Handle BOTH package and flat layouts (the daemon
        # runs as a bare script), degrading gracefully only if seed is truly absent.
        try:
            try:
                from . import ygg_seed as _seed
            except ImportError:  # flat layout (deployed scripts dir / bare script)
                import ygg_seed as _seed  # type: ignore
            looks_trunc = _seed._looks_truncated
        except Exception:  # noqa: BLE001
            looks_trunc = lambda _s: False  # noqa: E731

        by_type: dict[str, int] = {}
        by_project: dict[str, int] = {}
        seen_hash: dict[str, str] = {}
        exact_dupes: list[dict[str, str]] = []
        truncated: list[str] = []
        embedded: list[tuple[str, str, Any]] = []  # (id, project, unit vector)
        for r in rows:
            proj, typ = r["project"] or "—", r["type"] or "—"
            by_type[typ] = by_type.get(typ, 0) + 1
            by_project[proj] = by_project.get(proj, 0) + 1
            h = r["content_hash"]
            if h:
                if h in seen_hash:
                    exact_dupes.append({"a": seen_hash[h], "b": r["id"]})
                else:
                    seen_hash[h] = r["id"]
            if looks_trunc(r["content"] or ""):
                truncated.append(r["id"])
            if r["embedding_blob"]:
                u = _unit(_blob_to_array(r["embedding_blob"]))
                if u is not None:
                    embedded.append((r["id"], proj, u))

        near_dupes: list[dict[str, Any]] = []
        leakage: list[dict[str, Any]] = []
        for i in range(len(embedded)):
            id_i, pi, ui = embedded[i]
            for j in range(i + 1, len(embedded)):
                id_j, pj, uj = embedded[j]
                dot = sum(a * b for a, b in zip(ui, uj))  # unit vectors -> dot == cosine
                if dot >= near_dup_threshold:
                    pair = {"a": id_i, "b": id_j, "cosine": round(float(dot), 4),
                            "projects": sorted({pi, pj}), "same_project": pi == pj}
                    near_dupes.append(pair)
                    if pi != pj:
                        leakage.append(pair)
        near_dupes.sort(key=lambda p: -p["cosine"])
        leakage.sort(key=lambda p: -p["cosine"])
        return {
            "total": len(rows), "archived": archived, "embedded": len(embedded),
            "by_type": by_type, "by_project": by_project,
            "exact_duplicate_pairs": len(exact_dupes), "exact_duplicates": exact_dupes[:max_items],
            "near_duplicate_pairs": len(near_dupes), "near_duplicates": near_dupes[:max_items],
            "cross_project_leakage_pairs": len(leakage), "cross_project_leakage": leakage[:max_items],
            "truncated_count": len(truncated), "truncated_ids": truncated[:max_items],
            "near_dup_threshold": near_dup_threshold,
        }

    def get_by_id(self, memory_id: str) -> dict[str, Any] | None:
        """Direct indexed lookup by memory id (any store size, archived included)."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        return self._row_to_record(row) if row else None

    def find_by_hash(self, *, user_id: str, project: str, memory_type: str,
                     content_hash: str) -> dict[str, Any] | None:
        """Indexed dedup lookup: the live record with this content_hash in the
        same (user, project, type), or None. O(log n) — no row cap."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memories WHERE user_id=? AND project=? AND type=? "
                "AND content_hash=? AND archived=0 LIMIT 1",
                (user_id, project, memory_type, content_hash),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def find_similar(self, *, user_id: str, project: str, mem_type: str,
                     vec: list[float], threshold: float) -> dict[str, Any] | None:
        """The most semantically-similar live memory in the same (user, project,
        type) whose cosine to `vec` is >= threshold, or None. Catches near-dupes
        that exact content-hash misses (e.g. the LLM re-wording the same lesson)."""
        qunit = _unit(vec)
        if qunit is None:
            return None
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE user_id=? AND project=? AND type=? "
                "AND archived=0 AND embedding_blob IS NOT NULL",
                (user_id, project, mem_type),
            ).fetchall()
        best_row, best = None, float(threshold)
        for row in rows:
            cv = self._row_unit(row)
            if cv is None:
                continue
            sim = _dot(qunit, cv)  # both unit vectors → dot == cosine
            if sim is not None and sim >= best:
                best, best_row = sim, row
        if best_row is None:
            return None
        rec = self._row_to_record(best_row)
        rec["similarity"] = round(best, 4)
        return rec

    def delete_by_id(self, memory_id: str) -> bool:
        """HARD delete one memory (row + FTS). The engine's philosophy is
        archive-never-delete; this and purge() are the explicit escape hatch
        for unrecoverable mistakes (a bad `ygg seed`, leaked content)."""
        with self._lock:
            with self._conn:
                row = self._conn.execute("SELECT seq FROM memories WHERE id=?", (memory_id,)).fetchone()
                if row is None:
                    return False
                if self.use_fts:
                    self._conn.execute("DELETE FROM mem_fts WHERE rowid=?", (row["seq"],))
                self._conn.execute("DELETE FROM memories WHERE seq=?", (row["seq"],))
                self._conn.execute("DELETE FROM relations WHERE from_id=? OR to_id=?",
                                   (memory_id, memory_id))
            self._vec_cache.pop(row["seq"], None)
        return True

    def purge(self, *, user_id: str, namespace: str | None = None, project: str | None = None,
              source: str | None = None, mem_type: str | None = None, dry_run: bool = False) -> int:
        """HARD delete every memory matching the filters (always scoped to
        user_id; namespace/project/source/type narrow it). dry_run only counts.
        Callers (the /purge route, the CLI) enforce that at least one narrowing
        filter — or an explicit all flag — was provided."""
        where = ["user_id=?"]
        params: list[Any] = [user_id]
        for column, value in (("namespace", namespace), ("project", project),
                              ("source", source), ("type", mem_type)):
            if value:
                where.append(f"{column}=?")
                params.append(value)
        where_sql = " AND ".join(where)
        with self._lock:
            rows = self._conn.execute(f"SELECT seq, id FROM memories WHERE {where_sql}", params).fetchall()
            seqs = [r["seq"] for r in rows]
            if dry_run or not seqs:
                return len(seqs)
            ids = [r["id"] for r in rows]
            with self._conn:
                for i in range(0, len(seqs), 500):  # stay under SQLite's variable cap
                    chunk = seqs[i:i + 500]
                    marks = ",".join("?" for _ in chunk)
                    if self.use_fts:
                        self._conn.execute(f"DELETE FROM mem_fts WHERE rowid IN ({marks})", chunk)
                    self._conn.execute(f"DELETE FROM memories WHERE seq IN ({marks})", chunk)
                for i in range(0, len(ids), 250):   # 2 params per id below
                    chunk = ids[i:i + 250]
                    marks = ",".join("?" for _ in chunk)
                    self._conn.execute(
                        f"DELETE FROM relations WHERE from_id IN ({marks}) OR to_id IN ({marks})",
                        chunk + chunk)
            for s in seqs:
                self._vec_cache.pop(s, None)
        return len(seqs)

    # ------------------------------------------------------------------ #
    # relation graph — typed edges: why a memory exists / what replaced it
    # ------------------------------------------------------------------ #

    REL_TYPES = ("SOLVES", "SUPERSEDES", "CONTRADICTS")

    def relate(self, *, from_id: str, to_id: str, rel_type: str,
               user_id: str, source: str | None = None) -> dict[str, Any]:
        """Create one edge. Idempotent (UNIQUE); SUPERSEDES archives the target —
        the edge records WHY it left the active set. Raises ValueError on bad input."""
        rel = (rel_type or "").upper()
        if rel not in self.REL_TYPES:
            raise ValueError(f"unknown rel_type {rel_type!r}: use one of {', '.join(self.REL_TYPES)}")
        if from_id == to_id:
            raise ValueError("a memory cannot relate to itself")
        with self._lock:
            found = {r["id"] for r in self._conn.execute(
                "SELECT id FROM memories WHERE id IN (?, ?)", (from_id, to_id))}
            missing = {from_id, to_id} - found
            if missing:
                raise ValueError(f"memory not found: {', '.join(sorted(missing))}")
            with self._conn:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO relations (from_id, to_id, rel_type, user_id, source, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (from_id, to_id, rel, user_id, source, time.time()))
                created = cur.rowcount > 0
                if rel == "SUPERSEDES":
                    self._conn.execute(
                        "UPDATE memories SET archived=1 WHERE id=? AND archived=0", (to_id,))
        return {"from_id": from_id, "to_id": to_id, "rel_type": rel, "created": created}

    def unrelate(self, *, from_id: str, to_id: str, rel_type: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM relations WHERE from_id=? AND to_id=? AND rel_type=?",
                (from_id, to_id, (rel_type or "").upper()))
        return cur.rowcount > 0

    def relations_for(self, memory_id: str) -> dict[str, list[dict[str, Any]]]:
        """Both directions, each edge carrying the other end's content preview —
        one call answers 'why is this here / what did it replace / what disputes it'."""
        out: dict[str, list[dict[str, Any]]] = {"outgoing": [], "incoming": []}
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT r.from_id, r.to_id, r.rel_type, r.created_at,
                       m.content AS other_content, m.archived AS other_archived
                FROM relations r
                LEFT JOIN memories m
                  ON m.id = CASE WHEN r.from_id=? THEN r.to_id ELSE r.from_id END
                WHERE r.from_id=? OR r.to_id=?
                ORDER BY r.created_at
                """, (memory_id, memory_id, memory_id)).fetchall()
        for r in rows:
            direction = "outgoing" if r["from_id"] == memory_id else "incoming"
            other = r["to_id"] if direction == "outgoing" else r["from_id"]
            out[direction].append({
                "rel_type": r["rel_type"], "other_id": other,
                "other_content": (r["other_content"] or "")[:200],
                "other_archived": bool(r["other_archived"]),
                "created_at": r["created_at"],
            })
        return out

    # ------------------------------------------------------------------ #
    # git-backed sync — stable export + id-preserving upsert. The MERGE
    # policy lives in ygg_sync (pure, unit-tested); the engine only reads
    # and writes exactly what it's told.
    # ------------------------------------------------------------------ #

    SYNC_FIELDS = ("id", "user_id", "namespace", "scope", "project", "type", "content",
                   "content_hash", "source", "confidence", "importance", "created_at",
                   "archived", "metadata_json")

    def sync_export(self) -> dict[str, Any]:
        """Everything another machine needs to reproduce this store: all memories
        (stable fields only — no access counters, no vectors: those are per-machine)
        plus all relation edges. Ordered, so exports are byte-deterministic."""
        with self._lock:
            mems = [dict(r) for r in self._conn.execute(
                f"SELECT {','.join(self.SYNC_FIELDS)} FROM memories ORDER BY id")]
            rels = [dict(r) for r in self._conn.execute(
                "SELECT from_id, to_id, rel_type, user_id, source FROM relations "
                "ORDER BY from_id, to_id, rel_type")]
        return {"memories": mems, "relations": rels}

    def sync_upsert(self, memories: list[dict[str, Any]],
                    relations: list[dict[str, Any]] | None = None) -> dict[str, int]:
        """Write already-merged records under their ORIGINAL ids. New rows are
        inserted (embedding left empty — `ygg reindex` backfills locally);
        changed rows update content/flags + FTS; identical rows are skipped.
        Edges import idempotently; ones pointing at locally-deleted memories are
        skipped, not an error."""
        added = updated = unchanged = rel_added = rel_skipped = 0
        with self._lock:
            with self._conn:
                for rec in memories:
                    mid = rec.get("id")
                    if not mid or not rec.get("content"):
                        continue
                    # A lagging peer may still push demo-keyed records; adopt them
                    # to the default identity on import so machines converge.
                    rec["user_id"], rec["namespace"] = rebrand_legacy_identity(
                        rec.get("user_id"), rec.get("namespace"))
                    row = self._conn.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone()
                    if row is None:
                        cur = self._conn.execute(
                            """
                            INSERT INTO memories
                                (id,user_id,namespace,scope,project,type,content,content_hash,source,confidence,importance,created_at,access_count,archived,metadata_json)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)
                            """,
                            (mid, rec.get("user_id") or "global_user", rec.get("namespace"),
                             rec.get("scope"), rec.get("project"), rec.get("type"),
                             rec["content"], rec.get("content_hash"), rec.get("source"),
                             rec.get("confidence"),
                             rec.get("importance") if rec.get("importance") is not None else 0.5,
                             rec.get("created_at") or time.time(),
                             1 if rec.get("archived") else 0, rec.get("metadata_json")))
                        if self.use_fts:
                            self._conn.execute("INSERT INTO mem_fts(rowid, content) VALUES (?, ?)",
                                               (cur.lastrowid, expand_identifiers(rec["content"])))
                        added += 1
                        continue
                    same = all((dict(row).get(f) == rec.get(f)) for f in self.SYNC_FIELDS)
                    if same:
                        unchanged += 1
                        continue
                    content_changed = row["content"] != rec["content"]
                    self._conn.execute(
                        "UPDATE memories SET scope=?, project=?, type=?, content=?, content_hash=?, "
                        "source=?, confidence=?, importance=?, archived=?, metadata_json=?"
                        + (", embedding_blob=NULL, embed_model=NULL" if content_changed else "")
                        + " WHERE seq=?",
                        (rec.get("scope"), rec.get("project"), rec.get("type"), rec["content"],
                         rec.get("content_hash"), rec.get("source"), rec.get("confidence"),
                         rec.get("importance") if rec.get("importance") is not None else 0.5,
                         1 if rec.get("archived") else 0, rec.get("metadata_json"), row["seq"]))
                    if content_changed:
                        if self.use_fts:
                            self._conn.execute("DELETE FROM mem_fts WHERE rowid=?", (row["seq"],))
                            self._conn.execute("INSERT INTO mem_fts(rowid, content) VALUES (?, ?)",
                                               (row["seq"], expand_identifiers(rec["content"])))
                        self._vec_cache.pop(row["seq"], None)
                    updated += 1
        for rel in relations or []:
            try:
                rel_uid, _ = rebrand_legacy_identity(rel.get("user_id"), _cfg.DEMO_NAMESPACE)
                r = self.relate(from_id=str(rel.get("from_id") or ""),
                                to_id=str(rel.get("to_id") or ""),
                                rel_type=str(rel.get("rel_type") or ""),
                                user_id=str(rel_uid or "global_user"),
                                source=rel.get("source") or "sync")
                rel_added += 1 if r["created"] else 0
            except ValueError:
                rel_skipped += 1
        return {"added": added, "updated": updated, "unchanged": unchanged,
                "relations_added": rel_added, "relations_skipped": rel_skipped}

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def missing_embeddings(self) -> int:
        """Live memories with no current-model embedding — invisible to (or stale
        for) dense recall. Counts rows with no blob, plus rows embedded by a
        different model than this process uses (they need a reindex)."""
        with self._lock:
            if self._embed_model is None:
                return self._conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE embedding_blob IS NULL AND archived=0"
                ).fetchone()[0]
            return self._conn.execute(
                "SELECT COUNT(*) FROM memories WHERE archived=0 AND "
                "(embedding_blob IS NULL OR embed_model IS NOT ?)",
                (self._embed_model,),
            ).fetchone()[0]

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
        if not terms and self.embedder is None:
            return []  # lexical-only with no usable terms — nothing to match

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

        # Cap the lexical candidate set inside SQLite by BM25 rather than pulling
        # EVERY row that matches any OR-term into Python (a query with one common
        # word otherwise Python-scores half the corpus). Generous headroom over
        # the requested limit so the post-hoc boosts (importance/recency/usage/
        # pin) and lexical+vector fusion still have candidates to reorder; vector
        # hits enter separately via vec_rows, so this never hides a semantic match.
        fts_cap = max(limit * 10, 50)
        now = time.time()
        with self._lock:
            if self.use_fts and terms:
                match_query = " OR ".join(f'"{term}"' for term in terms)
                sql = (
                    "SELECT m.*, bm25(mem_fts) AS rank FROM mem_fts "
                    "JOIN memories m ON m.seq = mem_fts.rowid "
                    f"WHERE mem_fts MATCH ? AND {where_sql} "
                    "ORDER BY bm25(mem_fts) LIMIT ?"
                )
                rows = self._conn.execute(sql, [match_query, *params, fts_cap]).fetchall()
            elif self.use_fts:
                rows = []  # no usable lexical terms -> lean on dense (handled below)
            else:
                rows = self._conn.execute(f"SELECT m.* FROM memories m WHERE {where_sql}", params).fetchall()
            vec_rows = []
            if self.embedder is not None:
                vec_rows = self._conn.execute(
                    f"SELECT m.* FROM memories m WHERE {where_sql} AND m.embedding_blob IS NOT NULL", params
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

        # Dense ranking: cosine of the query vs the cached unit vectors over the
        # scoped set — no per-row JSON parse; cosine is a dot of two unit vectors.
        query_vec = self._embed_raw(query)
        qunit = _unit(query_vec) if query_vec else None
        vec_scored: list[dict[str, Any]] = []
        if qunit is not None:
            for row in vec_rows:
                cv = self._row_unit(row)
                if cv is None:
                    continue
                sim = _dot(qunit, cv)
                if sim is None or sim <= 0:
                    continue
                record = records.get(row["id"])
                if record is None:
                    record = self._row_to_record(row)
                    # Vector-only hit: still honor the user's explicit signals
                    # (pin, usage) via the same lexical channel — parity with
                    # lexical hits, which already bake these in.
                    record["lexical_score"] = self._user_signal(record)
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
        # Never come back empty when there's a semantic store to draw from: fall
        # back to the nearest memories by cosine (helps one-word / paraphrase /
        # cross-lingual queries where nothing cleared the cutoff above). Marked so
        # callers can tell these are "closest", not strong matches.
        if not result and qunit is not None and vec_rows:
            near: list[tuple[float, Any]] = []
            for row in vec_rows:
                cv = self._row_unit(row)
                if cv is None:
                    continue
                sim = _dot(qunit, cv)
                if sim is not None:
                    near.append((sim, row))
            near.sort(key=lambda t: t[0], reverse=True)
            for sim, row in near[:limit]:
                rec = self._row_to_record(row)
                rec["score"] = round(sim, 6)
                rec["nearest"] = True
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
            with self._conn:
                self._conn.executemany(
                    "UPDATE memories SET access_count = access_count + 1, last_accessed_at = ? WHERE id = ?",
                    [(now, i) for i in ids],
                )

    def reindex_embeddings(self) -> int:
        """Embed rows that have no current-model vector — self-heals after a
        cold-start timeout, when dense is enabled after content already exists,
        OR when the embedding model changed (rows tagged with a different model,
        including '(legacy)' JSON migrations, are re-embedded)."""
        if self.embedder is None:
            return 0
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, content FROM memories WHERE embedding_blob IS NULL OR embed_model IS NOT ?",
                (self._embed_model,),
            ).fetchall()
        healed = 0
        batch = getattr(self.embedder, "embed_batch", None)
        CHUNK = 32
        for i in range(0, len(rows), CHUNK):
            chunk = rows[i:i + CHUNK]
            texts = [r["content"] for r in chunk]
            vecs = batch(texts) if batch is not None else None
            if vecs is None:  # no batch API (or it failed) -> per-item fallback
                vecs = [self._embed_raw(t) for t in texts]
            for row, vec in zip(chunk, vecs):
                if vec:
                    with self._lock:
                        with self._conn:
                            self._store_embedding_locked(row["seq"], vec)
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
        if not self.token:
            return False  # never run open: no token means nothing authenticates
        header = self.headers.get("Authorization", "")
        # Constant-time compare — a plain == leaks the token byte-by-byte to a
        # local timing attacker.
        return hmac.compare_digest(header, f"Bearer {self.token}")

    def _host_ok(self) -> bool:
        """Reject DNS-rebinding: when bound to loopback, only loopback Host
        headers are legitimate — a browser lured to attacker.com resolving to
        127.0.0.1 sends `Host: attacker.com`. Deliberate non-loopback binds
        (YGG_MEMORY_HOST) are the operator's exposure choice and pass through."""
        bind = self.server.server_address[0]
        if bind not in ("127.0.0.1", "::1", "localhost"):
            return True
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ("127.0.0.1", "localhost", "::1", "")

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

    def _guarded(self, handler) -> None:
        """Malformed client input must yield a JSON 400, not a traceback and a
        dropped connection (which also used to leave a transaction open)."""
        try:
            handler()
        except (ValueError, TypeError, KeyError) as exc:
            self._send(400, {"success": False, "error": f"bad request: {exc}"})
        except Exception as exc:  # noqa: BLE001 — last-resort JSON 500
            self._send(500, {"success": False, "error": f"internal error: {exc}"})

    def do_GET(self) -> None:
        self._guarded(self._route_get)

    def do_POST(self) -> None:
        self._guarded(self._route_post)

    def do_PUT(self) -> None:
        self._guarded(self._route_put)

    def _route_get(self) -> None:
        if not self._host_ok():
            self._send(403, {"success": False, "error": "forbidden host header"})
            return
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            embedder = self.store.embedder
            embed_model = getattr(embedder, "model", None) if embedder is not None else None
            count = self.store.count()
            body = {
                "status": "ok",
                "memory_count": count,
                "graph_nodes": 0,
                "storage": "sqlite-fts5" if self.store.use_fts else "sqlite-fallback",
                "dense": (f"active ({embed_model})" if embedder is not None
                          else "inactive (no embedding model — lexical only)"),
                "reranker": "disabled (not configured)",
                # kept for backward compatibility with older clients:
                "backend": "ygg-sqlite-fts5" if self.store.use_fts else "ygg-sqlite-fallback",
            }
            # Dense is on but some rows never got embedded -> they can't be found
            # semantically until reindexed. Surfaced so `ygg doctor` can flag it.
            if embedder is not None:
                missing = self.store.missing_embeddings()
                if missing:
                    body["embeddings_missing"] = missing
            # Built-in vector search is an in-Python cosine — past this size, a
            # dedicated vector backend keeps recall fast. (Only when dense is on.)
            if embedder is not None and count >= VECTOR_WARN_AT:
                body["scale_hint"] = (
                    f"{count:,} memories with the built-in in-Python vector search — "
                    "recall will get slow. Point YGG_ENGINE_URL at a dedicated vector "
                    "backend (e.g. Qdrant) via the MemoryBackend contract; see "
                    "docs/backend-boundary.md."
                )
            self._send(200, body)
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
        if parsed.path == "/get":
            qs = parse_qs(parsed.query)
            memory_id = (qs.get("id") or [""])[0]
            if not memory_id:
                self._send(400, {"success": False, "error": "id is required"})
                return
            rec = self.store.get_by_id(memory_id)
            if rec is None:
                self._send(404, {"success": False, "error": f"memory not found: {memory_id}"})
                return
            self._send(200, {"success": True, "data": rec})
            return
        if parsed.path == "/quality":
            qs = parse_qs(parsed.query)
            data = self.store.quality_report(
                user_id=(qs.get("user_id") or ["global_user"])[0],
                namespace=(qs.get("namespace") or [None])[0],
                near_dup_threshold=float((qs.get("threshold") or ["0.95"])[0]),
            )
            self._send(200, {"success": True, "data": data})
            return
        if parsed.path == "/find_hash":
            qs = parse_qs(parsed.query)
            rec = self.store.find_by_hash(
                user_id=(qs.get("user_id") or ["global_user"])[0],
                project=(qs.get("project") or [""])[0],
                memory_type=(qs.get("type") or [""])[0],
                content_hash=(qs.get("hash") or [""])[0],
            )
            self._send(200, {"success": True, "data": rec})
            return
        self._send(404, {"success": False, "error": f"not found: {parsed.path}"})

    def _route_post(self) -> None:
        if not self._host_ok():
            self._send(403, {"success": False, "error": "forbidden host header"})
            return
        if not self._authorized():
            self._send(401, {"success": False, "error": "unauthorized"})
            return
        parsed = urlparse(self.path)
        body = self._read_json()
        if parsed.path == "/reindex":
            healed = self.store.reindex_embeddings()
            self._send(200, {"success": True, "data": {"healed": healed}})
            return
        if parsed.path == "/add":
            content = body.get("content")
            if not content:
                self._send(400, {"success": False, "error": "content is required"})
                return
            metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
            # Engine-level secret guard: refuse an obvious credential on ANY /add,
            # even one bypassing the CLI (the CLI's broader heuristic runs first).
            hit = looks_like_secret(str(content)) or looks_like_secret(json.dumps(metadata))
            if hit:
                self._send(400, {"success": False, "error": f"refusing to store an apparent secret: {hit}"})
                return
            record = self.store.add(
                content=str(content),
                user_id=str(body.get("user_id") or "global_user"),
                namespace=body.get("namespace"),
                scope=body.get("scope") or metadata.get("scope"),
                metadata=metadata,
                dedupe_threshold=body.get("dedupe_threshold"),
            )
            self._send(200, {"success": True, "data": record})
            return
        if parsed.path == "/delete":
            memory_id = body.get("memory_id")
            if not memory_id:
                self._send(400, {"success": False, "error": "memory_id is required"})
                return
            if not self.store.delete_by_id(str(memory_id)):
                self._send(404, {"success": False, "error": f"memory not found: {memory_id}"})
                return
            self._send(200, {"success": True, "data": {"deleted": 1}})
            return
        if parsed.path == "/purge":
            narrowing = {k: body.get(k) for k in ("namespace", "project", "source", "type") if body.get(k)}
            if not narrowing and not body.get("all"):
                self._send(400, {"success": False, "error":
                                 "refusing to purge without a narrowing filter "
                                 "(namespace/project/source/type) — pass all=true to override"})
                return
            deleted = self.store.purge(
                user_id=str(body.get("user_id") or "global_user"),
                namespace=narrowing.get("namespace"),
                project=narrowing.get("project"),
                source=narrowing.get("source"),
                mem_type=narrowing.get("type"),
                dry_run=bool(body.get("dry_run")),
            )
            self._send(200, {"success": True, "data": {"deleted": deleted, "dry_run": bool(body.get("dry_run"))}})
            return
        if parsed.path == "/relate":
            try:
                data = self.store.relate(
                    from_id=str(body.get("from_id") or ""),
                    to_id=str(body.get("to_id") or ""),
                    rel_type=str(body.get("rel_type") or ""),
                    user_id=str(body.get("user_id") or "global_user"),
                    source=body.get("source"),
                )
            except ValueError as exc:
                self._send(400, {"success": False, "error": str(exc)})
                return
            self._send(200, {"success": True, "data": data})
            return
        if parsed.path == "/unrelate":
            removed = self.store.unrelate(
                from_id=str(body.get("from_id") or ""),
                to_id=str(body.get("to_id") or ""),
                rel_type=str(body.get("rel_type") or ""))
            self._send(200, {"success": True, "data": {"removed": removed}})
            return
        if parsed.path == "/relations":
            memory_id = body.get("memory_id")
            if not memory_id:
                self._send(400, {"success": False, "error": "memory_id is required"})
                return
            self._send(200, {"success": True, "data": self.store.relations_for(str(memory_id))})
            return
        if parsed.path == "/sync_export":
            self._send(200, {"success": True, "data": self.store.sync_export()})
            return
        if parsed.path == "/sync_upsert":
            mems = body.get("memories") if isinstance(body.get("memories"), list) else []
            rels = body.get("relations") if isinstance(body.get("relations"), list) else []
            self._send(200, {"success": True, "data": self.store.sync_upsert(mems, rels)})
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

    def _route_put(self) -> None:
        if not self._host_ok():
            self._send(403, {"success": False, "error": "forbidden host header"})
            return
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
    parser.add_argument("--token-file", default=os.environ.get("YGG_TOKEN_FILE"),
                        help="Read the auth token from this file — keeps the secret out of `ps` and the plist.")
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
    store = MemoryStore(args.db, embedder=embedder)
    Handler.store = store
    tok = args.token
    if args.token_file:  # a value from the 0600 file beats the visible CLI default
        try:
            with open(args.token_file) as fh:
                file_tok = fh.read().strip()
            if file_tok:
                tok = file_tok
        except OSError:
            pass
    if not tok:
        # Nothing configured anywhere: reuse (or create) the standard install
        # token file instead of a publicly-known demo constant. Clients
        # (ygg_core, hooks, doctor) auto-read the same file, so a bare
        # `ygg serve` stays plug-and-play — without being open to every local process.
        home = os.environ.get("YGG_HOME") or os.path.join(os.path.expanduser("~"), ".yggdrasil")
        token_path = os.path.join(home, "token")
        try:
            with open(token_path, encoding="utf-8") as fh:
                tok = fh.read().strip()
        except OSError:
            tok = ""
        if not tok:
            import secrets
            tok = secrets.token_hex(24)
            try:
                os.makedirs(home, exist_ok=True)
                with open(token_path, "w", encoding="utf-8") as fh:
                    fh.write(tok)
                os.chmod(token_path, 0o600)
                print(f"ygg-memory: no token configured — generated one -> {token_path}", flush=True)
            except OSError:
                print("ygg-memory: no token configured — using an ephemeral random token "
                      f"(could not write {token_path})", flush=True)
    Handler.token = tok

    try:
        httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        # Almost always "address already in use" — the daemon is likely already
        # running, or another process holds the port. Give an actionable hint
        # instead of a bare traceback.
        print(
            f"ygg-memory: cannot bind {args.host}:{args.port} ({exc}).\n"
            f"  • already running? check:  ygg status   (or curl http://{args.host}:{args.port}/health)\n"
            f"  • port taken by something else? pick another:  YGG_MEMORY_PORT=42169 ygg serve …  "
            f"(and set YGG_PORT to match)",
            file=sys.stderr, flush=True,
        )
        return 1
    print(
        f"ygg-memory: listening on http://{args.host}:{args.port}  db={args.db}  "
        f"fts5={'on' if store.use_fts else 'off (python fallback)'}  "
        f"dense={args.embed_model or 'off'}",
        flush=True,
    )

    # Periodically refresh the 'newer version available' cache (the CLI/MCP just
    # read it, so they never block on the network). Best-effort, daemon thread.
    try:
        from . import ygg_update_check as _upd
    except ImportError:  # flat-deployed scripts dir
        import ygg_update_check as _upd  # type: ignore

    def _update_loop() -> None:
        while True:
            _upd.refresh_cache()
            time.sleep(_upd.TTL)
    threading.Thread(target=_update_loop, daemon=True).start()

    # Warm the model + backfill embeddings AFTER binding, off the request path.
    # Doing it before bind delayed listening (a long reindex could let
    # service.ensure_running lazy-spawn a SECOND daemon racing for the port).
    if embedder is not None:
        def _warm_and_reindex() -> None:
            embedder.embed("warmup")  # load the model so the first real embed doesn't time out
            healed = store.reindex_embeddings()
            if healed:
                print(f"ygg-memory: backfilled {healed} embeddings", flush=True)
        threading.Thread(target=_warm_and_reindex, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
