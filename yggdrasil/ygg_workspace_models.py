"""Read installed model catalogs without starting runtimes or downloading models."""
from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

try:
    from . import ygg_config as config
    from .ygg_providers import classify, _human
except ImportError:  # deployed flat scripts
    import ygg_config as config
    from ygg_providers import classify, _human


REQUEST_TIMEOUT = 2.0
RESPONSE_LIMIT = 1_048_576
MODEL_LIMIT = 1000


class _ProbeError(Exception):
    def __init__(self, message: str, fallback: bool = False):
        super().__init__(message)
        self.fallback = fallback


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _base(value: str, provider: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 2048 or
            any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value) or "\\" in value):
        raise ValueError("Enter a valid HTTP(S) model API URL.")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or
                parsed.username is not None or parsed.password is not None or
                parsed.query or parsed.fragment):
            raise ValueError
        port = parsed.port
        host = parsed.hostname.lower()
        host.encode("ascii")
        if ":" in host:
            host = f"[{host}]"
        if port is not None and port != (443 if parsed.scheme == "https" else 80):
            host += f":{port}"
    except (ValueError, UnicodeError):
        raise ValueError("Enter a valid HTTP(S) model API URL without credentials, query or fragment.") from None
    path = parsed.path.rstrip("/")
    if provider == "openai" and path.endswith("/v1"):
        path = path[:-3].rstrip("/")
    return urlunsplit((parsed.scheme, host, path, "", ""))


def _valid_key(value: str) -> str:
    if (not isinstance(value, str) or len(value) > 4096 or
            any(ord(c) < 32 or ord(c) > 126 for c in value)):
        raise ValueError("Invalid API key.")
    return value.strip()


def _key(body: dict, chat_service, base: str, provider: str, purpose: str) -> str:
    if "api_key" in body:
        return _valid_key(body["api_key"])
    if purpose == "chat":
        # save_settings writes endpoint and key together under this same lock.
        with chat_service._lock:
            saved = chat_service.settings()
            if saved.get("provider") != provider:
                return ""
            try:
                if _base(saved.get("url", ""), provider) == base:
                    return _valid_key(chat_service._key())
            except ValueError:
                pass
        return ""
    if purpose == "embed" and config.resolve("embed_backend") != provider:
        return ""
    prefix = "embed" if purpose == "embed" else "distill"
    saved_url = config.resolve(prefix + "_url")
    try:
        if _base(saved_url, provider) == base:
            return _valid_key(config.resolve(prefix + "_api_key"))
    except ValueError:
        # A malformed saved endpoint/key cannot authorize a discovery request.
        pass
    return ""


def _catalog(url: str, key: str, field: str) -> list:
    headers = {"Accept": "application/json", "User-Agent": "yggdrasil-workspace"}
    if key:
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(url, headers=headers)
    deadline = time.monotonic() + REQUEST_TIMEOUT
    try:
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(request, timeout=REQUEST_TIMEOUT) as response:
            length = response.headers.get("Content-Length")
            if length is not None and int(length) > RESPONSE_LIMIT:
                raise _ProbeError("The model catalog is too large.")
            raw = bytearray()
            while True:
                if time.monotonic() >= deadline:
                    raise _ProbeError("The model server did not respond in time.")
                part = response.read1(min(65536, RESPONSE_LIMIT + 1 - len(raw)))
                if not part:
                    break
                raw.extend(part)
                if len(raw) > RESPONSE_LIMIT:
                    raise _ProbeError("The model catalog is too large.")
            data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get(field), list):
            raise _ProbeError("The model server returned an invalid catalog.", fallback=True)
        if len(data[field]) > MODEL_LIMIT:
            raise _ProbeError("The model catalog is too large.")
        return data[field]
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        if status in (401, 403):
            raise _ProbeError("The model server rejected the API key.") from None
        if 300 <= status < 400:
            raise _ProbeError("The model server redirected the request. Check the API URL.") from None
        raise _ProbeError("The model server is unavailable or does not support model discovery.",
                          fallback=status in (404, 405, 501)) from None
    except TimeoutError:
        raise _ProbeError("The model server did not respond in time.") from None
    except (OSError, http.client.HTTPException):
        raise _ProbeError("The model server is unavailable. Check that it is running and the API URL is correct.") from None
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise _ProbeError("The model server returned an invalid catalog.", fallback=True) from None


def _text(value, limit: int = 1000) -> str:
    if not isinstance(value, str) or len(value) > limit:
        return ""
    return value.strip() if all(ord(c) >= 32 and ord(c) != 127 for c in value) else ""


def _models(entries: list, provider: str, purpose: str) -> list[dict]:
    result = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        mid = _text(entry.get("name") or entry.get("model")) if provider == "ollama" else _text(entry.get("id"))
        if not mid or mid in seen:
            continue
        model_type = _text(entry.get("type")).lower()
        details = entry.get("details")
        family = _text(details.get("family")) if isinstance(details, dict) else ""
        if model_type.startswith("embed"):
            kind = "embed"
        elif model_type in ("llm", "vlm"):
            kind = "llm"
        elif family:
            kind = classify(mid, family)
        else:
            kind = "embed" if classify(mid) == "embed" else "unknown"
        if (purpose == "embed" and kind == "llm") or (purpose != "embed" and kind == "embed"):
            continue
        item = {"id": mid, "kind": kind}
        size = entry.get("size")
        if isinstance(size, (int, float)) and not isinstance(size, bool) and 0 <= size <= 2 ** 63 - 1:
            item["size"] = _human(size)
        note = _text(entry.get("quantization"), 200)
        if kind == "unknown":
            note = "Model type not reported by server."
        if note:
            item["note"] = note
        seen.add(mid)
        result.append(item)
    return result


def discover_models(body: dict, chat_service) -> dict:
    """Probe one explicitly requested endpoint; saved credentials stay endpoint-scoped.

    Invalid browser input raises ValueError. Network and catalog failures return a
    safe unavailable result; an empty valid catalog is reachable with no models.
    """
    if not isinstance(body, dict):
        raise ValueError("Invalid model discovery request.")
    provider = body.get("provider")
    purpose = body.get("purpose", "chat")
    if provider not in ("ollama", "openai"):
        raise ValueError("Choose Ollama or an OpenAI-compatible API.")
    if purpose not in ("chat", "bg", "embed"):
        raise ValueError("Invalid model purpose.")
    base = _base(body.get("url"), provider)
    key = _key(body, chat_service, base, provider, purpose)
    try:
        if provider == "ollama":
            entries = _catalog(base + "/api/tags", key, "models")
        else:
            try:
                entries = _catalog(base + "/api/v0/models", key, "data")
            except _ProbeError as exc:
                if not exc.fallback:
                    raise
                entries = _catalog(base + "/v1/models", key, "data")
        return {"models": _models(entries, provider, purpose), "reachable": True}
    except _ProbeError as exc:
        return {"models": [], "reachable": False, "error": str(exc)}
