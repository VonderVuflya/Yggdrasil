"""CLI lifecycle for the local Workspace, separate from the memory daemon."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import replace
from pathlib import Path

from . import service
from . import ygg_config as config
from .ygg_core import YggConfig
from .ygg_workspace import EngineQuery, WorkspaceServer, _NoRedirect


def engine_config():
    # The service honors YGG_PORT; an explicit external engine URL wins.
    return replace(YggConfig.from_env(), url=os.environ.get('YGG_ENGINE_URL', service.URL).rstrip('/'))


def control_key(home):
    home.mkdir(parents=True, exist_ok=True)
    path = home / 'workspace-control'
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        key = path.read_text().strip()
        if len(key) < 32:
            raise RuntimeError('Некорректный файл workspace-control')
        return key
    with os.fdopen(fd, 'w') as stream:
        key = secrets.token_urlsafe(48)
        stream.write(key)
    return key


def _launch_info(port, key, *, check_identity=True):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/_launch', b'{}',
        {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'X-Ygg-Request': '1'})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=1) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        exc.close()
        return None
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get('workspace') is not True:
        return None
    if check_identity and (data.get('user_id') != config.user_id() or data.get('namespace') != config.namespace()):
        raise RuntimeError('На этом порту Workspace другого пространства. Используйте ygg ui --port ДРУГОЙ_ПОРТ.')
    if check_identity and data.get('engine_url') not in (None, engine_config().url):
        raise RuntimeError('На этом порту Workspace другого движка. Используйте ygg ui --port ДРУГОЙ_ПОРТ.')
    if not isinstance(data.get('ticket'), str):
        return None
    return data


def _ticket(port, key):
    info = _launch_info(port, key)
    return info['ticket'] if info else None


def restart_workspace(port, key):
    # The home-specific control key proves ownership even after identity changes.
    info = _launch_info(port, key, check_identity=False)
    if info is None:
        return False
    request = urllib.request.Request(f'http://127.0.0.1:{port}/_shutdown', b'{}',
        {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'X-Ygg-Request': '1'})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=3) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        if code == 409:
            raise RuntimeError('Сначала завершите или остановите команду в Workspace.') from None
        if code != 404:
            raise RuntimeError('Workspace отказал в перезапуске.') from None
        # Upgrade from the first Workspace release, which had no shutdown route.
        # Never trust a PID file or terminate an unauthenticated listener.
        pid = info.get('pid')
        if type(pid) is not int or pid <= 1 or pid == os.getpid():
            raise RuntimeError('Workspace не сообщил корректный PID для перезапуска.') from None
        os.kill(pid, signal.SIGTERM)
    return True


def _wait_for_shutdown(port):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', port))
                return
            except OSError:
                time.sleep(0.05)
    raise RuntimeError('Workspace ещё завершает работу. Повторите запуск через несколько секунд.')


def launch(home, port, *, open_browser=True, ensure_engine=True):
    if not 1 <= port <= 65535:
        raise ValueError('Порт должен быть от 1 до 65535')
    home = Path(home)
    if ensure_engine:
        engine_url = engine_config().url
        if engine_url == service.URL and not service.ensure_running():
            raise RuntimeError('Не удалось запустить движок. Выполните ygg doctor.')
    key = control_key(home)
    ticket = _ticket(port, key)
    if ticket is None:
        # Never terminate or replace a process just because it owns our default port.
        with socket.socket() as probe:
            # Match HTTPServer.allow_reuse_address so a completed shutdown's
            # TIME_WAIT connections are not mistaken for a foreign listener.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                raise RuntimeError(f'Порт {port} занят другим процессом. Используйте ygg ui --port ДРУГОЙ_ПОРТ.') from None
        static = Path(__file__).parent / 'workspace_static' / 'index.html'
        if not static.is_file():
            raise RuntimeError('Нет веб-сборки. Выполните npm ci и npm run build в web/.')
        logdir = home / 'logs'
        logdir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, YGG_HOME=str(home))
        kwargs = {'env': env, 'stdin': subprocess.DEVNULL}
        if os.name == 'nt':
            kwargs['creationflags'] = 0x00000008 | 0x08000000
        else:
            kwargs['start_new_session'] = True
        with (logdir / 'workspace.log').open('ab') as log:
            child = subprocess.Popen([sys.executable, '-m', 'yggdrasil.ygg_workspace',
                                      '--serve', '--port', str(port)], stdout=log, stderr=log, **kwargs)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            ticket = _ticket(port, key)
            if ticket is not None:
                break
            if child.poll() is not None:
                raise RuntimeError(f'Workspace не запустился. Лог: {logdir / "workspace.log"}')
            time.sleep(0.1)
        if ticket is None:
            raise RuntimeError(f'Workspace не ответил вовремя. Лог: {logdir / "workspace.log"}')
    url = f'http://127.0.0.1:{port}/#ticket={ticket}'
    if open_browser:
        try:
            webbrowser.open(url)
        except webbrowser.Error:
            pass  # The URL is always printed by main, including headless shells.
    return url


def _save_resume(server):
    from .ygg_workspace_management import _atomic_write
    key = secrets.token_hex(24)
    with server.auth_lock:
        sessions = {k: v for k, v in server.sessions.items() if v > time.monotonic()}
    _atomic_write(server.home / ('workspace-resume-' + key), json.dumps({
        'sessions': sessions, 'user_id': server.user_id, 'namespace': server.namespace,
        'update': server.completed_update, 'expires': time.time() + 60}))
    return key


def _restore_resume(server, key):
    if not re.fullmatch(r'[a-f0-9]{48}', key):
        raise ValueError('Invalid restart handoff')
    path = server.home / ('workspace-resume-' + key)
    try:
        value = json.loads(path.read_text())
    finally:
        path.unlink(missing_ok=True)
    if (value.get('expires', 0) < time.time() or value.get('user_id') != server.user_id
            or value.get('namespace') != server.namespace):
        return
    now = time.monotonic()
    server.sessions = {k: v for k, v in value.get('sessions', {}).items()
                       if isinstance(k, str) and isinstance(v, (int, float)) and now < v <= now + 43200}
    server.completed_update = value.get('update')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='ygg ui', description='Локальное пространство проектов и чатов')
    parser.add_argument('--no-open', action='store_true', help='Вывести адрес без открытия браузера')
    parser.add_argument('--port', type=int, default=int(os.environ.get('YGG_UI_PORT', '42070')))
    parser.add_argument('--restart', action='store_true', help='Перезапустить Workspace после обновления или изменения конфигурации')
    parser.add_argument('--resume', help=argparse.SUPPRESS)
    parser.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    home = Path(os.environ.get('YGG_HOME', str(Path.home() / '.yggdrasil')))
    try:
        if args.serve:
            cfg = engine_config()
            query = EngineQuery(cfg.url, cfg.token, cfg.user_id, cfg.namespace)
            server = WorkspaceServer(('127.0.0.1', args.port), home=home, query=query,
                                     control=control_key(home), user_id=cfg.user_id, namespace=cfg.namespace)
            if args.resume:
                _restore_resume(server, args.resume)
            def terminate(signum, frame):
                raise KeyboardInterrupt
            previous = signal.signal(signal.SIGTERM, terminate)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
                signal.signal(signal.SIGTERM, previous)
            if server.restart_requested:
                resume = _save_resume(server)
                os.execv(sys.executable, [sys.executable, '-m', 'yggdrasil.ygg_workspace',
                    '--serve', '--port', str(args.port), '--resume', resume])
            return 0
        if args.restart and restart_workspace(args.port, control_key(home)):
            _wait_for_shutdown(args.port)
        print(launch(home, args.port, open_browser=not args.no_open))
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f'Workspace: {exc}', file=sys.stderr)
        return 1
