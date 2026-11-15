"""Preflight must reject bad endpoints/models before any transcript is processed."""
import argparse
import contextlib
import io
import json
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from yggdrasil import ygg_seed as s
from yggdrasil import ygg_preflight as p


class ProbeTest(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def test_dns_failure_stops_before_http(self):
        with patch.object(p.socket, 'getaddrinfo', side_effect=socket.gaierror('unknown host')), \
                patch.object(p.urllib.request, 'urlopen') as http:
            with self.assertRaisesRegex(p.PreflightError, 'DNS'):
                p.probe_endpoint('http://missing.invalid:1234')
        http.assert_not_called()

    def test_refused_and_timeout_have_distinct_connection_errors(self):
        for error, message in ((ConnectionRefusedError(), 'refused'),
                               (TimeoutError(), 'firewall')):
            with self.subTest(error=type(error).__name__), \
                    patch.object(p.socket, 'getaddrinfo', return_value=[
                        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.1', 1234))]), \
                    patch.object(p.socket, 'socket') as sock, \
                    patch.object(p.urllib.request, 'urlopen') as http:
                sock.return_value.__enter__.return_value.connect.side_effect = error
                with self.assertRaisesRegex(p.PreflightError, message):
                    p.probe_endpoint('http://192.0.2.1:1234')
                http.assert_not_called()

    def test_model_list_uses_bearer_key_and_preserves_ids(self):
        with patch.object(p, 'check_connection'), patch.object(p.urllib.request, 'urlopen',
                return_value=io.BytesIO(b'{"data":[{"id":"qwen/model"}]}')) as http:
            inventory = p.probe_endpoint('http://studio:1234/v1', api_key='test-key', backend='openai')
        req = http.call_args.args[0]
        self.assertEqual(req.full_url, 'http://studio:1234/v1/models')
        self.assertEqual(req.get_header('Authorization'), 'Bearer test-key')
        self.assertEqual(inventory.models, ('qwen/model',))

    def test_openai_fallback_only_on_unsupported_route(self):
        missing = urllib.error.HTTPError('http://host/v1/models', 404, 'missing', {}, None)
        with patch.object(p, 'check_connection'), patch.object(p.urllib.request, 'urlopen',
                side_effect=[missing, io.BytesIO(b'{"data":[{"id":"qwen:latest"}]}')]) as http:
            inv = p.probe_endpoint('http://host:11434')
        self.assertEqual(inv.backend, 'openai')
        self.assertEqual(http.call_args.args[0].full_url, 'http://host:11434/v1/models')
        inv = p.ModelInventory('http://host', 'ollama', ('qwen:latest',))
        p.require_model(inv, 'qwen', 'bg_model')
        with self.assertRaisesRegex(p.PreflightError, 'qwen:4b'):
            p.require_model(inv, 'qwen:4b', 'bg_model')

    def test_api_errors_name_the_stage_and_do_not_fallback(self):
        for code in (401, 403, 500):
            with self.subTest(code=code), patch.object(p, 'check_connection'), \
                    patch.object(p.urllib.request, 'urlopen', side_effect=
                        urllib.error.HTTPError('http://host', code, 'error', {}, None)) as http:
                with self.assertRaisesRegex(p.PreflightError, str(code)):
                    p.probe_endpoint('http://host', backend='openai')
                self.assertEqual(http.call_count, 1)

    def test_invalid_inventory_is_not_a_healthy_model_api(self):
        for data in ({'status': 'ok'}, {'data': 'bad'}, {'data': [{}]}, [],
                     {'error': 'No access'}, {'data': [], 'error': 'No access'},
                     {'data': [{'id': 'x'}, {'id': 7}]}):
            with self.subTest(data=data), patch.object(p, 'check_connection'), \
                    patch.object(p.urllib.request, 'urlopen', return_value=
                        io.BytesIO(json.dumps(data).encode())):
                with self.assertRaises(p.PreflightError):
                    p.probe_endpoint('http://host', backend='openai')

    def test_missing_model_lists_available_ids_without_fuzzy_match(self):
        inv = p.ModelInventory('http://studio', 'openai', ('qwen:4b', 'embed'))
        with self.assertRaisesRegex(p.PreflightError, 'bg_model.*qwen:8b') as error:
            p.require_model(inv, 'qwen:8b', 'bg_model')
        self.assertIn('qwen:4b', str(error.exception))
        self.assertIn('http://studio', str(error.exception))


class RequiredModelsTest(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        settings = {'embed_model': 'embed', 'embed_url': 'http://embed:1234/v1',
                    'embed_api_key': 'embed-key', 'embed_backend': 'openai',
                    'distill_api_key': 'distill-key'}
        self.stack.enter_context(patch.object(s._cfg, 'resolve', side_effect=lambda k: settings[k]))
        self.stack.enter_context(patch.object(s, 'OLLAMA_URL', 'http://studio:1234'))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.inv = p.ModelInventory('http://studio:1234', 'openai', ('chosen',))
        self.stack.enter_context(patch.object(s, '_ping_endpoint', return_value=self.inv))

    def test_checks_embedding_at_its_own_endpoint_with_its_own_key(self):
        embed = p.ModelInventory('http://embed:1234', 'openai', ('embed',))
        with patch.object(p, 'probe_endpoint', return_value=embed) as probe:
            s._ensure_endpoint('chosen')
        self.assertEqual(probe.call_args.args[0], 'http://embed:1234/v1')
        self.assertEqual(probe.call_args.kwargs['api_key'], 'embed-key')
        self.assertEqual(probe.call_args.kwargs['backend'], 'openai')

    def test_missing_distill_model_never_starts_local_server(self):
        with patch.object(s, '_installed_model_servers') as start:
            with self.assertRaisesRegex(s._EndpointUnavailable, 'bg_model.*missing'):
                s._ensure_endpoint('missing')
        start.assert_not_called()

    def test_disabled_embedding_model_is_skipped(self):
        with patch.object(s._cfg, 'resolve', return_value=''), \
                patch.object(p, 'probe_endpoint') as probe:
            s._ensure_endpoint('chosen')
        probe.assert_not_called()

    def test_shared_endpoint_and_key_reuses_inventory(self):
        settings = {'embed_model': 'chosen', 'embed_url': 'http://studio:1234/v1',
                    'embed_api_key': 'same', 'embed_backend': 'openai', 'distill_api_key': 'same'}
        with patch.object(s._cfg, 'resolve', side_effect=lambda k: settings[k]), \
                patch.object(p, 'probe_endpoint') as probe:
            s._ensure_endpoint('chosen')
        probe.assert_not_called()

    def test_shared_endpoint_with_different_key_does_not_reuse_inventory(self):
        settings = {'embed_model': 'chosen', 'embed_url': 'http://studio:1234/v1',
                    'embed_api_key': 'other', 'embed_backend': 'openai', 'distill_api_key': 'same'}
        with patch.object(s._cfg, 'resolve', side_effect=lambda k: settings[k]), \
                patch.object(p, 'probe_endpoint', return_value=self.inv) as probe:
            s._ensure_endpoint('chosen')
        probe.assert_called_once()


class BeforeGenerationTest(unittest.TestCase):
    def test_seed_and_distill_stop_before_extracting_or_writing(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'chat.md'
            f.write_text('Conversation')
            args = argparse.Namespace(model='override', user_id='u', namespace='n',
                                      yes=True, dry_run=False, source=str(f), project='p')
            src = {'kind': 'obsidian', 'project': 'p', 'path': d, 'bytes': 12}
            for command in (s.seed, s.distill_cmd):
                state = {}
                with self.subTest(command=command.__name__), \
                        patch.object(s, 'discover', return_value=[src]), \
                        patch.object(s, '_load_seed_state', return_value=state), \
                        patch.object(s, '_save_seed_state'), \
                        patch.object(s, '_ensure_endpoint', side_effect=s._EndpointUnavailable('missing model')) as check, \
                        patch.object(s, '_extract_text') as extract, \
                        patch.object(s, '_ollama_generate') as generate, \
                        patch.object(s._ygg, 'write_memory') as write, \
                        contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(command(args), 1)
                check.assert_called_once_with('override')
                extract.assert_not_called()
                generate.assert_not_called()
                write.assert_not_called()
                self.assertEqual(state, {})


class HttpPreflightTest(unittest.TestCase):
    def test_missing_model_stops_real_http_preflight_before_any_post(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(('GET', self.path))
                if self.path == '/api/tags':
                    self.send_error(404)
                    return
                body = b'{"data":[{"id":"different-model"}]}'
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                requests.append(('POST', self.path))
                self.send_error(500)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'chat.md').write_text('Conversation')
            src = {'kind': 'obsidian', 'project': 'p', 'path': d, 'bytes': 12}
            args = argparse.Namespace(model='required-model', user_id='u', namespace='n',
                                      yes=True, dry_run=False)
            state = {}
            err = io.StringIO()
            with patch.object(s, 'OLLAMA_URL', f'http://127.0.0.1:{server.server_port}'), \
                    patch.object(s, 'discover', return_value=[src]), \
                    patch.object(s, '_load_seed_state', return_value=state), \
                    patch.object(s, '_save_seed_state'), \
                    patch.object(s._cfg, 'resolve', return_value=''), \
                    patch.object(s, '_extract_text') as extract, \
                    patch.object(s._ygg, 'write_memory') as write, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                self.assertEqual(s.seed(args), 1)
            self.assertIn('required-model', err.getvalue())
            self.assertIn('different-model', err.getvalue())
            self.assertEqual(requests, [('GET', '/api/tags'), ('GET', '/v1/models')])
            self.assertEqual(state, {})
            extract.assert_not_called()
            write.assert_not_called()


class CompatibilityTest(unittest.TestCase):
    def test_proxied_endpoint_checks_the_proxy_connection(self):
        with patch.object(p.urllib.request, 'getproxies', return_value={
                'https': 'http://user:secret@proxy.example:8080'}), \
                patch.object(p.urllib.request, 'proxy_bypass', return_value=False), \
                patch.object(p.socket, 'getaddrinfo', return_value=[
                    (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.1', 8080))]) as resolve, \
                patch.object(p.socket, 'socket'), contextlib.redirect_stdout(io.StringIO()) as output:
            p.check_connection('https://only-via-proxy.invalid/v1')
        resolve.assert_called_once_with('proxy.example', 8080, type=socket.SOCK_STREAM)
        self.assertNotIn('secret', output.getvalue())

    def test_backend_aliases_and_full_embedding_endpoint(self):
        for backend in ('openai-compatible', 'llamacpp', 'llama.cpp', ' OpenAI '):
            with self.subTest(backend=backend), patch.object(p, 'check_connection'), \
                    patch.object(p.urllib.request, 'urlopen', return_value=
                        io.BytesIO(b'{"data":[{"id":"embed"}]}')) as http, \
                    contextlib.redirect_stdout(io.StringIO()):
                inv = p.probe_endpoint('https://host/prefix/v1/embeddings', backend=backend)
            self.assertEqual(http.call_args.args[0].full_url, 'https://host/prefix/v1/models')
            self.assertEqual(inv.backend, 'openai')

    def test_requests_identify_the_product_for_bot_filtered_servers(self):
        def response(req, **kwargs):
            if not (req.get_header('User-agent') or '').startswith('yggdrasil'):
                raise urllib.error.HTTPError(req.full_url, 403, 'bot filtered', {}, None)
            return io.BytesIO(b'{"data":[{"id":"model"}]}')
        with patch.object(p, 'check_connection'), \
                patch.object(p.urllib.request, 'urlopen', side_effect=response), \
                contextlib.redirect_stdout(io.StringIO()):
            p.probe_endpoint('https://host/v1', backend='openai')

    def test_openrouter_embedding_catalog_is_separate_from_text_models(self):
        def response(req, **kwargs):
            model = 'embed' if req.full_url.endswith('/embeddings/models') else 'chat'
            return io.BytesIO(json.dumps({'data': [{'id': model}]}).encode())
        for backend in ('openai', 'openrouter'):
            with self.subTest(backend=backend), patch.object(p, 'check_connection'), \
                    patch.object(p.urllib.request, 'urlopen', side_effect=response), \
                    contextlib.redirect_stdout(io.StringIO()):
                inv = p.probe_endpoint('https://openrouter.ai/api/v1', backend=backend,
                                       purpose='embedding')
                p.require_model(inv, 'embed', 'embed_model')

    def test_missing_embedding_model_blocks_seed_before_generation(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'chat.md').write_text('Conversation')
            settings = {'distill_api_key': '', 'embed_model': 'missing-embed',
                        'embed_url': 'http://embed/v1', 'embed_backend': 'openai', 'embed_api_key': ''}
            args = argparse.Namespace(model='chat', user_id='u', namespace='n', yes=True, dry_run=False)
            with patch.object(s, 'discover', return_value=[
                    {'kind': 'obsidian', 'project': 'p', 'path': d, 'bytes': 12}]), \
                    patch.object(s, '_load_seed_state', return_value={}), \
                    patch.object(s, '_save_seed_state'), \
                    patch.object(s, '_ping_endpoint', return_value=p.ModelInventory('http://chat', 'openai', ('chat',))), \
                    patch.object(s._cfg, 'resolve', side_effect=lambda k: settings[k]), \
                    patch.object(p, 'probe_endpoint', return_value=p.ModelInventory('http://embed', 'openai', ('other',))), \
                    patch.object(s, '_ollama_generate') as generate, \
                    patch.object(s._ygg, 'write_memory') as write, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(s.seed(args), 1)
            self.assertIn('missing-embed', err.getvalue())
            generate.assert_not_called()
            write.assert_not_called()

    def test_generation_catalog_is_not_reused_for_openrouter_embeddings(self):
        settings = {'embed_model': 'embed', 'embed_url': 'https://openrouter.ai/api/v1',
                    'embed_api_key': 'same', 'embed_backend': 'openai', 'distill_api_key': 'same'}
        inv = p.ModelInventory('https://openrouter.ai/api', 'openai', ('chat',), 'generation')
        embed = p.ModelInventory('https://openrouter.ai/api', 'openai', ('embed',), 'embedding')
        with patch.object(s, 'OLLAMA_URL', 'https://openrouter.ai/api/v1'), \
                patch.object(s, '_ping_endpoint', return_value=inv), \
                patch.object(s._cfg, 'resolve', side_effect=lambda k: settings[k]), \
                patch.object(p, 'probe_endpoint', return_value=embed) as probe, \
                contextlib.redirect_stdout(io.StringIO()):
            s._ensure_endpoint('chat')
        self.assertEqual(probe.call_args.kwargs['purpose'], 'embedding')

    def test_no_proxy_bypasses_proxy_transport(self):
        with patch.object(p.urllib.request, 'getproxies', return_value={'http': 'http://proxy:8080'}), \
                patch.object(p.urllib.request, 'proxy_bypass', return_value=True), \
                patch.object(p.socket, 'getaddrinfo', return_value=[
                    (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.1', 1234))]) as resolve, \
                patch.object(p.socket, 'socket'), contextlib.redirect_stdout(io.StringIO()):
            p.check_connection('http://studio:1234')
        resolve.assert_called_once_with('studio', 1234, type=socket.SOCK_STREAM)

    def test_no_new_files_does_not_contact_model_server(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'chat.md'
            f.write_text('Conversation')
            state = {str(f): {'mtime': f.stat().st_mtime, 'size': f.stat().st_size}}
            args = argparse.Namespace(model='chat', user_id='u', namespace='n', yes=True, dry_run=False)
            with patch.object(s, 'discover', return_value=[
                    {'kind': 'obsidian', 'project': 'p', 'path': d, 'bytes': 12}]), \
                    patch.object(s, '_load_seed_state', return_value=state), \
                    patch.object(s, '_ensure_endpoint') as check, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(s.seed(args), 0)
            check.assert_not_called()

    def test_force_preflight_failure_preserves_previous_completed_state(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'chat.md').write_text('Conversation')
            args = argparse.Namespace(model='chat', user_id='u', namespace='n', yes=True,
                                      dry_run=False, force=True)
            with patch.object(s, 'discover', return_value=[
                    {'kind': 'obsidian', 'project': 'p', 'path': d, 'bytes': 12}]), \
                    patch.object(s, '_save_seed_state') as save, \
                    patch.object(s, '_ensure_endpoint', side_effect=s._EndpointUnavailable('missing model')), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(s.seed(args), 1)
            save.assert_not_called()
