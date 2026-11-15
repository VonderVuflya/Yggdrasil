"""Read-only network, model API and inventory checks before distillation."""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

PROBE_TIMEOUT = 3.0


class PreflightError(ValueError):
    def __init__(self, stage: str, url: str, detail: str):
        self.stage = stage
        super().__init__(f"[{stage}] {url}: {detail}")


@dataclass(frozen=True)
class ModelInventory:
    url: str
    backend: str
    models: tuple[str, ...]
    purpose: str = "all"
    kinds: tuple[str, ...] = ()


def endpoint_root(url: str) -> str:
    root = url.rstrip('/')
    if root.endswith('/embeddings'):
        root = root[:-11]
    return root[:-3] if root.endswith('/v1') else root


def normalise_backend(backend: str) -> str:
    backend = backend.strip().lower()
    if backend in ("openai-compatible", "llamacpp", "llama.cpp", "openrouter"):
        return "openai"
    return backend


def check_connection(url: str) -> None:
    """Check DNS then TCP; a timeout cannot distinguish host loss from filtering."""
    try:
        address = urllib.parse.urlsplit(url)
        if address.scheme not in ('http', 'https') or not address.hostname:
            raise ValueError('expected an http(s) URL with a hostname')
        port = address.port or (443 if address.scheme == 'https' else 80)
        proxy = urllib.request.getproxies().get(address.scheme)
        via_proxy = bool(proxy and not urllib.request.proxy_bypass(address.netloc))
        if via_proxy:
            address = urllib.parse.urlsplit(proxy if "://" in proxy else "http://" + proxy)
            if not address.hostname:
                raise ValueError("invalid proxy address")
            port = address.port or (443 if address.scheme == "https" else 80)
    except ValueError as exc:
        raise PreflightError('configuration', url, str(exc)) from exc
    try:
        addresses = socket.getaddrinfo(address.hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise PreflightError('DNS', url, 'cannot resolve hostname; check the address and DNS') from exc
    print(f"  ✓ {'Proxy DNS' if via_proxy else 'DNS'}: {address.hostname}")
    deadline = time.monotonic() + PROBE_TIMEOUT
    failure: OSError = TimeoutError()
    for family, kind, proto, _, target in addresses:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            with socket.socket(family, kind, proto) as sock:
                sock.settimeout(remaining)
                sock.connect(target)
            print(f"  ✓ {'Proxy TCP' if via_proxy else 'TCP'}: {address.hostname}:{port}")
            return
        except OSError as exc:
            failure = exc
    if isinstance(failure, ConnectionRefusedError):
        detail = ('connection refused: the address responds but the port does not accept connections; '
                  'start LM Studio/Ollama and check its listening address, port and firewall')
    elif isinstance(failure, TimeoutError):
        detail = ('no response from host/port; the PC may be unreachable or a firewall may block '
                  'the connection; check the network, server listening address and firewall')
    else:
        detail = 'network connection failed; check the route, server address and firewall'
    if via_proxy:
        detail = f'proxy transport {address.hostname}:{port}: {detail}'
    raise PreflightError('connection', url, detail) from failure


def probe_endpoint(url: str, *, api_key: str = '', backend: str = 'auto',
                   purpose: str = 'generation') -> ModelInventory:
    """List models without loading them, generating tokens or sending user text."""
    provider = backend.strip().lower()
    backend = normalise_backend(backend)
    if backend not in ('auto', 'ollama', 'openai'):
        raise PreflightError('configuration', url, f'unsupported embedding backend: {backend}')
    check_connection(url)
    root = endpoint_root(url)
    host = urllib.parse.urlsplit(url).hostname or ''
    openrouter = provider == 'openrouter' or host == 'openrouter.ai' or host.endswith('.openrouter.ai')
    # Prefer native Ollama so tag semantics are known even on a custom port.
    routes = [('ollama', root + '/api/tags'), ('openai', root + '/v1/models')]
    if backend == 'ollama':
        routes = routes[:1]
    elif backend == 'openai':
        base = url.rstrip('/')
        if base.endswith('/embeddings'):
            base = base[:-11]
        routes = [('openai', base + '/models')]
        if not base.endswith('/v1'):
            routes.append(('openai', base + '/v1/models'))
    if openrouter:
        route = '/v1/embeddings/models' if purpose == 'embedding' else '/v1/models'
        routes = [('openai', root + route)]
    headers = {'Accept': 'application/json', 'User-Agent': 'yggdrasil-preflight'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    for kind, route in routes:
        req = urllib.request.Request(route, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            hint = ('check the API key and server access settings' if exc.code in (401, 403)
                    else 'check the model server logs')
            raise PreflightError('API', url, f'HTTP {exc.code}; {hint}') from exc
        except (OSError, ValueError) as exc:
            raise PreflightError('API', url, 'no valid JSON response; check server availability, '
                                 'TLS, connectivity and the API address') from exc
        if isinstance(data, dict) and data.get('error'):
            if 'unexpected endpoint or method' in str(data['error']).lower():
                continue  # LM Studio can report unsupported routes with HTTP 200.
            raise PreflightError('API', url, 'server returned an API error; '
                                 'check credentials and the model server logs')
        field, id_field = ('models', 'name') if kind == 'ollama' else ('data', 'id')
        rows = data.get(field) if isinstance(data, dict) else None
        if (not isinstance(rows, list) or
                any(not isinstance(row, dict) or not isinstance(row.get(id_field), str)
                    or not row[id_field] for row in rows)):
            raise PreflightError('API', url, 'unexpected model list; this is not a supported '
                                 'LM Studio/Ollama model API')
        try:
            from .ygg_providers import classify
        except ImportError:  # flat deploy
            from ygg_providers import classify
        kinds = []
        for row in rows:
            category = str(row.get("type") or "").lower()
            details = row.get("details") or {}
            family = details.get("family", "") if isinstance(details, dict) else ""
            if openrouter:
                category = "embedding" if purpose == "embedding" else "llm"
            kinds.append("embed" if category.startswith("embed") else
                         "llm" if category in ("llm", "vlm") else
                         "embed" if (classify(row[id_field]) == "embed" or
                                     classify("", str(family)) == "embed") else "llm")
        inventory = ModelInventory(root, kind, tuple(row[id_field] for row in rows),
                                   purpose if openrouter else 'all', tuple(kinds))
        print(f"  ✓ API ({kind}): {root}")
        return inventory
    raise PreflightError('API', url, 'no supported model-list API; check the server address '
                         'and enable the LM Studio/Ollama API')


def require_model(inventory: ModelInventory, model: str, setting: str) -> None:
    candidates = {model}
    if inventory.backend == 'ollama':
        if ':' not in model.rsplit('/', 1)[-1]:
            candidates.add(model + ':latest')
        elif model.endswith(':latest'):
            candidates.add(model[:-7])
    if not model or not candidates.intersection(inventory.models):
        available = ', '.join(inventory.models) or '(none)'
        raise PreflightError('model', inventory.url,
                             f'{setting}: {model!r} is unavailable. Available IDs: {available}. '
                             'Download/load that model on the server or correct the model setting.')
    print(f"  ✓ {setting}: {model}")
