"""Local settings and bounded, server-owned CLI jobs for Workspace.

No command strings are evaluated. Jobs use the installed Python interpreter and
the same CLI dispatcher as the terminal, with a terminal for its existing wizard.
Only snapshots leave this module; subprocess handles and input remain private.
"""
from __future__ import annotations

import codecs
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import uuid

try:
    from . import ygg_config as config
except ImportError:  # deployed flat scripts
    import ygg_config as config


OUTPUT_LIMIT = 128 * 1024
JOB_LIMIT = 32
PTY_AVAILABLE = os.name == 'posix'
REDACTED = '[redacted]'
NUMBERS = {'distill_timeout': 1, 'distill_num_ctx': 1, 'distill_ttl': 0, 'embed_ttl': 0}
OPTIONS = {'embed_backend': ['ollama', 'openai'], 'distill_reasoning': ['auto', 'off', 'on']}
SECRET_FLAG = re.compile(r'(?:api[-_]key|token|password|secret)$', re.I)

# Metadata is explicit so a new CLI operation cannot accidentally become an
# executable browser endpoint without choosing its confirmation policy.
_CATALOG = (
    ('ui', 'Run or open Workspace', 'Service', True, True, ['--no-open']),
    ('install', 'Install and configure the background service', 'Service', True, True, []),
    ('setup', 'Run the interactive setup wizard', 'Configuration', True, True, []),
    ('wizard', 'Alias for setup', 'Configuration', True, True, []),
    ('recommend', 'Show hardware-aware model recommendations', 'Diagnostics', False, False, []),
    ('hw', 'Alias for recommend', 'Diagnostics', False, False, []),
    ('providers', 'Scan local model runtimes', 'Diagnostics', False, False, []),
    ('doctor', 'Diagnose the installation', 'Diagnostics', False, False, []),
    ('register', 'Register the MCP server with supported agents', 'Service', False, True, []),
    ('reindex', 'Backfill missing memory embeddings', 'Memory', False, True, []),
    ('config', 'Read, edit, set or unset persistent settings', 'Configuration', True, True, ['list']),
    ('update', 'Upgrade the package and redeploy the daemon', 'Service', False, True, []),
    ('redeploy', 'Redeploy installed code and restart the daemon', 'Service', False, True, []),
    ('status', 'Show service status', 'Diagnostics', False, False, []),
    ('start', 'Start the background service', 'Service', False, True, []),
    ('stop', 'Stop the background service', 'Service', False, True, []),
    ('restart', 'Restart the background service', 'Service', False, True, []),
    ('ensure', 'Ensure the memory engine is running', 'Service', False, True, []),
    ('logs', 'Read service logs', 'Diagnostics', False, False, []),
    ('token', 'Check the engine token (value is redacted)', 'Diagnostics', False, False, []),
    ('uninstall', 'Uninstall the background service', 'Service', True, True, []),
    ('hooks', 'Enable retrieval hooks', 'Service', False, True, []),
    ('unhooks', 'Disable retrieval hooks', 'Service', False, True, []),
    ('stophooks', 'Enable session distillation hooks', 'Service', False, True, []),
    ('unstophooks', 'Disable session distillation hooks', 'Service', False, True, []),
    ('consolidate', 'Enable scheduled consolidation', 'Service', False, True, []),
    ('unconsolidate', 'Disable scheduled consolidation', 'Service', False, True, []),
    ('serve', 'Run a memory engine until stopped', 'Service', False, True, []),
    ('mcp', 'Run the stdio MCP facade until stopped', 'Service', True, True, []),
    ('mcp-http', 'Run the HTTP MCP facade until stopped', 'Service', False, True, []),
    ('stats', 'Show memory statistics (starts engine if needed)', 'Memory', False, True, []),
    ('seed', 'Distill existing chats into memory', 'Memory', True, True, ['--dry-run']),
    ('distill', 'Distill a directory or file into lessons', 'Memory', False, True, ['--source', '/path/to/source']),
    ('sync', 'Sync memory through your configured git repository', 'Memory', False, True, []),
    ('health', 'Check memory engine health', 'Diagnostics', False, False, []),
    ('bootstrap', 'Build project memory context', 'Memory', False, False, ['--project', 'project']),
    ('search', 'Search project memories', 'Memory', False, False, ['--project', 'project', '--query', 'query']),
    ('recall', 'Recall memories across projects', 'Memory', False, False, ['--query', 'query']),
    ('remember', 'Store a memory', 'Memory', False, True, ['--project', 'project', '--type', 'lesson', '--content', 'content']),
    ('materialize', 'Materialize a memory into a project', 'Memory', False, True, ['--id', 'ID', '--project', 'project']),
    ('export-native', 'Write a curated memory digest to a file', 'Memory', False, True, ['--project', 'project']),
    ('import', 'Import memories from another memory tool', 'Memory', False, True, ['--from', 'mcp-memory', '--path', '/path/to/source']),
    ('review', 'Inspect or apply memory governance actions', 'Memory', True, True, []),
    ('pin', 'Pin a memory', 'Memory', False, True, ['--id', 'ID']),
    ('unpin', 'Unpin a memory', 'Memory', False, True, ['--id', 'ID']),
    ('supersede', 'Mark a memory as superseded', 'Memory', False, True, ['--id', 'ID']),
    ('delete', 'Permanently delete a memory', 'Memory', False, True, ['--id', 'ID']),
    ('reset', 'Permanently delete a selected group of memories', 'Memory', True, True, ['--project', 'project']),
    ('relate', 'Add a relation between memories', 'Memory', False, True, ['--from', 'ID', '--rel', 'solves', '--to', 'ID']),
    ('relations', 'List memory relations', 'Memory', False, False, ['--id', 'ID']),
    ('quality', 'Inspect memory quality', 'Memory', False, False, []),
    ('migrate', 'Migrate stored memories', 'Memory', False, True, []),
) + tuple((name, 'Show CLI help', 'Help', False, False, []) for name in ('help', '-h', '--help', '-help')) + tuple(
    (name, 'Show installed version', 'Help', False, False, []) for name in ('version', '--version', '-V'))


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8').strip()
    except (OSError, UnicodeError):
        return ''


def _mask(text: str, secrets: set[str]) -> str:
    if not secrets:
        return text
    # A single substitution avoids re-masking the replacement itself for a
    # short key or for keys contained within other configured credentials.
    pattern = '|'.join([re.escape(REDACTED), *(re.escape(secret) for secret in sorted(secrets, key=len, reverse=True))])
    return re.sub(pattern, REDACTED, text)


def _atomic_write(path: Path, value: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix='.workspace-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(value)
        os.replace(temporary, path)  # mkstemp creates mode 0600 before writing
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class _Output:
    """Strip split terminal escapes and retain secret prefixes until complete."""
    def __init__(self):
        self.text = ''
        self.pending = ''
        self.escape = ''
        self.truncated = False
        self.secrets: frozenset[str] = frozenset()
        self.trie: dict = {}

    def feed(self, text: str, secrets: set[str], final: bool = False) -> None:
        clean = []
        for char in text:
            if self.escape:
                if self.escape == '\x1b':
                    self.escape = '\x1b[' if char == '[' else ('\x1b]' if char == ']' else '')
                elif self.escape == '\x1b[':
                    if '@' <= char <= '~':
                        self.escape = ''
                elif char == '\x07' or (self.escape.endswith('\x1b') and char == '\\'):
                    self.escape = ''
                elif char == '\x1b':
                    self.escape = '\x1b]\x1b'
                continue
            if char == '\x1b':
                self.escape = char
            elif char == '\r':
                continue
            elif char in '\n\t' or ord(char) >= 32:
                clean.append(char)
        if secrets != self.secrets:
            self.secrets = frozenset(secrets)
            self.trie = {}
            for secret in secrets:
                node = self.trie
                for char in secret:
                    node = node.setdefault(char, {})
                node[None] = True
        combined = self.pending + ''.join(clean)
        self.pending = ''
        emitted = []
        index = 0
        while index < len(combined):
            node = self.trie
            end = index
            matched = None
            while end < len(combined) and combined[end] in node:
                node = node[combined[end]]
                end += 1
                if None in node:
                    matched = end
            if end == len(combined) and end > index and any(key is not None for key in node):
                # An incomplete longer key must remain private even when its
                # prefix is itself another complete known key.
                if final:
                    emitted.append(REDACTED)
                else:
                    self.pending = combined[index:]
                break
            if matched is not None:
                emitted.append(REDACTED)
                index = matched
            else:
                emitted.append(combined[index])
                index += 1
        self.text += ''.join(emitted)
        # A key may have been created by a wizard since the previous read.
        self.text = _mask(self.text, secrets)
        if len(self.text) > OUTPUT_LIMIT:
            self.text = self.text[-OUTPUT_LIMIT:]
            self.truncated = True


class Management:
    def __init__(self, home: Path):
        self.home = Path(home).resolve()
        self._lock = threading.RLock()
        self._jobs: dict[str, dict] = {}
        self._closed = False

    def _config(self) -> dict:
        path = self.home / 'config.json'
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise ValueError('Cannot read existing config.json; repair it before saving settings.') from exc
        if not isinstance(value, dict):
            raise ValueError('Existing config.json must contain an object.')
        return value

    def _secret_path(self, key: str) -> Path:
        return self.home / config.SECRET_FILES[key].name

    def configuration(self) -> dict:
        with self._lock:
            stored = self._config()
            entries = {}
            identity = {}
            for key, (envs, default, description) in config.SETTINGS.items():
                secret = key in config.SECRET_FILES
                saved = (_read(self._secret_path(key)) if secret else
                         (str(stored[key]) if stored.get(key) not in (None, '') else ''))
                value = saved or default
                source = ('keyfile' if secret else 'config') if saved else 'default'
                for env in envs:
                    if os.environ.get(env):
                        value, source = os.environ[env], 'env:' + env
                        break
                if key in ('user_id', 'namespace'):
                    identity[key] = value
                entry = {'key': key, 'value': '' if secret else value,
                         'stored_value': '' if secret else (saved if key in stored and stored[key] is not None else None), 'source': source,
                         'default': '' if secret else default, 'description': description,
                         'secret': secret, 'has_value': bool(value),
                         'restart_required': key.startswith('embed_') or key in ('user_id', 'namespace'),
                         'type': 'number' if key in NUMBERS else ('select' if key in OPTIONS else 'string')}
                if key in OPTIONS:
                    entry['options'] = list(OPTIONS[key])
                entries[key] = entry
            groups = [{'id': f'group-{i}', 'label': label, 'settings': [entries[k] for k in keys]}
                      for i, (label, keys) in enumerate(config.grouped())]
            return {'groups': groups, 'identity': identity}

    def save_configuration(self, body) -> dict:
        if not isinstance(body, dict) or set(body) - {'values', 'unset'}:
            raise ValueError('Expected values and optional unset settings.')
        values, unset = body.get('values'), body.get('unset', [])
        if not isinstance(values, dict) or not isinstance(unset, list):
            raise ValueError('values must be an object and unset must be an array.')
        if any(not isinstance(k, str) or k not in config.SETTINGS for k in [*values, *unset]):
            raise ValueError('Unknown setting.')
        if set(values) & set(unset) or len(unset) != len(set(unset)):
            raise ValueError('A setting cannot be saved and unset together or unset twice.')
        for key, value in values.items():
            if not isinstance(value, str) or len(value) > 8192 or any(ord(c) < 32 for c in value):
                raise ValueError(f'{key} must be a single-line string of at most 8192 characters.')
            if key in NUMBERS and (not re.fullmatch(r'[0-9]+', value) or not NUMBERS[key] <= int(value) <= 2147483647):
                raise ValueError(f'{key} must be an integer between {NUMBERS[key]} and 2147483647.')
            if key in OPTIONS and value not in OPTIONS[key]:
                raise ValueError(f'Invalid value for {key}.')
            if key in ('user_id', 'namespace') and not value.strip():
                raise ValueError(f'{key} cannot be empty; use unset to restore its default.')
            if key.endswith('_url'):
                try:
                    url = urlsplit(value)
                    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.fragment:
                        raise ValueError()
                    url.port
                except ValueError:
                    raise ValueError(f'{key} must be an HTTP(S) endpoint without credentials or fragment.') from None
        with self._lock:
            self._available()
            stored = self._config()
            for key in unset:
                stored.pop(key, None)
            for key, value in values.items():
                if key not in config.SECRET_FILES:
                    stored[key] = value
                else:
                    stored.pop(key, None)
            self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
            # All validation and serialization precede the first disk write.
            serialized = json.dumps(stored, indent=2, sort_keys=True) + '\n'
            for key, value in values.items():
                if key in config.SECRET_FILES:
                    _atomic_write(self._secret_path(key), value.strip())
            for key in unset:
                if key in config.SECRET_FILES:
                    self._secret_path(key).unlink(missing_ok=True)
            _atomic_write(self.home / 'config.json', serialized)
            return self.configuration()

    def commands(self) -> dict:
        return {'commands': [{'name': name, 'description': description + (
            ' Line input only; arrow keys are unavailable on this platform.' if interactive and not PTY_AVAILABLE else ''),
            'group': group, 'interactive': interactive, 'confirmation': confirmation, 'example': list(example)}
            for name, description, group, interactive, confirmation, example in _CATALOG]}

    def _available(self) -> None:
        if self._closed:
            raise ValueError('Workspace management has been closed.')
        if any(job['status'] == 'running' for job in self._jobs.values()):
            raise ValueError('Another CLI job is running; wait for it or stop it first.')

    def _secrets(self) -> set[str]:
        paths = {'token', 'workspace_chat_key', 'workspace-control', 'workspace_key', 'workspace_session_key'}
        paths.update(path.name for path in config.SECRET_FILES.values())
        secrets = {_read(self.home / path) for path in paths}
        try:
            stored = self._config()
            secrets.update(str(stored[key]) for key in config.SECRET_FILES if stored.get(key))
        except ValueError:
            pass
        for env, value in os.environ.items():
            if SECRET_FLAG.search(env):
                secrets.add(value)
        return {value for value in secrets if value}

    def _snapshot(self, job: dict) -> dict:
        secrets = job['secrets'] | self._secrets()
        output = job['buffer'].text
        args = list(job['args'])
        output = _mask(output, secrets)
        args = [_mask(arg, secrets) for arg in args]
        return {key: job[key] for key in ('id', 'command', 'status', 'exit_code', 'created_at', 'finished_at', 'interactive')} | {
            'args': args, 'output': output, 'truncated': job['buffer'].truncated}

    def jobs(self) -> dict:
        with self._lock:
            return {'jobs': [self._snapshot(job) for job in reversed(list(self._jobs.values()))]}

    def get(self, identifier: str) -> dict:
        with self._lock:
            return self._snapshot(self._jobs[identifier])

    def start(self, body) -> dict:
        if not isinstance(body, dict) or set(body) - {'command', 'args', 'confirmed'}:
            raise ValueError('Expected command, args and optional confirmed flag.')
        name, args = body.get('command'), body.get('args')
        command = next((c for c in self.commands()['commands'] if c['name'] == name), None)
        if command is None:
            raise ValueError('Unsupported CLI command.')
        if (not isinstance(args, list) or len(args) > 256 or
                any(not isinstance(arg, str) or '\0' in arg or len(arg) > 8192 for arg in args) or
                sum(map(len, args)) > 65536):
            raise ValueError('args must be a bounded array of strings without NUL characters.')
        if 'confirmed' in body and not isinstance(body['confirmed'], bool):
            raise ValueError('confirmed must be a boolean.')
        if command['confirmation'] and body.get('confirmed') is not True:
            raise ValueError('This command changes local state and requires confirmation.')
        with self._lock:
            self._available()
            secrets = self._secrets()
            public_args = list(args)
            for i, arg in enumerate(args):
                flag, separator, value = arg.partition('=')
                if flag.startswith('-') and SECRET_FLAG.search(flag):
                    if separator:
                        secrets.add(value)
                        public_args[i] = flag + '=' + REDACTED
                    elif i + 1 < len(args):
                        secrets.add(args[i + 1])
                        public_args[i + 1] = REDACTED
            if name == 'config' and len(args) >= 3 and args[0] == 'set' and args[1] in config.SECRET_FILES:
                secrets.add(args[2])
                public_args[2] = REDACTED
            secrets.discard('')
            public_args = [_mask(arg, secrets) for arg in public_args]
            self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
            env = os.environ.copy()
            env.update(YGG_HOME=str(self.home), PYTHONUNBUFFERED='1')
            package_root = Path(__file__).resolve().parent.parent
            env['PYTHONPATH'] = str(package_root) + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
            master = slave = None
            options = {'cwd': self.home, 'env': env, 'shell': False, 'stderr': subprocess.STDOUT}
            if os.name == 'posix':
                options['start_new_session'] = True
            if PTY_AVAILABLE:
                import pty
                import termios
                master, slave = pty.openpty()
                attrs = termios.tcgetattr(slave)
                attrs[3] &= ~(termios.ECHO | termios.ECHONL)
                termios.tcsetattr(slave, termios.TCSANOW, attrs)
                options.update(stdin=slave, stdout=slave, stderr=slave)
                env.setdefault('TERM', 'xterm-256color')
            else:
                options.update(stdin=subprocess.PIPE, stdout=subprocess.PIPE)
                env['YGG_NO_TUI'] = '1'
                if os.name == 'nt':
                    options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            try:
                process = subprocess.Popen([sys.executable, '-m', 'yggdrasil.cli', name, *args], **options)
            except Exception:
                if master is not None:
                    os.close(master)
                raise
            finally:
                if slave is not None:
                    os.close(slave)
            job = {'id': uuid.uuid4().hex, 'command': name, 'args': public_args, 'status': 'running',
                   'exit_code': None, 'created_at': time.time(), 'finished_at': None,
                   'interactive': command['interactive'], 'buffer': _Output(), 'process': process,
                   'master': master, 'secrets': secrets, 'stopping': False,
                   'input_queue': queue.Queue(maxsize=16), 'done': threading.Event()}
            self._jobs[job['id']] = job
            while len(self._jobs) > JOB_LIMIT:
                del self._jobs[next(iter(self._jobs))]
            thread = threading.Thread(target=self._read_job, args=(job,), daemon=True, name='workspace-cli')
            job['thread'] = thread
            input_fd = os.dup(master if master is not None else process.stdin.fileno())
            if os.name == 'posix':
                os.set_blocking(input_fd, False)
            writer = threading.Thread(target=self._write_job, args=(job, input_fd), daemon=True, name='workspace-cli-input')
            job['writer'] = writer
            writer.start()
            thread.start()
            return self._snapshot(job)

    def _read_job(self, job: dict) -> None:
        process = job['process']
        decoder = codecs.getincrementaldecoder('utf-8')('replace')
        try:
            while True:
                try:
                    data = os.read(job['master'] if job['master'] is not None else process.stdout.fileno(), 4096)
                except BlockingIOError:
                    # Duplicated PTY input/output descriptors share flags.
                    import select
                    select.select([job['master']], [], [], .1)
                    continue
                except OSError:
                    break  # a closed POSIX slave reports EIO rather than EOF
                if not data:
                    break
                with self._lock:
                    job['secrets'].update(self._secrets())
                    job['buffer'].feed(decoder.decode(data), job['secrets'])
        finally:
            code = process.wait()
            job['done'].set()
            with self._lock:
                job['secrets'].update(self._secrets())
                job['buffer'].feed(decoder.decode(b'', final=True), job['secrets'], final=True)
                job['exit_code'] = code
                job['status'] = 'stopped' if job['stopping'] else ('completed' if code == 0 else 'failed')
                job['finished_at'] = time.time()
                if job['master'] is not None:
                    os.close(job['master'])
                    job['master'] = None
                for stream in (process.stdin, process.stdout):
                    if stream:
                        stream.close()

    def _write_job(self, job: dict, fd: int) -> None:
        """Bounded input queue keeps a full terminal/pipe off HTTP threads."""
        try:
            while not job['done'].is_set():
                try:
                    data = job['input_queue'].get(timeout=.1)
                except queue.Empty:
                    continue
                while data and not job['done'].is_set():
                    try:
                        count = os.write(fd, data)
                        data = data[count:]
                    except BlockingIOError:
                        import select
                        select.select([], [fd], [], .1)
        except OSError:
            pass  # process closed its input
        finally:
            os.close(fd)

    def input(self, identifier: str, text: str, secret: bool = False) -> dict:
        if not isinstance(text, str) or len(text) > 16384 or '\0' in text:
            raise ValueError('Input must be text of at most 16384 characters without NUL.')
        if not isinstance(secret, bool):
            raise ValueError('secret must be a boolean.')
        with self._lock:
            job = self._jobs[identifier]
            if job['status'] != 'running' or job['stopping']:
                raise ValueError('This job is no longer accepting input.')
            # Users can mark newly entered credentials before the CLI saves
            # them. Ordinary menu answers must not mask unrelated log text.
            if secret:
                for line in text.splitlines():
                    if line.strip() and not any(ord(c) < 32 for c in line):
                        job['secrets'].add(line.strip())
            try:
                job['input_queue'].put_nowait(text.encode('utf-8'))
            except queue.Full:
                raise ValueError('The job input queue is full; wait before sending more input.') from None
            return self._snapshot(job)

    def stop(self, identifier: str) -> dict:
        with self._lock:
            job = self._jobs[identifier]
            if job['status'] != 'running':
                return self._snapshot(job)
            job['stopping'] = True
            process = job['process']
            try:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
        # The launcher can exit while its children retain the PTY. They still
        # belong to this job's isolated process group and must be stopped too.
        job['thread'].join(timeout=.2)
        if os.name == 'posix' and job['thread'].is_alive():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        job['thread'].join(timeout=3)
        return self.get(identifier)

    def close(self) -> None:
        """Stop owned jobs when the HTTP server closes; do not restore on launch."""
        with self._lock:
            self._closed = True
            active = [job['id'] for job in self._jobs.values() if job['status'] == 'running']
        for identifier in active:
            self.stop(identifier)
