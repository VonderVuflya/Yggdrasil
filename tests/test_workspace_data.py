import tempfile
import unittest
from pathlib import Path
from yggdrasil.ygg_memory_server import MemoryStore


class WorkspaceDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MemoryStore(str(Path(self.tmp.name) / 'memory.sqlite'))

    def tearDown(self):
        self.store._conn.close()
        self.tmp.cleanup()

    def add(self, text='needle', project='A', user='alice', namespace='personal', **metadata):
        return self.store.add(content=text, user_id=user, namespace=namespace,
                              scope='project', metadata={'project': project, **metadata})

    def query(self, op, **params):
        from yggdrasil.ygg_workspace_data import workspace_query
        return workspace_query(self.store, {'op': op, 'user_id': 'alice',
                                            'namespace': 'personal', **params})

    def test_aggregates_all_records_and_pages_without_leaking_identity(self):
        for i in range(1003):
            self.add(str(i), type='decision')
        self.add(project='B')
        self.add(project='secret', user='bob')
        self.add(project='hidden', namespace='other')
        projects = self.query('projects')['projects']
        self.assertEqual({p['name']: p['count'] for p in projects}, {'A': 1003, 'B': 1})
        page = self.query('memories', project='A', offset=1000, limit=20)
        self.assertEqual(page['total'], 1003)
        self.assertEqual(len(page['items']), 3)
        self.assertEqual(page['items'][0]['project'], 'A')

    def test_empty_project_and_search_stay_scoped(self):
        orphan = self.add(project='')
        self.add(project='B')
        self.assertEqual([r['id'] for r in self.query('search', project='', query='needle')['items']], [orphan['id']])
        self.assertEqual(len(self.query('search', project=None, query='needle')['items']), 2)
        with self.assertRaises(ValueError):
            self.query('memories')

    def test_memory_id_cannot_escape_project_or_identity(self):
        other = self.add(project='B')
        foreign = self.add(user='bob')
        for ident in (other['id'], foreign['id']):
            with self.assertRaises(KeyError):
                self.query('memory', project='A', id=ident)

    def test_archive_filter_and_literal_query(self):
        record = self.add('100% complete', source='file.md')
        self.add('1000 complete')
        self.assertEqual(self.query('memories', project='A', query='%')['total'], 1)
        self.store.update(record['id'], data=None, metadata_patch=None, archived=True)
        self.assertEqual(self.query('memories', project='A', archived=True)['items'][0]['id'], record['id'])
        self.assertEqual(self.query('projects')['projects'][0]['archived_count'], 1)
        self.assertEqual(self.query('sources', project='A')['sources'], [{'name': '', 'count': 1}])

    def test_graph_edges_are_real_and_external_content_hidden(self):
        a = self.add('visible')
        b = self.add('private other project', project='B')
        c = self.add('foreign', user='bob')
        self.store.relate(from_id=a['id'], to_id=b['id'], rel_type='SOLVES', user_id='alice')
        self.store.relate(from_id=a['id'], to_id=c['id'], rel_type='SOLVES', user_id='alice')
        graph = self.query('graph', project='A')
        self.assertEqual([n['id'] for n in graph['nodes']], [a['id']])
        self.assertEqual(len(graph['edges']), 1)
        self.assertTrue(graph['edges'][0]['external'])
        self.assertEqual(graph['edges'][0]['other_project'], 'B')
        self.assertNotIn('private other project', str(graph))
        self.assertNotIn(c['id'], str(graph))

    def test_limits_and_bad_arguments(self):
        for i in range(305):
            self.add(str(i))
        graph = self.query('graph', project='A')
        self.assertEqual(len(graph['nodes']), 300)
        self.assertEqual(graph['total'], 305)
        self.assertTrue(graph['truncated'])
        for args in ({'offset': -1}, {'limit': 0}, {'project': []}, {'archived': 'false'}):
            with self.assertRaises(ValueError):
                self.query('memories', **({'project': 'A'} | args))

    def test_default_type_and_absent_source_filter_match_public_values(self):
        default = self.add('untyped')
        self.add('typed', type='decision', source='notes.md')
        self.assertEqual([m['id'] for m in self.query('memories', project='A', type='memory')['items']], [default['id']])
        self.assertEqual([m['id'] for m in self.query('memories', project='A', source='')['items']], [default['id']])
        self.assertEqual(self.query('memories', project='A')['total'], 2)
