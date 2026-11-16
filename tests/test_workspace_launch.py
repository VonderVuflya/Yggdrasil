import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


class WorkspaceLaunchTests(unittest.TestCase):
    def test_no_args_dispatches_ui_and_help_still_prints_usage(self):
        from yggdrasil import cli
        with patch('sys.argv', ['ygg']), patch('yggdrasil.ygg_workspace.main', return_value=0) as run:
            self.assertEqual(cli._run(), 0)
            run.assert_called_once_with([])
        with patch('sys.argv', ['ygg', '--help']), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli._run(), 0)
        self.assertIn('ygg ui', out.getvalue())

    def test_control_key_is_persistent_and_private(self):
        from yggdrasil.ygg_workspace_launch import control_key
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            first = control_key(home)
            self.assertEqual(control_key(home), first)
            self.assertGreater(len(first), 30)
            if os.name != 'nt':
                self.assertEqual((home / 'workspace-control').stat().st_mode & 0o777, 0o600)

    def test_existing_server_is_reused_and_no_open_prints_ticket_url(self):
        from yggdrasil.ygg_workspace import WorkspaceServer
        from yggdrasil.ygg_workspace_launch import control_key, launch
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            server = WorkspaceServer(('127.0.0.1', 0), home=home,
                query=lambda b: {'projects': []}, control=control_key(home))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch('subprocess.Popen') as spawn, patch('webbrowser.open') as browser:
                    url = launch(home, server.server_port, open_browser=False, ensure_engine=False)
                    second = launch(home, server.server_port, open_browser=False, ensure_engine=False)
                self.assertIn('#ticket=', url)
                self.assertNotEqual(url, second)
                spawn.assert_not_called()
                browser.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_port_owned_by_other_process_is_not_stopped(self):
        import socket
        from yggdrasil.ygg_workspace_launch import launch
        with tempfile.TemporaryDirectory() as tmp, socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            sock.listen()
            with patch('subprocess.Popen') as spawn:
                with self.assertRaises(RuntimeError):
                    launch(Path(tmp), sock.getsockname()[1], open_browser=False, ensure_engine=False)
                spawn.assert_not_called()

    def test_wrong_identity_existing_server_not_reused(self):
        from yggdrasil.ygg_workspace import WorkspaceServer
        from yggdrasil.ygg_workspace_launch import launch, control_key
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            server = WorkspaceServer(('127.0.0.1', 0), home=home, query=lambda b: {},
                                     control=control_key(home), user_id='someone-else')
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with self.assertRaises(RuntimeError):
                    launch(home, server.server_port, open_browser=False, ensure_engine=False)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_engine_config_honors_service_port_and_explicit_url(self):
        from yggdrasil.ygg_workspace_launch import engine_config
        with patch.dict(os.environ, {}, clear=True), patch('yggdrasil.service.URL', 'http://127.0.0.1:43210'):
            self.assertEqual(engine_config().url, 'http://127.0.0.1:43210')
            with patch.dict(os.environ, {'YGG_ENGINE_URL': 'http://127.0.0.1:44321/'}):
                self.assertEqual(engine_config().url, 'http://127.0.0.1:44321')

    def test_single_dash_help_alias_preserves_cli(self):
        from yggdrasil import cli
        with patch('sys.argv', ['ygg', '-help']), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli._run(), 0)
        self.assertIn('ygg seed', out.getvalue())
        self.assertIn('ygg config', out.getvalue())

    def test_restart_requests_shutdown_only_of_authenticated_workspace(self):
        from yggdrasil.ygg_workspace_launch import restart_workspace
        from unittest.mock import Mock
        reply=Mock()
        reply.__enter__=Mock(return_value=reply)
        reply.__exit__=Mock(return_value=False)
        reply.read.return_value=b'{"ok":true}'
        with patch('yggdrasil.ygg_workspace_launch._launch_info',return_value={'ticket':'one-time','pid':12345}), patch('urllib.request.OpenerDirector.open',return_value=reply) as send, patch('os.kill') as kill:
            restart_workspace(42070,'private-test-key')
        self.assertTrue(send.call_args.args[0].full_url.endswith('/_shutdown'))
        kill.assert_not_called()

    def test_restart_ignores_unauthenticated_server(self):
        from yggdrasil.ygg_workspace_launch import restart_workspace
        with patch('yggdrasil.ygg_workspace_launch._launch_info',return_value=None), patch('os.kill') as kill:
            restart_workspace(42070,'private-test-key')
        kill.assert_not_called()

    def test_restart_never_kills_when_running_job_blocks_shutdown(self):
        import urllib.error
        from yggdrasil.ygg_workspace_launch import restart_workspace
        error = urllib.error.HTTPError('http://localhost', 409, 'Busy', {}, None)
        with patch('yggdrasil.ygg_workspace_launch._launch_info', return_value={'pid':12345}), patch('urllib.request.OpenerDirector.open', side_effect=error), patch('os.kill') as kill:
            with self.assertRaisesRegex(RuntimeError, 'команду'):
                restart_workspace(42070, 'private-test-key')
        kill.assert_not_called()

    def test_restart_old_release_uses_only_authenticated_pid(self):
        import urllib.error
        import signal
        from yggdrasil.ygg_workspace_launch import restart_workspace
        error = urllib.error.HTTPError('http://localhost', 404, 'Not Found', {}, None)
        with patch('yggdrasil.ygg_workspace_launch._launch_info', return_value={'pid':12345}) as info, patch('urllib.request.OpenerDirector.open', side_effect=error), patch('os.kill') as kill:
            self.assertTrue(restart_workspace(42070, 'private-test-key'))
        info.assert_called_once_with(42070, 'private-test-key', check_identity=False)
        kill.assert_called_once_with(12345, signal.SIGTERM)

    @unittest.skipIf(os.name == 'nt', 'POSIX TIME_WAIT reuse semantics')
    def test_launch_reuses_port_after_server_closed_connection(self):
        import socket
        from yggdrasil.ygg_workspace_launch import launch, _wait_for_shutdown
        # Force server-side TIME_WAIT: the accepted connection closes before the client.
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as listener:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind(('127.0.0.1', 0))
                listener.listen()
                port = listener.getsockname()[1]
                with socket.create_connection(('127.0.0.1', port)) as client:
                    accepted, _ = listener.accept()
                    accepted.close()
                    self.assertEqual(client.recv(1), b'')
            _wait_for_shutdown(port)
            with patch('yggdrasil.ygg_workspace_launch._ticket', side_effect=[None, 'new-ticket']), patch('subprocess.Popen') as spawn:
                url = launch(Path(tmp), port, open_browser=False, ensure_engine=False)
            spawn.assert_called_once()
            self.assertIn('#ticket=new-ticket', url)
