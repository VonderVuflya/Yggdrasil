"""Real HTTP boundary: engine -> Workspace -> persistent scoped chat."""
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from yggdrasil.ygg_memory_server import Handler, MemoryStore
from yggdrasil.ygg_workspace import EngineQuery, WorkspaceServer


class WorkspaceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        home = Path(self.tmp.name)
        self.store = MemoryStore(str(home / 'memory.sqlite'))
        for project in ('A', 'B'):
            self.store.add(content=f'needle: decision in {project}', user_id='alice',
                namespace='personal', scope='project', metadata={'project': project, 'type': 'decision'})
        handler = type('TestEngineHandler', (Handler,), {'store': self.store, 'token': 'test-only-token'})
        self.engine = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        query = EngineQuery(f'http://127.0.0.1:{self.engine.server_port}', 'test-only-token', 'alice', 'personal')
        self.workspace = WorkspaceServer(('127.0.0.1', 0), home=home, query=query,
                                         control='test-control', user_id='alice', namespace='personal')
        self.threads = []
        for server in (self.engine, self.workspace):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.threads.append(thread)
        ticket = self.workspace.issue_ticket()
        self.cookie = ''
        _, headers, _ = self.request('/api/session', {'ticket': ticket})
        self.cookie = headers['Set-Cookie'].split(';')[0]

    def tearDown(self):
        for server in (self.workspace, self.engine):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join()
        if self.workspace._chat:
            self.workspace._chat._db.close()
        self.store._conn.close()
        self.tmp.cleanup()

    def request(self, path, body=None, method=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.workspace.server_port, timeout=5)
        conn.request(method or ('GET' if body is None else 'POST'), path,
                     None if body is None else json.dumps(body),
                     {'Cookie': self.cookie, 'X-Ygg-Request': '1', 'Content-Type': 'application/json'})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read().decode()
        conn.close()
        return result

    def test_real_engine_projects_and_identity_override_ignored(self):
        status, _, text = self.request('/api/projects')
        self.assertEqual(status, 200)
        self.assertEqual({r['name'] for r in json.loads(text)['projects']}, {'A', 'B'})
        status, _, text = self.request('/api/memories', {'project': 'A', 'user_id': 'bob'})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(text)['items'][0]['project'], 'A')

    def test_project_chat_sources_are_scoped_and_global_includes_both(self):
        for project, expected in [('A', {'A'}), (None, {'A', 'B'})]:
            _, _, text = self.request('/api/chats', {'project': project})
            chat = json.loads(text)
            status, _, stream = self.request('/api/chats/' + chat['id'] + '/messages',
                                             {'content': 'needle', 'project': 'B'})
            self.assertEqual(status, 200)
            events = [json.loads(line) for line in stream.splitlines()]
            self.assertEqual({r['project'] for r in events[0]['sources']}, expected)
            self.assertEqual(events[-1]['message']['status'], 'search_only')
            _, _, saved = self.request('/api/chats/' + chat['id'])
            self.assertEqual(json.loads(saved)['chat']['project'], project)
            self.assertEqual(len(json.loads(saved)['messages']), 2)

    def test_attachment_rejects_other_project(self):
        _, _, text = self.request('/api/memories', {'project': 'B'})
        ident = json.loads(text)['items'][0]['id']
        status, _, _ = self.request('/api/chats', {'project': 'A', 'memory_id': ident})
        self.assertEqual(status, 404)

    def test_stream_bad_chat_and_empty_question_are_http_errors(self):
        self.assertEqual(self.request('/api/chats/missing/messages', {'content': 'needle'})[0], 404)
        _, _, text = self.request('/api/chats', {'project': 'A'})
        ident = json.loads(text)['id']
        self.assertEqual(self.request(f'/api/chats/{ident}/messages', {'content': ''})[0], 400)
