"""Cached public release metadata and a verified, shared CLI update operation."""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from pathlib import Path

from . import __version__
from .ygg_workspace_management import _atomic_write
from .ygg_update_check import _vtuple

REPOSITORY = 'https://github.com/VonderVuflya/Yggdrasil'
RELEASES = REPOSITORY + '/releases'
VERSION = re.compile(r'^\d+\.\d+\.\d+(?:[a-zA-Z0-9.+-]*)$')


def disk_version():
    """Read the installed code afresh; imported __version__ survives a pip upgrade."""
    try:
        text = Path(__file__).with_name('__init__.py').read_text(encoding='utf-8')
        match = re.search(r'__version__\s*=\s*[\"\']([^\"\']+)[\"\']', text)
        if match and VERSION.fullmatch(match[1]):
            return match[1]
    except OSError:
        pass
    return __version__


def _public_json(url):
    request = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'Yggdrasil-Workspace'})
    with urllib.request.urlopen(request, timeout=4) as response:
        raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError('Response too large')
        return json.loads(raw)


class ReleaseService:
    def __init__(self, home, manager, completed=None):
        self.home = Path(home)
        self.manager = manager
        self.lock = threading.RLock()
        self.refreshing = False
        self.next_check = 0
        self.latest = None
        self.stars = None
        self.check_error = False
        self.operation = completed
        self.completed = completed
        latest_checked = 0
        try:
            cache = json.loads((self.home / 'workspace-release.json').read_text())
            self._load(cache)
            latest_checked = float(cache.get('checked_at', 0))
            self.next_check = min(float(cache.get('checked_at', 0)) + 3600, time.time() + 3600)
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        # The daemon already maintains a PyPI cache; reuse it immediately.
        try:
            cache = json.loads((self.home / 'update-check.json').read_text())
            latest = cache.get('latest')
            if (isinstance(latest, str) and VERSION.fullmatch(latest)
                    and (not self.latest or float(cache.get('checked_at', 0)) >= latest_checked)):
                self.latest = latest
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def _load(self, value):
        latest, stars = value.get('latest'), value.get('stars')
        if isinstance(latest, str) and VERSION.fullmatch(latest):
            self.latest = latest
        if type(stars) is int and 0 <= stars < 1_000_000_000:
            self.stars = stars

    def _refresh(self):
        values = {}
        failed = False
        try:
            values['latest'] = _public_json('https://pypi.org/pypi/yggdrasil-memory/json')['info']['version']
        except Exception:
            failed = True
        try:
            values['stars'] = _public_json('https://api.github.com/repos/VonderVuflya/Yggdrasil')['stargazers_count']
        except Exception:
            pass  # Unknown stars are rendered as unavailable, never invented.
        with self.lock:
            self._load(values)
            self.check_error = failed
            self.refreshing = False
            try:
                _atomic_write(self.home / 'workspace-release.json', json.dumps({
                    'latest': self.latest, 'stars': self.stars, 'checked_at': time.time()}))
            except OSError:
                pass

    def _update(self, installed):
        if not self.operation:
            return None
        if self.completed:
            return self.completed
        try:
            job = self.manager.get(self.operation['id'])
        except KeyError:
            job = {'status': 'failed', 'output': '', 'exit_code': None}
        state = job['status']
        error = None
        if state == 'completed' and _vtuple(installed) < _vtuple(self.operation['target']):
            state = 'failed'
            error = 'The command finished, but the requested version was not installed. Review the output.'
        elif state in ('failed', 'stopped'):
            error = 'The update did not complete. Review the output and try again.'
        result = {**self.operation, 'status': state, 'output': job['output'],
                  'exit_code': job['exit_code'], 'error': error}
        if state != 'running':
            self.completed = result
        return result

    def snapshot(self):
        with self.lock:
            if not self.refreshing and time.time() >= self.next_check:
                self.refreshing = True
                self.next_check = time.time() + 3600
                threading.Thread(target=self._refresh, daemon=True).start()
            installed = disk_version()
            return {'current': installed, 'running': __version__, 'latest': self.latest,
                    'available': bool(self.latest and _vtuple(self.latest) > _vtuple(installed)),
                    'stars': self.stars, 'repository': REPOSITORY, 'releases': RELEASES,
                    'checking': self.refreshing, 'check_error': self.check_error,
                    'restart_required': installed != __version__, 'update': self._update(installed)}

    def start(self, body):
        if not isinstance(body, dict) or set(body) != {'confirmed'} or body.get('confirmed') is not True:
            raise ValueError('Confirm the update before starting.')
        with self.lock:
            installed = disk_version()
            current = self._update(installed)
            if current and current['status'] == 'running':
                return self.snapshot()
            if not self.latest or (_vtuple(self.latest) <= _vtuple(installed) and not (current and current['status'] in ('failed', 'stopped'))):
                raise ValueError('No newer version is available.')
            job = self.manager.start({'command': 'update', 'args': [], 'confirmed': True})
            self.operation = {'id': job['id'], 'target': self.latest, 'previous': installed}
            self.completed = None
            return self.snapshot()

    def resume_result(self):
        """Carry only completion metadata across restart, never command output."""
        with self.lock:
            update = self._update(disk_version())
            if not update or update['status'] != 'completed':
                raise ValueError('Complete the update before restarting Workspace.')
            return {**update, 'output': ''}
