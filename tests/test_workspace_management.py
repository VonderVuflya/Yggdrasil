"""Workspace management uses temporary homes and harmless process fixtures only."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from yggdrasil import ygg_config as config
from yggdrasil import ygg_workspace_management as management


class ManagementTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.env = patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                             if not k.startswith("YGG_")}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.manager = management.Management(self.home)
        self.addCleanup(self.manager.close)

    def settings(self, result=None):
        result = result or self.manager.configuration()
        return {s['key']: s for g in result['groups'] for s in g['settings']}

    def wait(self, job):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = self.manager.get(job['id'])
            if result['status'] != 'running':
                return result
            time.sleep(.01)
        self.fail('fixture did not finish')

    def fixture(self, code, command='help', args=None):
        real_popen = subprocess.Popen
        calls = []

        def launch(argv, **kwargs):
            calls.append((argv, kwargs))
            return real_popen([sys.executable, '-u', '-c', code], **kwargs)

        with patch.object(management.subprocess, 'Popen', side_effect=launch):
            job = self.manager.start({'command': command, 'args': args or [], 'confirmed': True})
        return job, calls

    def test_registry_all_settings_and_environment_precedence(self):
        (self.home / 'config.json').write_text(json.dumps({'embed_url': 'http://stored:1234'}))
        with patch.dict(os.environ, {'YGG_EMBED_URL': 'http://environment:1234'}):
            settings = self.settings()
        self.assertEqual(set(settings), set(config.SETTINGS))
        self.assertEqual(settings['embed_url']['value'], 'http://environment:1234')
        self.assertEqual(settings['embed_url']['stored_value'], 'http://stored:1234')
        self.assertEqual(settings['embed_url']['source'], 'env:YGG_EMBED_URL')
        self.assertEqual(settings['distill_url']['value'], 'http://environment:1234')
        self.assertTrue(settings['user_id']['restart_required'])

    def test_subprocess_output_uses_utf8_even_with_legacy_parent_encoding(self):
        with patch.dict(os.environ, {'PYTHONIOENCODING': 'cp1252'}):
            job, calls = self.fixture("print('Привет ✓')")
        self.assertEqual(calls[0][1]['env']['PYTHONIOENCODING'], 'utf-8')
        result = self.wait(job)
        self.assertEqual(result['status'], 'completed', result['output'])
        self.assertIn('Привет ✓', result['output'])

    def test_save_preserves_config_and_hides_private_keys(self):
        (self.home / 'config.json').write_text(json.dumps({'unrelated': {'keep': 1}}))
        result = self.manager.save_configuration({'values': {'embed_api_key': 'secret-key', 'user_id': 'alice'}})
        self.assertEqual(json.loads((self.home / 'config.json').read_text()), {'unrelated': {'keep': 1}, 'user_id': 'alice'})
        self.assertEqual((self.home / 'embed_api_key').read_text(), 'secret-key')
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE((self.home / 'embed_api_key').stat().st_mode), 0o600)
        entry = self.settings(result)['embed_api_key']
        self.assertEqual([entry[k] for k in ('value', 'stored_value', 'default')], ['', '', ''])
        self.assertTrue(entry['has_value'])
        self.assertNotIn('secret-key', json.dumps(result))
        self.assertEqual(result['identity']['user_id'], 'alice')
        self.manager.save_configuration({'values': {}, 'unset': ['embed_api_key', 'user_id']})
        self.assertFalse((self.home / 'embed_api_key').exists())
        self.assertEqual(self.manager.configuration()['identity']['user_id'], 'local')

    def test_all_validation_happens_before_any_write(self):
        invalid = [None, [], {'values': []}, {'values': {'bad': 'x'}},
                   {'values': {'distill_timeout': 'NaN'}}, {'values': {'embed_ttl': '-1'}},
                   {'values': {'embed_backend': 'invalid'}}, {'values': {'user_id': ''}},
                   {'values': {'embed_url': 'file:///tmp/x'}}, {'values': {'namespace': 5}},
                   {'values': {'namespace': 'a\nb'}}, {'values': {}, 'unset': ['unknown']},
                   {'values': {'namespace': 'a'}, 'unset': ['namespace']},
                   {'values': {}, 'cwd': '/tmp'}]
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(ValueError):
                if isinstance(body, dict) and isinstance(body.get('values'), dict):
                    body['values']['embed_api_key'] = 'must-not-be-written'
                self.manager.save_configuration(body)
            self.assertEqual(list(self.home.iterdir()), [])

    def test_invalid_existing_config_is_not_destroyed(self):
        (self.home / 'config.json').write_text('{broken')
        with self.assertRaises(ValueError):
            self.manager.save_configuration({'values': {'namespace': 'new'}})
        self.assertEqual((self.home / 'config.json').read_text(), '{broken')

    def test_cli_reads_the_same_home_config_and_private_files(self):
        self.manager.save_configuration({'values': {'namespace': 'from-browser', 'embed_api_key': 'private-test'}})
        with patch.object(config, 'YGG_HOME', self.home), patch.object(config, 'CONFIG', self.home / 'config.json'), patch.object(config, 'SECRET_FILES', {'embed_api_key': self.home / 'embed_api_key'}):
            self.assertEqual(config.resolve('namespace'), 'from-browser')
            self.assertEqual(config.resolve('embed_api_key'), 'private-test')
            config.set_value('namespace', 'from-cli')
        self.assertEqual(self.settings()['namespace']['value'], 'from-cli')

    def test_catalog_includes_cli_aliases_and_confirmation(self):
        from yggdrasil.cli import MEMORY_CMDS, SERVICE_CMDS
        commands = {c['name']: c for c in self.manager.commands()['commands']}
        expected = MEMORY_CMDS | SERVICE_CMDS | {'ui', 'version', '--version', '-V', 'help', '-h', '--help', '-help', 'serve', 'mcp', 'mcp-http', 'setup', 'wizard', 'recommend', 'hw', 'providers', 'stats', 'seed', 'distill', 'sync', 'install', 'ensure', 'doctor', 'register', 'reindex', 'config', 'update', 'redeploy'}
        self.assertEqual(set(commands), expected)
        for name in ('delete', 'reset', 'seed', 'uninstall', 'config', 'setup'):
            self.assertTrue(commands[name]['confirmation'])

    def test_rejects_payloads_before_launch(self):
        for body in ({'command': 'sh', 'args': []}, {'command': 'help', 'args': ';whoami'},
                     {'command': 'help', 'args': ['x\0']}, {'command': 'help', 'args': [], 'cwd': '/tmp'},
                     {'command': 'delete', 'args': []}, {'command': 'seed', 'args': [], 'confirmed': 'yes'}):
            with self.subTest(body=body), patch.object(management.subprocess, 'Popen') as launch, self.assertRaises(ValueError):
                self.manager.start(body)
            launch.assert_not_called()

    def test_subprocess_contract_output_failure_and_refresh(self):
        job, calls = self.fixture("import sys; print('stdout'); print('stderr', file=sys.stderr); sys.exit(3)", args=['a; echo NOT_A_SHELL'])
        result = self.wait(job)
        argv, kw = calls[0]
        self.assertEqual(argv, [sys.executable, '-m', 'yggdrasil.cli', 'help', 'a; echo NOT_A_SHELL'])
        self.assertIs(kw['shell'], False)
        self.assertEqual(kw['cwd'], self.home)
        self.assertEqual(kw['env']['YGG_HOME'], str(self.home))
        self.assertEqual(kw['env']['PYTHONUNBUFFERED'], '1')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['exit_code'], 3)
        self.assertIn('stdout', result['output'])
        self.assertIn('stderr', result['output'])
        self.assertEqual(self.manager.jobs()['jobs'], [result])
        self.assertEqual(set(result), {'id', 'command', 'args', 'status', 'output', 'exit_code', 'created_at', 'finished_at', 'interactive', 'truncated'})

    def test_output_and_arguments_redact_secrets_and_ansi(self):
        (self.home / 'token').write_text('engine-secret')
        (self.home / 'workspace_chat_key').write_text('chat-secret')
        (self.home / 'embed_api_key').write_text('embed-secret')
        code = "import sys,time; sys.stdout.write('\\x1b[31mengine-sec'); sys.stdout.flush(); time.sleep(.08); print('ret chat-secret embed-secret argument-secret\\x1b[0m')"
        job, _ = self.fixture(code, 'config', ['set', 'distill_api_key', 'argument-secret'])
        result = self.wait(job)
        for secret in ('engine-secret', 'chat-secret', 'embed-secret', 'argument-secret', '\x1b'):
            self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(result['args'][-1], '[redacted]')
        self.assertIn('[redacted]', result['output'])

    def test_partial_secret_is_never_exposed_during_poll(self):
        (self.home / 'token').write_text('secret-value')
        job, _ = self.fixture("import sys,time; print('sec', end='', flush=True); time.sleep(.3); print('ret-value')")
        time.sleep(.1)
        self.assertNotIn('sec', self.manager.get(job['id'])['output'])
        self.assertNotIn('secret-value', self.wait(job)['output'])

    def test_output_is_bounded(self):
        with patch.object(management, 'OUTPUT_LIMIT', 512):
            job, _ = self.fixture("print('x' * 20000)")
            result = self.wait(job)
            self.assertLessEqual(len(result['output']), 512)
            self.assertTrue(result['truncated'])

    def test_pipe_fallback_accepts_line_input_and_reports_limit(self):
        with patch.object(management, 'PTY_AVAILABLE', False):
            setup = next(c for c in self.manager.commands()['commands'] if c['name'] == 'setup')
            self.assertIn('Line input only', setup['description'])
            job, _ = self.fixture("import sys; print('tty='+str(sys.stdin.isatty()),flush=True); answer=input(); print('accepted',flush=True)", 'setup')
        self.manager.input(job['id'], 'secret answer\n')
        result = self.wait(job)
        self.assertIn('tty=False', result['output'])
        self.assertIn('accepted', result['output'])

    def test_output_redacts_control_and_legacy_config_keys(self):
        (self.home / 'workspace-control').write_text('control-secret')
        (self.home / 'config.json').write_text(json.dumps({'embed_api_key': 'legacy-secret'}))
        job, _ = self.fixture("print('control-secret legacy-secret')")
        result = self.wait(job)
        self.assertNotIn('control-secret', result['output'])
        self.assertNotIn('legacy-secret', result['output'])

    def test_history_is_bounded_and_new_manager_does_not_restore_jobs(self):
        with patch.object(management, 'JOB_LIMIT', 2):
            for _ in range(3):
                job, _ = self.fixture("print('ok')")
                self.wait(job)
        self.assertEqual(len(self.manager.jobs()['jobs']), 2)
        other = management.Management(self.home)
        self.addCleanup(other.close)
        self.assertEqual(other.jobs(), {'jobs': []})

    def test_actual_module_help_runs_from_an_empty_temporary_home(self):
        job = self.manager.start({'command': '--help', 'args': []})
        result = self.wait(job)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('ygg seed', result['output'])

    def test_input_backpressure_does_not_block_management(self):
        job, _ = self.fixture("import time; time.sleep(20)", 'setup')
        started = time.monotonic()
        for _ in range(80):
            try:
                self.manager.input(job['id'], 'a' * 16000)
            except ValueError:
                break
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(self.manager.stop(job['id'])['status'], 'stopped')

    @unittest.skipUnless(os.name == 'posix', 'POSIX owned process group')
    def test_stop_kills_owned_descendant_that_ignores_term_without_touching_external_process(self):
        external = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])
        self.addCleanup(lambda: external.wait(timeout=3))
        self.addCleanup(external.kill)
        code = ("import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"
                "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print(\"child-ready\",flush=True); time.sleep(30)']); time.sleep(30)")
        job, _ = self.fixture(code, 'setup')
        deadline = time.monotonic() + 4
        while 'child-ready' not in self.manager.get(job['id'])['output'] and time.monotonic() < deadline:
            time.sleep(.01)
        result = self.manager.stop(job['id'])
        self.assertEqual(result['status'], 'stopped')
        self.assertIsNone(external.poll())

    def test_input_stop_and_no_concurrent_mutation(self):
        job, _ = self.fixture("import sys; print('ready',flush=True); print('answer='+input(),flush=True); input()", 'setup')
        with self.assertRaises(ValueError):
            self.manager.start({'command': 'help', 'args': []})
        with self.assertRaises(ValueError):
            self.manager.save_configuration({'values': {'namespace': 'race'}})
        self.manager.input(job['id'], 'entered-private-key\n', secret=True)
        time.sleep(.08)
        result = self.manager.stop(job['id'])
        self.assertEqual(result['status'], 'stopped')
        self.assertIsNotNone(result['exit_code'])
        self.assertNotIn('entered-private-key', result['output'])
        self.assertEqual(self.manager.stop(job['id'])['status'], 'stopped')
        with self.assertRaises(KeyError):
            self.manager.stop('not-owned')

    def test_normal_input_is_not_treated_as_a_secret(self):
        job, _ = self.fixture("answer=input(); print('yes, 1 memory is ready',flush=True)", 'setup')
        self.manager.input(job['id'], 'y\n')
        self.assertIn('yes, 1 memory is ready', self.wait(job)['output'])

    def test_overlapping_secret_prefixes_do_not_expose_partial_values(self):
        buffer = management._Output()
        buffer.feed('prefix-sec', {'prefix', 'prefix-secret'})
        self.assertNotIn('sec', buffer.text)
        buffer.feed('ret\n', {'prefix', 'prefix-secret'}, final=True)
        self.assertEqual(buffer.text, '[redacted]\n')

    def test_redaction_markers_stay_stable_for_short_secret_values(self):
        buffer = management._Output()
        buffer.feed('a\n', {'a'})
        buffer.feed('b\n', {'a'}, final=True)
        self.assertEqual(buffer.text, '[redacted]\nb\n')

    @unittest.skipUnless(os.name == 'posix', 'POSIX raw terminal')
    def test_pty_supports_raw_arrow_keys_and_disables_echo(self):
        code = "import os,tty,termios; print('tty='+str(os.isatty(0)),flush=True); print('echo='+str(bool(termios.tcgetattr(0)[3]&termios.ECHO)),flush=True); tty.setraw(0); print('ready',flush=True); data=os.read(0,3); print('arrow='+str(data==b'\\x1b[B'),flush=True)"
        job, _ = self.fixture(code, 'setup')
        deadline = time.monotonic() + 4
        while 'ready' not in self.manager.get(job['id'])['output'] and time.monotonic() < deadline:
            time.sleep(.01)
        self.manager.input(job['id'], '\x1b[B')
        result = self.wait(job)
        self.assertIn('tty=True', result['output'])
        self.assertIn('echo=False', result['output'])
        self.assertIn('arrow=True', result['output'])


if __name__ == '__main__':
    unittest.main()
