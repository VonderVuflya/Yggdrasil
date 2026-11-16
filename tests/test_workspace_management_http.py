import unittest
import test_workspace_http as base


class ManagementHTTPTests(unittest.TestCase):
    setUp = base.WorkspaceHTTPTests.setUp
    tearDown = base.WorkspaceHTTPTests.tearDown
    request = base.WorkspaceHTTPTests.request
    login = base.WorkspaceHTTPTests.login

    def test_management_routes_require_session_and_return_catalog(self):
        self.assertEqual(self.request('/api/config')[0], 401)
        self.assertEqual(self.request('/api/commands')[0], 401)
        self.login()
        import json
        status, _, raw = self.request('/api/config')
        self.assertEqual(status, 200)
        keys = {s['key'] for g in json.loads(raw)['groups'] for s in g['settings']}
        from yggdrasil.ygg_config import SETTINGS
        self.assertEqual(keys, set(SETTINGS))
        status, _, raw = self.request('/api/commands')
        self.assertEqual(status, 200)
        names = {c['name'] for c in json.loads(raw)['commands']}
        self.assertTrue({'seed','config','status','sync','review'}.issubset(names))

    def test_management_mutations_still_require_csrf(self):
        self.login()
        self.assertEqual(self.request('/api/config', {'values':{}}, {'X-Ygg-Request':''}, method='PUT')[0],403)
        self.assertEqual(self.request('/api/jobs', {'command':'seed','args':[]}, {'Origin':'https://evil.example'})[0],403)

    def test_models_route_is_authenticated_and_validates(self):
        self.assertEqual(self.request('/api/models', {'provider':'invalid','url':'file:///etc/passwd'})[0],401)
        self.login()
        self.assertEqual(self.request('/api/models', {'provider':'invalid','url':'file:///etc/passwd'})[0],400)

    def test_job_unknown_id_and_command_never_start_shell(self):
        self.login()
        self.assertEqual(self.request('/api/jobs', {'command':'sh','args':['-c','false']})[0],400)
        self.assertEqual(self.request('/api/jobs/missing')[0],404)

    def test_shutdown_requires_control_key_even_with_browser_session(self):
        self.login()
        self.assertEqual(self.request('/_shutdown', {})[0], 401)
        self.assertEqual(self.request('/_shutdown', {}, {'Authorization':'Bearer control-secret', 'Origin':self.origin})[0], 403)

    def test_shutdown_refuses_active_job_and_closes_idle_server(self):
        from unittest.mock import patch
        manager = self.server.management
        manager._jobs['fixture'] = {'status':'running'}
        try:
            self.assertEqual(self.request('/_shutdown', {}, {'Authorization':'Bearer control-secret'})[0], 409)
            self.assertFalse(manager._closed)
        finally:
            manager._jobs.clear()
        with patch.object(self.server, 'shutdown') as shutdown:
            self.assertEqual(self.request('/_shutdown', {}, {'Authorization':'Bearer control-secret'})[0], 200)
            self.thread.join(timeout=.05)
            self.assertTrue(manager._closed)
            shutdown.assert_called_once()

    def test_release_api_requires_session_and_update_confirmation(self):
        from unittest.mock import Mock
        self.assertEqual(self.request('/api/release')[0], 401)
        self.assertEqual(self.request('/api/release/update', {'confirmed':True})[0],401)
        self.login()
        release = Mock()
        release.snapshot.return_value = {'current':'1.0.0','stars':12}
        release.start.return_value = {'update':{'status':'running'}}
        self.server._release = release
        self.assertEqual(self.request('/api/release')[0],200)
        self.assertEqual(self.request('/api/release/update', {'confirmed':True}, {'X-Ygg-Request':''})[0],403)
        self.assertEqual(self.request('/api/release/update', {'confirmed':True})[0],200)
        release.start.assert_called_once_with({'confirmed':True})

    def test_release_restart_only_after_verified_update_and_without_active_jobs(self):
        from unittest.mock import Mock, patch
        self.login()
        self.server._release = Mock()
        self.server._release.resume_result.side_effect = ValueError('Complete the update')
        self.assertEqual(self.request('/api/release/restart', {})[0],400)
        self.server._release.resume_result.side_effect = None
        self.server._release.resume_result.return_value = {'id':'update-1','status':'completed'}
        self.server.management._jobs['fixture'] = {'status':'running'}
        try:
            self.assertEqual(self.request('/api/release/restart', {})[0],400)
            self.assertFalse(self.server.restart_requested)
        finally:
            self.server.management._jobs.clear()
        with patch.object(self.server,'shutdown') as shutdown:
            self.assertEqual(self.request('/api/release/restart', {})[0],200)
            self.thread.join(timeout=.05)
            self.assertTrue(self.server.restart_requested)
            shutdown.assert_called_once()
