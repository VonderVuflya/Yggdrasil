"""Exercise a real Workspace process replacement, with a harmless fake installer.

Only a temporary package copy is modified. No pip, service or model is invoked.
"""
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest


class ReleaseLifecycleTests(unittest.TestCase):
    def test_update_reexec_preserves_browser_session_and_reports_new_code(self):
        with tempfile.TemporaryDirectory(prefix='ygg-update-fixture-') as directory:
            root = Path(directory)
            package = root / 'package' / 'yggdrasil'
            source = Path(__file__).resolve().parents[1] / 'yggdrasil'
            package.mkdir(parents=True)
            for file in source.glob('*.py'):
                shutil.copy2(file, package / file.name)
            home = root / 'home'
            home.mkdir()
            (home / 'workspace-release.json').write_text(json.dumps({'latest':'99.0.0','stars':12,'checked_at':time.time()}))
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            # Only the old process replaces the update command with this fixture.
            # The exec'd process boots the actual new module, without monkeypatches.
            installer = root / 'install_fixture.py'
            installer.write_text(
                "from pathlib import Path\n"
                f"p=Path({str(package / '__init__.py')!r})\n"
                "lines=p.read_text().splitlines()\n"
                "p.write_text(chr(10).join('__version__ = '+repr('99.0.0') if line.startswith('__version__') else line for line in lines)+chr(10)+'# updated fixture')\n"
                "print('Fixture installer completed')\n")
            wrapper = f"""
import sys
from unittest.mock import patch
from yggdrasil import ygg_workspace_management as management
from yggdrasil.ygg_workspace_launch import main
original = management.subprocess.Popen
def launch(argv, **kwargs):
    if argv[1:4] != ['-m', 'yggdrasil.cli', 'update']:
        raise AssertionError('Unexpected fixture command')
    return original([sys.executable, '-u', {str(installer)!r}], **kwargs)
with patch.object(management.subprocess, 'Popen', side_effect=launch):
    raise SystemExit(main(['--serve', '--port', sys.argv[1]]))
"""
            launch_file = root / 'launch.py'
            launch_file.write_text(wrapper)
            env = {**os.environ, 'PYTHONPATH':str(package.parent), 'YGG_HOME':str(home),
                   'YGG_USER_ID':'fixture', 'YGG_NAMESPACE':'fixture', 'YGG_ENGINE_URL':'http://127.0.0.1:9'}
            with (root / 'server.log').open('w+') as log:
                process = subprocess.Popen([sys.executable, str(launch_file), str(port)], env=env, cwd=root, stdout=log, stderr=log)
                def request(path, body=None, headers=None):
                    connection = http.client.HTTPConnection('127.0.0.1',port,timeout=2)
                    connection.request('POST' if body is not None else 'GET',path, json.dumps(body) if body is not None else None,
                        {'Content-Type':'application/json','X-Ygg-Request':'1', **(headers or {})})
                    response = connection.getresponse()
                    value = response.status, dict(response.getheaders()), json.loads(response.read())
                    connection.close()
                    return value
                try:
                    for _ in range(100):
                        try:
                            key = (home / 'workspace-control').read_text()
                            status, _, info = request('/_launch', {}, {'Authorization':'Bearer '+key})
                            if status == 200:
                                break
                        except OSError:
                            pass
                        if process.poll() is not None:
                            log.seek(0)
                            self.fail(log.read())
                        time.sleep(.05)
                    else:
                        self.fail('Workspace fixture failed to start')
                    status, headers, _ = request('/api/session', {'ticket':info['ticket']})
                    self.assertEqual(status,200)
                    auth = {'Cookie':headers['Set-Cookie'].split(';')[0]}
                    status, _, value = request('/api/release/update', {'confirmed':True}, auth)
                    self.assertEqual(status,200,value)
                    for _ in range(100):
                        _, _, value = request('/api/release', headers=auth)
                        if value['update']['status'] != 'running':
                            break
                        time.sleep(.05)
                    self.assertEqual(value['update']['status'],'completed',value['update'])
                    self.assertTrue(value['restart_required'])
                    self.assertEqual(request('/api/release/restart',{},auth)[0],200)
                    for _ in range(160):
                        try:
                            status, _, value = request('/api/release', headers=auth)
                            if status == 200 and value['running'] == '99.0.0':
                                break
                        except (OSError, http.client.HTTPException):
                            pass
                        time.sleep(.05)
                    else:
                        log.seek(0)
                        self.fail(log.read())
                    self.assertEqual(value['current'],'99.0.0')
                    self.assertEqual(value['update']['status'],'completed')
                    self.assertFalse(value['restart_required'])
                    self.assertEqual(value['update']['output'],'')
                    self.assertEqual(list(home.glob('workspace-resume-*')),[])
                finally:
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=5)
