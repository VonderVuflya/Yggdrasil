"""A missing model can be explicitly replaced in the preflight wizard."""
import contextlib
import io
import unittest
from unittest.mock import patch

from yggdrasil import ygg_seed as s
from yggdrasil import ygg_preflight as p
from yggdrasil import ygg_prompt as prompt


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.inv = p.ModelInventory('http://studio', 'openai', ('qwen:4b', 'qwen:8b', 'text-embedding-bge-m3'))
        self.settings = {'embed_model': '', 'distill_api_key': '', 'embed_url': 'http://studio/v1',
                         'embed_backend': 'openai', 'embed_api_key': ''}
        self.stack.enter_context(patch.object(s, '_ping_endpoint', return_value=self.inv))
        self.stack.enter_context(patch.object(s, 'OLLAMA_URL', 'http://studio'))
        self.stack.enter_context(patch.object(s._cfg, 'resolve', side_effect=lambda k: self.settings[k]))
        self.stack.enter_context(patch.object(s._cfg, 'source', return_value='config'))
        self.write = self.stack.enter_context(patch.object(s._cfg, 'set_value'))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

    def test_selection_updates_only_bg_model_and_returns_it_for_this_run(self):
        with patch.object(prompt, 'interactive', return_value=True), \
                patch.object(prompt, 'select', return_value='qwen:8b') as select:
            chosen = s._ensure_endpoint('missing')
        self.assertEqual(chosen, 'qwen:8b')
        self.write.assert_called_once_with('bg_model', 'qwen:8b')
        options = select.call_args.args[1]
        self.assertIn('qwen:4b', [o.value for o in options])
        self.assertNotIn('text-embedding-bge-m3', [o.value for o in options])

    def test_noninteractive_does_not_prompt_or_mutate_config(self):
        with patch.object(prompt, 'interactive', return_value=False), \
                patch.object(prompt, 'select') as select:
            with self.assertRaises(s._EndpointUnavailable):
                s._ensure_endpoint('missing')
        select.assert_not_called()
        self.write.assert_not_called()

    def test_cancel_and_keyboard_interrupt_preserve_configuration(self):
        for result in (prompt.BACK, KeyboardInterrupt()):
            with self.subTest(result=repr(result)), patch.object(prompt, 'interactive', return_value=True), \
                    patch.object(prompt, 'select', **({'side_effect': result} if isinstance(result, BaseException)
                                                    else {'return_value': result})):
                with self.assertRaises(s._EndpointUnavailable):
                    s._ensure_endpoint('missing')
        self.write.assert_not_called()

    def test_only_embedding_models_do_not_become_generation_choices(self):
        inv = p.ModelInventory('http://studio', 'openai', ('text-embedding-bge-m3',))
        with patch.object(s, '_ping_endpoint', return_value=inv), \
                patch.object(prompt, 'interactive', return_value=True), patch.object(prompt, 'select') as select:
            with self.assertRaises(s._EndpointUnavailable):
                s._ensure_endpoint('missing')
        select.assert_not_called()
        self.write.assert_not_called()

    def test_embedding_selection_saves_and_requires_daemon_redeploy(self):
        self.settings['embed_model'] = 'missing-embed'
        with patch.object(prompt, 'interactive', return_value=True), \
                patch.object(prompt, 'select', return_value='text-embedding-bge-m3'):
            with self.assertRaisesRegex(s._EndpointUnavailable, 'ygg redeploy'):
                s._ensure_endpoint('qwen:4b')
        self.write.assert_called_once_with('embed_model', 'text-embedding-bge-m3')

    def test_invalid_choice_is_not_persisted(self):
        with patch.object(prompt, 'interactive', return_value=True), \
                patch.object(prompt, 'select', return_value='not-advertised'):
            with self.assertRaises(s._EndpointUnavailable):
                s._ensure_endpoint('missing')
        self.write.assert_not_called()

    def test_config_write_failure_is_actionable_and_stops(self):
        self.write.side_effect = PermissionError('read only')
        with patch.object(prompt, 'interactive', return_value=True), \
                patch.object(prompt, 'select', return_value='qwen:4b'):
            with self.assertRaisesRegex(s._EndpointUnavailable, 'save.*bg_model'):
                s._ensure_endpoint('missing')

    def test_environment_override_is_explained(self):
        out = io.StringIO()
        with patch.object(s._cfg, 'source', return_value='env:YGG_BG_MODEL'), \
                patch.object(prompt, 'interactive', return_value=True), \
                patch.object(prompt, 'select', return_value='qwen:4b'), contextlib.redirect_stdout(out):
            self.assertEqual(s._ensure_endpoint('missing'), 'qwen:4b')
        self.assertIn('YGG_BG_MODEL', out.getvalue())

    def test_advertised_model_returns_without_configuration_changes(self):
        self.assertEqual(s._ensure_endpoint('qwen:4b'), 'qwen:4b')
        self.write.assert_not_called()

    def test_seed_and_distill_generate_with_selected_model(self):
        import argparse
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'chat.md'
            f.write_text('A work log')
            args = argparse.Namespace(model='missing', user_id='u', namespace='n', yes=True,
                                      dry_run=False, source=str(f), project='p')
            for command in (s.seed, s.distill_cmd):
                with self.subTest(command=command.__name__), \
                        patch.object(s, 'discover', return_value=[
                            {'kind': 'obsidian', 'project': 'p', 'path': d, 'bytes': 10}]), \
                        patch.object(s, '_load_seed_state', return_value={}), \
                        patch.object(s, '_save_seed_state'), \
                        patch.object(s, '_release_model'), \
                        patch.object(s, '_scale_hint', return_value=None), \
                        patch.object(prompt, 'interactive', return_value=True), \
                        patch.object(prompt, 'select', return_value='qwen:8b'), \
                        patch.object(s, '_ollama_generate', return_value='{"lessons":[]}') as generate:
                    self.assertEqual(command(args), 0)
                self.assertEqual(generate.call_args.args[0], 'qwen:8b')

    def test_server_kind_metadata_beats_name_heuristics(self):
        # A misleading ID is an embedding model according to the server.
        inv = p.ModelInventory('http://studio', 'openai', ('custom-name',), 'all', ('embed',))
        with patch.object(s, '_ping_endpoint', return_value=inv), \
                patch.object(prompt, 'interactive', return_value=True), patch.object(prompt, 'select') as select:
            with self.assertRaises(s._EndpointUnavailable):
                s._ensure_endpoint('missing')
        select.assert_not_called()
        self.write.assert_not_called()

    def test_embedding_name_is_not_overridden_by_ollama_architecture_family(self):
        body = b'{"models":[{"name":"qwen3-embedding:latest","details":{"family":"qwen3"}},{"name":"qwen:4b","details":{"family":"qwen3"}}]}'
        with patch.object(p, 'check_connection'), patch.object(p.urllib.request, 'urlopen',
                return_value=io.BytesIO(body)):
            inv = p.probe_endpoint('http://studio', backend='ollama')
        with patch.object(s, '_ping_endpoint', return_value=inv), \
                patch.object(prompt, 'interactive', return_value=True), \
                patch.object(prompt, 'select', return_value='qwen:4b') as select:
            self.assertEqual(s._ensure_endpoint('missing'), 'qwen:4b')
        self.assertNotIn('qwen3-embedding:latest', [o.value for o in select.call_args.args[1]])

    def test_untyped_openai_inventory_uses_existing_embedding_name_hints(self):
        body = b'{"data":[{"id":"text-embedding-bge-m3"},{"id":"qwen:4b"}]}'
        with patch.object(p, 'check_connection'), patch.object(p.urllib.request, 'urlopen',
                return_value=io.BytesIO(body)):
            inv = p.probe_endpoint('http://studio/v1', backend='openai')
        self.assertEqual(inv.kinds, ('embed', 'llm'))


class RecoveryPtyTest(unittest.TestCase):
    @unittest.skipIf(__import__('os').name == 'nt', 'POSIX PTY input')
    def test_real_arrow_and_enter_save_only_selected_model_and_cancel_preserves_config(self):
        import json
        import os
        import select
        import subprocess
        import sys
        import tempfile
        import time
        import pty
        from pathlib import Path
        root = str(Path(__file__).resolve().parents[1])
        for keys, expected in (([b'\x1b[B', b'\x1b[B', b'\r'], 'qwen:8b'), ([b'\x03'], 'missing')):
            with self.subTest(keys=keys), tempfile.TemporaryDirectory() as d:
                config = Path(d) / 'config.json'
                config.write_text(json.dumps({'bg_model': 'missing', 'embed_model': '', 'unrelated': 'keep'}))
                code = f'''
import sys
sys.path.insert(0, {root!r})
from pathlib import Path
from yggdrasil import ygg_seed as s, ygg_preflight as p
s._cfg.YGG_HOME = Path({d!r})
s._cfg.CONFIG = Path({str(config)!r})
s._ping_endpoint = lambda: p.ModelInventory('http://fixture', 'openai', ('qwen:4b', 'qwen:8b', 'text-embedding-bge-m3'))
try:
    result = s._ensure_endpoint('missing')
    print('RESULT=' + result)
except s._EndpointUnavailable:
    print('RESULT=cancelled')
'''
                env = {k: v for k, v in os.environ.items()
                       if not k.startswith('YGG_') and k != 'NO_COLOR'}
                master, slave = pty.openpty()
                process = subprocess.Popen([sys.executable, '-c', code], stdin=slave,
                                           stdout=slave, stderr=slave, env=env)
                os.close(slave)
                output = bytearray()

                def pump(seconds):
                    deadline = time.monotonic() + seconds
                    while time.monotonic() < deadline:
                        if select.select([master], [], [], 0.02)[0]:
                            try:
                                chunk = os.read(master, 65536)
                            except OSError:
                                break
                            if not chunk:
                                break
                            output.extend(chunk)

                try:
                    deadline = time.monotonic() + 5
                    while b'Choose a replacement' not in output and time.monotonic() < deadline:
                        pump(0.05)
                    self.assertIn(b'Choose a replacement', output)
                    pump(0.1)  # menu has rendered and entered raw mode
                    for key in keys:
                        os.write(master, key)
                        pump(0.15)
                    deadline = time.monotonic() + 5
                    while process.poll() is None and time.monotonic() < deadline:
                        pump(0.05)
                    self.assertEqual(process.poll(), 0, output.decode(errors='replace'))
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=5)
                    os.close(master)
                saved = json.loads(config.read_text())
                self.assertEqual(saved, {'bg_model': expected, 'embed_model': '', 'unrelated': 'keep'})
                self.assertIn(b'available', output)
                self.assertIn(b'\x1b[32mavailable', output)  # visible green inventory badges
