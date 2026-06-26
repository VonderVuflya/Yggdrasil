"""Core Yggdrasil primitives shared by CLI, review, and gate tools."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol, runtime_checkable


DEFAULT_ENGINE_URL = "http://127.0.0.1:42069"
DEFAULT_DEMO_TOKEN = "yggdrasil-demo-token"


def _read_token_file() -> str | None:
    """Read the engine token written by ``ygg install`` (``~/.yggdrasil/token``).

    Lets CLI memory commands authenticate out of the box without the user having
    to export ``YGG_ENGINE_TOKEN`` by hand — the same file ``ygg doctor`` and the
    session hook already read. Honors ``YGG_HOME`` like the rest of the CLI.
    """
    home = os.environ.get("YGG_HOME")
    base = home if home else os.path.join(os.path.expanduser("~"), ".yggdrasil")
    try:
        with open(os.path.join(base, "token"), "r", encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


class YggError(RuntimeError):
    """Base Yggdrasil workflow error."""


class BackendCapabilityError(YggError):
    """Raised when the configured backend does not support a required operation."""


@dataclass(frozen=True)
class YggConfig:
    """Runtime configuration for a Yggdrasil memory backend."""

    url: str = DEFAULT_ENGINE_URL
    token: str = DEFAULT_DEMO_TOKEN
    namespace: str = "yggdrasil-demo"
    user_id: str = "global_user"

    @classmethod
    def from_env(cls) -> "YggConfig":
        token = (
            os.environ.get("YGG_ENGINE_TOKEN")
            or os.environ.get("YGG_TOKEN")
            or _read_token_file()
            or DEFAULT_DEMO_TOKEN
        )
        return cls(
            url=(os.environ.get("YGG_ENGINE_URL") or DEFAULT_ENGINE_URL).rstrip("/"),
            token=token,
            namespace=os.environ.get("YGG_NAMESPACE") or "yggdrasil-demo",
            user_id=os.environ.get("YGG_USER_ID") or "global_user",
        )


@runtime_checkable
class MemoryBackend(Protocol):
    """The memory backend contract Yggdrasil depends on.

    This is the entire surface area that the CLI, MCP facade, review queue and
    gates require. Any engine that satisfies it is a drop-in backend. The
    DEFAULT engine is Yggdrasil's own ``ygg_memory_server.py`` (stdlib SQLite +
    FTS5, zero heavy dependencies). Any external engine that satisfies this
    contract is a drop-in: point ``YGG_ENGINE_URL`` at it. Both are reached
    through the same REST client below, so nothing in the workflow layer is
    engine-specific.
    """

    def health(self) -> dict[str, Any]: ...
    def add(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def search(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_all(self, *, user_id: str | None = ..., limit: int = ..., namespace: str | None = ...) -> list[dict[str, Any]]: ...
    def update_memory(self, memory_id: str, *, data: str | None = ..., metadata_patch: dict[str, Any] | None = ..., archived: bool | None = ...) -> dict[str, Any]: ...
    def archive_memory(self, memory_id: str, metadata_patch: dict[str, Any]) -> dict[str, Any]: ...


class RestMemoryBackend:
    """Engine-agnostic REST client for any backend speaking the memory contract.

    This talks to ANY compatible REST engine. By default that is Yggdrasil's own
    ``ygg_memory_server.py``; setting ``YGG_ENGINE_URL`` lets you point it at an
    external engine instead. It reports missing backend capabilities at the
    boundary (e.g. an engine without the metadata-update contract raises
    :class:`BackendCapabilityError`).
    """

    def __init__(self, config: YggConfig | None = None, timeout: int = 30):
        self.config = config or YggConfig.from_env()
        self.timeout = timeout

    def request_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        url = self.config.url + path
        if query:
            url += "?" + urllib.parse.urlencode({key: value for key, value in query.items() if value is not None})
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.config.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 401:
                detail += (
                    "\nHint: the engine rejected the auth token. The CLI auto-reads "
                    "~/.yggdrasil/token; if that's stale, run `ygg install`, or set "
                    "YGG_ENGINE_TOKEN=$(ygg token)."
                )
            raise YggError(f"{method} {path} failed: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise YggError(f"{method} {path} failed: {exc.reason}") from exc

    def health(self) -> dict[str, Any]:
        return self.request_json("GET", "/health", timeout=10)

    def add(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request_json("POST", "/add", body=payload, timeout=60)

    def search(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request_json("POST", "/search", body=payload, timeout=60)

    def get_all(self, *, user_id: str | None = None, limit: int = 1000, namespace: str | None = None) -> list[dict[str, Any]]:
        return self.request_json(
            "GET",
            "/get_all",
            query={"user_id": user_id or self.config.user_id, "limit": limit, "namespace": namespace},
        ).get("data", [])

    def update_memory(
        self,
        memory_id: str,
        *,
        data: str | None = None,
        metadata_patch: dict[str, Any] | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"memory_id": memory_id}
        if data is not None:
            payload["data"] = data
        if metadata_patch is not None:
            payload["metadata_patch"] = metadata_patch
        if archived is not None:
            payload["archived"] = archived
        try:
            return self.request_json("PUT", "/update", body=payload)
        except YggError as exc:
            if metadata_patch is not None or archived is not None:
                raise BackendCapabilityError(
                    "The configured backend does not expose Yggdrasil's required metadata update contract. "
                    "Required: PUT /update accepting metadata_patch and archived."
                ) from exc
            raise

    def archive_memory(self, memory_id: str, metadata_patch: dict[str, Any]) -> dict[str, Any]:
        return self.update_memory(memory_id, metadata_patch=metadata_patch, archived=True)


def metadata_of(record: dict[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def record_is_archived(record: dict[str, Any]) -> bool:
    metadata = metadata_of(record)
    return bool(record.get("archived")) or str(metadata.get("status") or "").lower() == "archived"
