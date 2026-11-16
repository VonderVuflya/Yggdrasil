import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from yggdrasil.ygg_workspace_release import ReleaseService


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.manager = Mock()
        self.service = ReleaseService(self.home, self.manager)
        self.service.next_check = time.time() + 3600
        self.disk = patch('yggdrasil.ygg_workspace_release.disk_version', return_value='1.0.0')
        self.version = self.disk.start()
        self.addCleanup(self.disk.stop)

    def test_cached_version_and_stars_without_network(self):
        (self.home / 'workspace-release.json').write_text(json.dumps({'latest':'1.2.0','stars':6548,'checked_at':time.time()}))
        with patch('threading.Thread') as thread:
            result = ReleaseService(self.home, self.manager).snapshot()
        self.assertTrue(result['available'])
        self.assertEqual(result['current'], '1.0.0')
        self.assertEqual(result['stars'], 6548)
        thread.assert_not_called()

    def test_older_daemon_cache_cannot_hide_a_new_release(self):
        now = time.time()
        (self.home / 'workspace-release.json').write_text(json.dumps({'latest':'1.2.0','stars':12,'checked_at':now}))
        (self.home / 'update-check.json').write_text(json.dumps({'latest':'1.0.0','checked_at':now-3600}))
        with patch('threading.Thread') as thread:
            result = ReleaseService(self.home, self.manager).snapshot()
        self.assertTrue(result['available'])
        self.assertEqual(result['latest'], '1.2.0')
        thread.assert_not_called()

    def test_failed_fetch_preserves_cache_and_unknown_stars_are_null(self):
        self.service.latest = '1.2.0'
        with patch('yggdrasil.ygg_workspace_release._public_json', side_effect=OSError('offline')):
            self.service._refresh()
        result = self.service.snapshot()
        self.assertTrue(result['check_error'])
        self.assertEqual(result['latest'], '1.2.0')
        self.assertIsNone(result['stars'])

    def test_metadata_is_fetched_only_from_fixed_public_endpoints(self):
        with patch('yggdrasil.ygg_workspace_release._public_json', side_effect=[{'info':{'version':'1.3.0'}}, {'stargazers_count':12}]) as fetch:
            self.service._refresh()
        self.assertEqual(self.service.snapshot()['stars'], 12)
        self.assertTrue(all(call.args[0].startswith(('https://pypi.org/', 'https://api.github.com/')) for call in fetch.call_args_list))
        self.assertEqual(json.loads((self.home / 'workspace-release.json').read_text())['latest'], '1.3.0')

    def start(self):
        self.service.latest = '1.2.0'
        self.manager.start.return_value = {'id':'update-1'}
        self.manager.get.return_value = {'status':'running', 'output':'Downloading…', 'exit_code':None}
        return self.service.start({'confirmed':True})

    def test_update_uses_cli_and_duplicate_requests_reuse_job(self):
        result = self.start()
        again = self.service.start({'confirmed':True})
        self.manager.start.assert_called_once_with({'command':'update','args':[],'confirmed':True})
        self.assertEqual(result['update']['id'], again['update']['id'])
        self.assertEqual(result['update']['output'], 'Downloading…')

    def test_confirmation_and_no_update_block_launch(self):
        for body in ({}, {'confirmed':1}, {'confirmed':False}, {'confirmed':True,'command':'sh'}):
            with self.assertRaises(ValueError):
                self.service.start(body)
        with self.assertRaisesRegex(ValueError, 'No newer'):
            self.service.start({'confirmed':True})
        self.manager.start.assert_not_called()

    def test_exit_zero_without_installed_version_is_not_success(self):
        self.start()
        self.manager.get.return_value = {'status':'completed','output':'uvx: run again', 'exit_code':0}
        result = self.service.snapshot()['update']
        self.assertEqual(result['status'], 'failed')
        self.assertIn('not installed', result['error'])
        with self.assertRaises(ValueError):
            self.service.resume_result()

    def test_verified_upgrade_success_and_restart_excludes_output(self):
        self.start()
        self.version.return_value = '1.2.0'
        self.manager.get.return_value = {'status':'completed','output':'upgraded and redeployed', 'exit_code':0}
        result = self.service.snapshot()
        self.assertFalse(result['available'])
        self.assertEqual(result['update']['status'], 'completed')
        self.assertEqual(self.service.resume_result()['output'], '')
        self.assertEqual(self.service.resume_result()['target'], '1.2.0')

    def test_failed_redeploy_can_retry_when_package_already_upgraded(self):
        self.start()
        self.version.return_value = '1.2.0'
        self.manager.get.return_value = {'status':'failed','output':'redeploy failed','exit_code':1}
        self.assertEqual(self.service.snapshot()['update']['status'], 'failed')
        self.service.start({'confirmed':True})
        self.assertEqual(self.manager.start.call_count, 2)

    def test_invalid_public_metadata_does_not_become_ui_data(self):
        with patch('yggdrasil.ygg_workspace_release._public_json', side_effect=[{'info':{'version':'<html>'}}, {'stargazers_count':True}]):
            self.service._refresh()
        result = self.service.snapshot()
        self.assertIsNone(result['latest'])
        self.assertIsNone(result['stars'])


class RestartHandoffTests(unittest.TestCase):
    def test_handoff_preserves_only_live_sessions_once_and_is_private(self):
        from yggdrasil.ygg_workspace_launch import _save_resume, _restore_resume
        with tempfile.TemporaryDirectory() as tmp:
            server = Mock(home=Path(tmp), user_id='local', namespace='default')
            import threading
            server.auth_lock = threading.Lock()
            server.sessions = {'live':time.monotonic()+3600, 'expired':0}
            server.completed_update = {'id':'update-1','status':'completed','output':''}
            key = _save_resume(server)
            if os.name == 'posix':
                self.assertEqual((server.home / ('workspace-resume-'+key)).stat().st_mode & 0o777, 0o600)
            server.sessions = {}
            _restore_resume(server, key)
            self.assertEqual(set(server.sessions), {'live'})
            self.assertEqual(server.completed_update['id'], 'update-1')
            self.assertFalse((server.home / ('workspace-resume-'+key)).exists())
            with self.assertRaises(FileNotFoundError):
                _restore_resume(server, key)

    def test_expired_or_other_identity_handoff_never_authenticates(self):
        from yggdrasil.ygg_workspace_launch import _restore_resume
        with tempfile.TemporaryDirectory() as tmp:
            server = Mock(home=Path(tmp), user_id='local', namespace='default', sessions={})
            key = 'a'*48
            for values in ({'expires':0,'user_id':'local','namespace':'default'}, {'expires':time.time()+60,'user_id':'other','namespace':'default'}):
                (server.home / ('workspace-resume-'+key)).write_text(json.dumps({**values, 'sessions':{'secret':time.monotonic()+300}}))
                _restore_resume(server,key)
                self.assertEqual(server.sessions,{})
            with self.assertRaises(ValueError):
                _restore_resume(server,'../../outside')
