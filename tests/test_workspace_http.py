import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path


class WorkspaceHTTPTests(unittest.TestCase):
    def setUp(self):
        from yggdrasil.ygg_workspace import WorkspaceServer
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        static = root / 'static'
        static.mkdir()
        (static / 'index.html').write_text('<html>workspace</html>')
        (root / 'private.txt').write_text('private secret')
        self.server = WorkspaceServer(('127.0.0.1', 0), home=root, static=static,
                                      query=lambda body: {'projects': []}, control='control-secret')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.cookie = ''

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, body=None, headers=None, method=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        hdrs = {'Content-Type': 'application/json', 'X-Ygg-Request': '1'}
        if self.cookie:
            hdrs['Cookie'] = self.cookie
        hdrs.update(headers or {})
        conn.request(method or ('POST' if body is not None else 'GET'), path,
                     body=json.dumps(body) if body is not None else None, headers=hdrs)
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read().decode()
        conn.close()
        return result

    def login(self):
        status, _, text = self.request('/_launch', {}, {'Authorization': 'Bearer control-secret'})
        self.assertEqual(status, 200)
        ticket = json.loads(text)['ticket']
        status, headers, _ = self.request('/api/session', {'ticket': ticket})
        self.assertEqual(status, 200)
        self.cookie = headers['Set-Cookie'].split(';')[0]
        return ticket, headers

    def test_session_one_time_and_private_api_requires_cookie(self):
        self.assertEqual(self.request('/api/projects')[0], 401)
        ticket, headers = self.login()
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        self.assertEqual(self.request('/api/session', {'ticket': ticket})[0], 401)
        self.assertEqual(json.loads(self.request('/api/projects')[2]), {'projects': []})

    def test_expired_ticket_rejected(self):
        ticket = self.server.issue_ticket()
        self.server.tickets[ticket] = 0
        self.assertEqual(self.request('/api/session', {'ticket': ticket})[0], 401)

    def test_host_origin_and_csrf_rejected(self):
        self.login()
        self.assertEqual(self.request('/api/projects', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('/api/projects', headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('/api/memories', {'project': None}, {'X-Ygg-Request': ''})[0], 403)
        self.assertEqual(self.request('/_launch', {}, {'Authorization': 'Bearer control-secret', 'Origin': self.origin})[0], 403)
        self.assertEqual(self.request('/_launch', {})[0], 401)

    def test_static_assets_and_spa_cannot_traverse_or_expose_config(self):
        self.assertEqual(self.request('/projects/test')[0], 200)
        self.assertEqual(self.request('/project?project=A&tab=chat')[0], 200)
        status, headers, _ = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        for url in ('/../private.txt', '/%2e%2e/private.txt', '/api/unknown', '/missing.js'):
            status, _, text = self.request(url)
            self.assertGreaterEqual(status, 400)
            self.assertNotIn('private secret', text)

    def test_invalid_body_returns_400(self):
        self.login()
        self.assertEqual(self.request('/api/memories', ['bad'])[0], 400)
        self.assertEqual(self.request('/api/memories', {'project': None}, {'Content-Length': '2000000'})[0], 413)

    def test_two_ports_keep_independent_browser_sessions(self):
        from yggdrasil.ygg_workspace import WorkspaceServer
        self.login()
        first_cookie = self.cookie
        second = WorkspaceServer(('127.0.0.1', 0), home=Path(self.tmp.name),
                                 query=lambda b: {'projects': []}, control='control-secret')
        thread = threading.Thread(target=second.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection('127.0.0.1', second.server_port, timeout=3)
            conn.request('POST', '/api/session', json.dumps({'ticket': second.issue_ticket()}),
                         {'Content-Type': 'application/json', 'X-Ygg-Request': '1'})
            response = conn.getresponse()
            new_cookie = response.getheader('Set-Cookie').split(';')[0]
            response.read()
            conn.close()
            cookies = {c.split('=')[0]: c for c in (first_cookie, new_cookie)}
            self.cookie = '; '.join(cookies.values())
            self.assertEqual(self.request('/api/projects')[0], 200)
            conn = http.client.HTTPConnection('127.0.0.1', second.server_port, timeout=3)
            conn.request('GET', '/api/projects', headers={'Cookie': self.cookie})
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            conn.close()
        finally:
            second.shutdown()
            second.server_close()
            thread.join()
