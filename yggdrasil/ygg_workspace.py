"""Loopback Workspace HTTP server. Browser credentials never expose engine keys."""
from __future__ import annotations

import hmac
import json
import mimetypes
import os
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import ygg_config as config


class EngineQuery:
    def __init__(self, url, token, user_id, namespace):
        self.url = url.rstrip('/')
        self.token = token
        self.user_id = user_id
        self.namespace = namespace

    def __call__(self, body):
        payload = {**body, 'user_id': self.user_id, 'namespace': self.namespace}
        request = urllib.request.Request(self.url + '/workspace/query',
            json.dumps(payload).encode(), {'Authorization': f'Bearer {self.token}',
                                         'Content-Type': 'application/json'})
        try:
            # Never forward credentials through HTTP redirects.
            with urllib.request.build_opener(_NoRedirect()).open(request, timeout=30) as response:
                result = json.load(response)
                if not isinstance(result, dict) or not isinstance(result.get('data'), dict):
                    raise RuntimeError('Некорректный ответ движка')
                return result['data']
        except urllib.error.HTTPError as exc:
            exc.close()
            if exc.code == 404:
                # The engine can report an absent memory or an old API version.
                if body.get('op') == 'memory':
                    raise KeyError('Запись не найдена') from None
                raise RuntimeError('Движок не поддерживает Workspace. Выполните ygg redeploy.') from None
            if exc.code == 400:
                raise ValueError('Некорректные параметры запроса') from None
            raise RuntimeError('Движок отклонил запрос. Проверьте ygg doctor и токен подключения.') from None
        except (OSError, ValueError) as exc:
            if isinstance(exc, ValueError):
                raise RuntimeError('Некорректный ответ движка') from None
            raise RuntimeError('Нет связи с движком. Проверьте ygg doctor.') from None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WorkspaceServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, *, home, query, control, static=None, user_id=None, namespace=None):
        if address[0] != '127.0.0.1':
            raise ValueError('Workspace доступен только через 127.0.0.1')
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.static = Path(static or Path(__file__).parent / 'workspace_static').resolve()
        self.query = query
        self.control = control
        self.user_id = user_id or config.user_id()
        self.namespace = namespace or config.namespace()
        self.tickets = {}
        self.sessions = {}
        self.auth_lock = threading.Lock()
        self.chat_lock = threading.Lock()
        self._chat = None
        self._management = None
        self._release = None
        self.completed_update = None
        self.restart_requested = False
        super().__init__(address, WorkspaceHandler)
        # Cookies are host-scoped, not port-scoped. Independent Workspaces on
        # different ports must not replace one another's login.
        self.cookie_name = f'ygg_workspace_{self.server_port}'

    @property
    def chat(self):
        with self.chat_lock:
            if self._chat is None:
                from .ygg_workspace_chat import ChatService
                self._chat = ChatService(self.home, self.query, self.user_id, self.namespace)
            return self._chat

    def issue_ticket(self):
        with self.auth_lock:
            now = time.monotonic()
            self.tickets = {k: v for k, v in self.tickets.items() if v > now}
            if len(self.tickets) >= 64:
                self.tickets.pop(next(iter(self.tickets)))
            ticket = secrets.token_urlsafe(32)
            self.tickets[ticket] = now + 60
            return ticket

    @property
    def management(self):
        with self.chat_lock:
            if self._management is None:
                from .ygg_workspace_management import Management
                self._management = Management(self.home)
            return self._management

    @property
    def release(self):
        manager = self.management
        with self.chat_lock:
            if self._release is None:
                from .ygg_workspace_release import ReleaseService
                self._release = ReleaseService(self.home, manager, self.completed_update)
            return self._release

    def server_close(self):
        if self._management is not None:
            self._management.close()
        super().server_close()
        with self.chat_lock:
            if self._chat is not None:
                with self._chat._lock:
                    self._chat._db.close()


class WorkspaceHandler(BaseHTTPRequestHandler):
    server_version = 'YggWorkspace/1'
    protocol_version = 'HTTP/1.0'

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, *args):
        pass  # URLs, queries, and session tickets do not belong in logs.

    def _headers(self, code, content_type, size=None, extra=None):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if size is not None:
            self.send_header('Content-Length', str(size))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _json(self, code, data, extra=None):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self._headers(code, 'application/json; charset=utf-8', len(raw), extra)
        self.wfile.write(raw)

    def _guard(self):
        host = self.headers.get('Host', '')
        valid = (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
        if host not in valid:
            self._json(403, {'error': 'Недопустимый Host'})
            return False
        origin = self.headers.get('Origin')
        if origin is not None and origin != 'http://' + host:
            self._json(403, {'error': 'Межсайтовый запрос запрещён'})
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self._json(403, {'error': 'Межсайтовый запрос запрещён'})
            return False
        if self.command not in ('GET', 'HEAD') and self.headers.get('X-Ygg-Request') != '1':
            self._json(403, {'error': 'Отсутствует защита запроса'})
            return False
        return True

    def _session(self):
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            name = self.server.cookie_name
            key = cookie[name].value if name in cookie else ''
        except Exception:
            key = ''
        with self.server.auth_lock:
            expires = self.server.sessions.get(key, 0)
            if expires <= time.monotonic():
                self.server.sessions.pop(key, None)
                self._json(401, {'error': 'Откройте Workspace командой ygg для входа'})
                return False
        return True

    def _body(self):
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('Transfer-Encoding не поддерживается')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise ValueError('Некорректная длина запроса') from None
        if length < 0:
            raise ValueError('Некорректная длина запроса')
        if length > 1_048_576:
            raise OverflowError('Слишком большой запрос')
        if self.headers.get_content_type() != 'application/json':
            raise ValueError('Ожидается application/json')
        try:
            body = json.loads(self.rfile.read(length) or '{}')
        except (ValueError, UnicodeDecodeError):
            raise ValueError('Некорректный JSON') from None
        if not isinstance(body, dict):
            raise ValueError('Ожидается JSON-объект')
        return body

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def do_PUT(self):
        self._dispatch()

    def do_DELETE(self):
        self._dispatch()

    def _dispatch(self):
        try:
            if not self._guard():
                return
            path = urllib.parse.urlsplit(self.path).path
            if path in ('/_launch', '/_shutdown') and self.command == 'POST':
                if self.headers.get('Origin') is not None:
                    return self._json(403, {'error': 'Запуск доступен только из CLI'})
                if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.server.control):
                    return self._json(401, {'error': 'Нет разрешения запуска'})
                self._body()
                if path == '/_shutdown':
                    manager = self.server.management
                    with manager._lock:
                        if any(job['status'] == 'running' for job in manager._jobs.values()):
                            return self._json(409, {'error': 'Finish or stop the running command before restarting.'})
                        manager._closed = True
                    self._json(200, {'ok': True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                return self._json(200, {'ticket': self.server.issue_ticket(), 'workspace': True,
                    'user_id': self.server.user_id, 'namespace': self.server.namespace,
                    'engine_url': getattr(self.server.query, 'url', None), 'pid': os.getpid()})
            if path == '/api/session' and self.command == 'POST':
                ticket = self._body().get('ticket', '')
                if not isinstance(ticket, str):
                    raise ValueError('Некорректное разрешение запуска')
                with self.server.auth_lock:
                    if self.server.tickets.pop(ticket, 0) <= time.monotonic():
                        return self._json(401, {'error': 'Ссылка истекла. Запустите ygg ещё раз.'})
                    now = time.monotonic()
                    self.server.sessions = {k:v for k,v in self.server.sessions.items() if v > now}
                    if len(self.server.sessions) >= 64:
                        self.server.sessions.pop(next(iter(self.server.sessions)))
                    key = secrets.token_urlsafe(32)
                    self.server.sessions[key] = now + 43200
                return self._json(200, {'ok': True}, {'Set-Cookie': f'{self.server.cookie_name}={key}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200'})
            if path.startswith('/api/'):
                if not self._session():
                    return
                return self._api(path)
            if self.command != 'GET':
                return self._json(404, {'error': 'Маршрут не найден'})
            return self._static(path)
        except OverflowError as exc:
            self._json(413, {'error': str(exc)})
        except (ValueError, TypeError) as exc:
            self._json(400, {'error': str(exc)})
        except KeyError:
            self._json(404, {'error': 'Данные не найдены в этой области'})
        except RuntimeError as exc:
            self._json(502, {'error': str(exc)})
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass
        except Exception:
            self._json(500, {'error': 'Внутренняя ошибка Workspace'})

    def _api(self, path):
        method = self.command
        if path == '/api/release' and method == 'GET':
            return self._json(200, self.server.release.snapshot())
        if path == '/api/release/update' and method == 'POST':
            return self._json(200, self.server.release.start(self._body()))
        if path == '/api/release/restart' and method == 'POST':
            self._body()
            completed = self.server.release.resume_result()
            manager = self.server.management
            with manager._lock:
                manager._available()
                manager._closed = True
                self.server.completed_update = completed
                self.server.restart_requested = True
            self._json(200, {'ok': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if path == '/api/models' and method == 'POST':
            from .ygg_workspace_models import discover_models
            body = self._body()
            with self.server.management._lock:
                result = discover_models(body, self.server.chat)
            return self._json(200, result)
        if path == '/api/config':
            if method == 'GET':
                return self._json(200, self.server.management.configuration())
            if method == 'PUT':
                return self._json(200, self.server.management.save_configuration(self._body()))
        if path == '/api/commands' and method == 'GET':
            return self._json(200, self.server.management.commands())
        if path == '/api/jobs':
            if method == 'GET':
                return self._json(200, self.server.management.jobs())
            if method == 'POST':
                return self._json(200, self.server.management.start(self._body()))
        job_parts = path.strip('/').split('/')
        if len(job_parts) >= 3 and job_parts[:2] == ['api', 'jobs']:
            if len(job_parts) == 3 and method == 'GET':
                return self._json(200, self.server.management.get(job_parts[2]))
            if len(job_parts) == 4 and method == 'POST':
                if job_parts[3] == 'input':
                    body = self._body()
                    return self._json(200, self.server.management.input(job_parts[2], body.get('text'), body.get('secret', False)))
                if job_parts[3] == 'stop':
                    self._body()
                    return self._json(200, self.server.management.stop(job_parts[2]))
        if path == '/api/status' and method == 'GET':
            try:
                self.server.query({'op': 'projects'})
                engine = True
            except RuntimeError:
                engine = False
            return self._json(200, {'engine': engine, 'user_id': self.server.user_id, 'namespace': self.server.namespace})
        if path == '/api/projects' and method == 'GET':
            return self._json(200, self.server.query({'op': 'projects'}))
        if path in ('/api/memories', '/api/memory', '/api/sources', '/api/graph') and method == 'POST':
            return self._json(200, self.server.query({**self._body(), 'op': path.rsplit('/', 1)[1]}))
        if path == '/api/settings':
            if method == 'GET':
                return self._json(200, self.server.chat.settings())
            if method == 'PUT':
                return self._json(200, self.server.chat.save_settings(self._body()))
        if path == '/api/chats/list' and method == 'POST':
            body = self._body()
            if 'project' not in body:
                raise ValueError('Укажите область диалога')
            return self._json(200, self.server.chat.list_chats(body['project']))
        if path == '/api/chats' and method == 'POST':
            body = self._body()
            if 'project' not in body:
                raise ValueError('Укажите область диалога')
            return self._json(200, self.server.chat.create_chat(body['project'], body.get('memory_id')))
        parts = path.strip('/').split('/')
        if len(parts) >= 3 and parts[:2] == ['api', 'chats']:
            ident = parts[2]
            if len(parts) == 3 and method == 'GET':
                return self._json(200, self.server.chat.get_chat(ident))
            if len(parts) == 3 and method == 'DELETE':
                return self._json(200, self.server.chat.delete_chat(ident))
            if len(parts) == 4 and parts[3] == 'stop' and method == 'POST':
                self._body()
                return self._json(200, self.server.chat.stop(ident))
            if len(parts) == 4 and parts[3] == 'messages' and method == 'POST':
                body = self._body()
                stream = iter(self.server.chat.stream(ident, body.get('content')))
                first = next(stream)
                self._headers(200, 'application/x-ndjson; charset=utf-8')
                try:
                    self._event(first)
                    for event in stream:
                        self._event(event)
                except (BrokenPipeError, ConnectionResetError, socket.timeout):
                    self.server.chat.stop(ident)
                finally:
                    if hasattr(stream, 'close'):
                        stream.close()
                return
        self._json(404, {'error': 'Маршрут не найден'})

    def _event(self, event):
        self.wfile.write(json.dumps(event, ensure_ascii=False).encode() + b'\n')
        self.wfile.flush()

    def _static(self, path):
        decoded = urllib.parse.unquote(path)
        target = (self.server.static / decoded.lstrip('/')).resolve()
        if not target.is_relative_to(self.server.static):
            return self._json(404, {'error': 'Файл не найден'})
        if not target.is_file():
            if decoded == '/' or decoded.startswith(('/project', '/chat', '/settings', '/operations')):
                target = self.server.static / 'index.html'
            else:
                return self._json(404, {'error': 'Файл не найден'})
        if not target.is_file():
            return self._json(503, {'error': 'Веб-сборка отсутствует. Выполните npm ci и npm run build в web/.'})
        raw = target.read_bytes()
        self._headers(200, mimetypes.guess_type(str(target))[0] or 'application/octet-stream', len(raw))
        self.wfile.write(raw)


def main(argv=None):
    from .ygg_workspace_launch import main as launch_main
    return launch_main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
