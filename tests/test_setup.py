"""Tests for ygg_setup: the acceleration-tier / GPU-warning classifier (§1) and
the multilingual-aware model catalog + recommendation (§3).

These are pure/deterministic given a hardware dict, so no Ollama or engine is
touched — we feed synthetic `hw()` dicts and assert the recommendation and the
rendered catalog."""

import builtins
import importlib
import io
import json
import os
import pathlib
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from yggdrasil import ygg_setup as s


def _hw(**over):
    base = {"cpu": "test", "cores": 8, "ram_gb": 16, "arch": "x86_64",
            "apple_silicon": False, "accel": "CPU", "accel_tier": "cpu",
            "accel_warn": "", "gpus": []}
    base.update(over)
    return base


class RecommendTest(unittest.TestCase):
    def test_never_recommends_llama_for_the_upgrade(self):
        # Llama 3.2 has no Russian/Chinese — it must never be the default pick.
        for h in (_hw(apple_silicon=True, accel_tier="metal", ram_gb=32),
                  _hw(accel_tier="cuda", ram_gb=64),
                  _hw(accel_tier="rocm/vulkan", ram_gb=32),
                  _hw(ram_gb=8), _hw(ram_gb=32)):  # CPU-only, big + small RAM
            _, bg = s.recommend(h)
            self.assertNotEqual(bg, "llama3.2:3b")
            self.assertTrue(bg.startswith("qwen2.5"))

    def test_accelerated_16gb_gets_the_3b_upgrade(self):
        self.assertEqual(s.recommend(_hw(apple_silicon=True, accel_tier="metal", ram_gb=16))[1],
                         "qwen2.5:3b")

    def test_cpu_only_stays_on_the_1_5b_sweet_spot(self):
        self.assertEqual(s.recommend(_hw(accel_tier="cpu", ram_gb=32))[1], "qwen2.5:1.5b")


class CatalogTest(unittest.TestCase):
    def _render(self, h):
        buf = io.StringIO()
        with redirect_stdout(buf):
            s.print_catalog(h)
        return buf.getvalue()

    def test_warns_when_gpu_will_not_accelerate(self):
        out = self._render(_hw(accel_warn="You have a GPU (AMD Radeon RX 580) but it will NOT accelerate ..."))
        self.assertIn("⚠", out)
        self.assertIn("RX 580", out)

    def test_llama_entry_flags_no_russian(self):
        out = self._render(_hw())
        # the language column makes the gap explicit right on the llama line
        line = next(l for l in out.splitlines() if "llama3.2:3b" in l)
        self.assertIn("NO Russian", line)

    def test_every_bg_model_carries_a_language_tag(self):
        # the 5th tuple field must be present and rendered for real models
        for name, _size, _desc, _tier, lang in s.BG_MODELS:
            if name != "none":
                self.assertTrue(lang and lang != "—", name)


def _providers_fixture(ollama_installed=False):
    """LM Studio up with models; Ollama and llama.cpp absent. `ollama_installed`
    flips Ollama to installed-but-idle, the state that triggers the start offer."""
    from yggdrasil import ygg_providers as P
    lms = P.Provider("lmstudio", "LM Studio", "http://127.0.0.1:1234", [
        P.Model("text-embedding-nomic-embed-text-v1.5", "embed"),
        P.Model("text-embedding-paraphrase-multilingual-mpnet-base-v2.gguf", "embed"),
        P.Model("qwen2.5-3b-instruct", "llm"),
    ], installed=True)
    ollama = P.Provider("ollama", "Ollama", P.OLLAMA_URL, None, installed=ollama_installed)
    cpp = P.Provider("llamacpp", "llama.cpp", P.LLAMACPP_URL, None, installed=False)
    return [lms, ollama, cpp]


class WizardBase(unittest.TestCase):
    """Drives the wizard through the non-TTY fallback (numbered list + input()) —
    the same path a real `uvx ... ygg install` takes when stdin isn't a terminal.

    Detection and every subprocess are stubbed: these tests assert what lands in
    config.json, and must never touch a real Ollama, LM Studio, or the network.
    """

    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp())
        os.environ["YGG_HOME"] = str(self.home)
        import yggdrasil.ygg_config as C
        self.C = importlib.reload(C)
        importlib.reload(s)
        self.cfg = self.home / "config.json"
        self._real_input = builtins.input
        self.provs = _providers_fixture()
        self._patches = [
            mock.patch.object(s._providers, "detect", lambda timeout=1.5: self.provs),
            # can_pull() shells out to find a binary; pretend both are there so the
            # download rows appear.
            mock.patch.object(s._providers, "lms_bin", lambda: "/fake/lms"),
            mock.patch.object(s._providers, "ollama_bin", lambda: "/fake/ollama"),
            mock.patch.object(s._providers, "start", lambda p, wait=25.0: False),
            # Ollama serves back the tag you pulled; the LM Studio tests that
            # care about id resolution override this.
            mock.patch.object(s._providers, "pull_and_resolve",
                              lambda prov, spec, kind: spec),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        builtins.input = self._real_input
        os.environ.pop("YGG_HOME", None)
        shutil.rmtree(self.home, ignore_errors=True)
        importlib.reload(s)

    def _run(self, *answers, key=None):
        it = iter(answers)
        builtins.input = lambda *a, **k: next(it)
        if key is not None:
            import getpass
            self._real_getpass = getpass.getpass
            getpass.getpass = lambda prompt="": key
        import yggdrasil.service as service
        real = service.install
        service.install = lambda *a, **k: 0
        try:
            with redirect_stdout(io.StringIO()):
                s.wizard()
        finally:
            service.install = real
            if key is not None:
                import getpass
                getpass.getpass = self._real_getpass
        return json.loads(self.cfg.read_text())


# The runtime picker lists live runtimes first, then idle, then missing, then
# the three escape hatches. With the fixture above that is:
LMSTUDIO, OLLAMA, LLAMACPP, CUSTOM, OPENROUTER, NONE = "1", "2", "3", "4", "5", "6"
# The embedding-model picker for LM Studio: catalog order, downloaded first.
EMBED_NOMIC, EMBED_MPNET = "1", "2"
# The distill picker for LM Studio: qwen2.5-3b-instruct is the only one on disk.
LLM_QWEN3B = "1"
NO4 = ("n", "n", "n", "n")     # the four feature confirms
# The wizard names every pending download and asks once before spending the
# disk and the wait; only runs that picked a red row have to answer it.
DL_YES = "y"


class WizardEndpointTest(WizardBase):
    """The whole point of the rework: the user picks a runtime, and we write the
    three settings they used to have to derive by hand."""

    def test_lmstudio_fills_in_both_urls_and_the_backend(self):
        cfg = self._run(LMSTUDIO, EMBED_MPNET, LMSTUDIO, LLM_QWEN3B, *NO4)
        self.assertEqual(cfg["embed_model"],
                         "text-embedding-paraphrase-multilingual-mpnet-base-v2.gguf")
        self.assertEqual(cfg["bg_model"], "qwen2.5-3b-instruct")
        self.assertEqual(cfg["embed_backend"], "openai")
        # embed_url takes the /v1 base, distill_url takes the host root.
        self.assertEqual(cfg["embed_url"], "http://127.0.0.1:1234/v1")
        self.assertEqual(cfg["distill_url"], "http://127.0.0.1:1234")

    def test_the_model_ids_written_are_the_ones_the_server_answers_to(self):
        """Not the catalog's download spec — `nomic-embed-text` 404s."""
        cfg = self._run(LMSTUDIO, EMBED_NOMIC, LMSTUDIO, LLM_QWEN3B, *NO4)
        self.assertEqual(cfg["embed_model"], "text-embedding-nomic-embed-text-v1.5")

    def test_local_ollama_pins_nothing(self):
        cfg = self._run(OLLAMA, "1", OLLAMA, "1", *NO4, DL_YES)
        self.assertNotIn("embed_backend", cfg)   # ollama on 11434 is the default
        self.assertNotIn("embed_url", cfg)
        self.assertNotIn("distill_url", cfg)

    def test_embeddings_and_distillation_can_live_on_different_runtimes(self):
        cfg = self._run(LMSTUDIO, EMBED_MPNET, OLLAMA, "1", *NO4, DL_YES)
        self.assertEqual(cfg["embed_url"], "http://127.0.0.1:1234/v1")
        self.assertNotIn("distill_url", cfg)     # Ollama's default, left implicit

    def test_a_machine_on_the_lan_is_probed_and_both_urls_derived(self):
        from yggdrasil import ygg_providers as P
        remote = [P.Model("text-embedding-bge-m3", "embed"), P.Model("qwen3-4b", "llm")]
        with mock.patch.object(s._providers, "probe_any", lambda url, timeout=1.5: ("openai", remote)):
            cfg = self._run(CUSTOM, "http://192.168.3.150:1234", "1",
                            CUSTOM, "http://192.168.3.150:1234", "1", *NO4)
        self.assertEqual(cfg["embed_backend"], "openai")
        self.assertEqual(cfg["embed_url"], "http://192.168.3.150:1234/v1")
        self.assertEqual(cfg["distill_url"], "http://192.168.3.150:1234")
        self.assertEqual(cfg["embed_model"], "text-embedding-bge-m3")

    def test_a_bare_host_port_gets_a_scheme(self):
        from yggdrasil import ygg_providers as P
        with mock.patch.object(s._providers, "probe_any",
                               lambda url, timeout=1.5: ("ollama", [P.Model("qwen2.5:3b", "llm")])):
            cfg = self._run(NONE, CUSTOM, "box.local:11434", "1", *NO4)
        self.assertEqual(cfg["distill_url"], "http://box.local:11434")

    def test_openrouter_sets_the_hosted_url_and_stores_the_key(self):
        cfg = self._run(OPENROUTER, "nvidia/llama-nemotron-embed-vl-1b-v2:free",
                        NONE, *NO4, key="sk-or-v1-TESTKEY")
        self.assertEqual(cfg["embed_backend"], "openai")
        self.assertEqual(cfg["embed_url"], "https://openrouter.ai/api/v1")
        self.assertNotIn("embed_api_key", cfg)            # never in config.json
        self.assertEqual(self.C.read_secret(self.C.EMBED_KEY_FILE), "sk-or-v1-TESTKEY")
        # ...but not to the half that isn't hosted
        self.assertFalse(self.C.DISTILL_KEY_FILE.exists())

    def test_the_key_follows_whichever_half_is_hosted(self):
        cfg = self._run(LMSTUDIO, EMBED_MPNET,
                        OPENROUTER, "qwen/qwen3-4b:free", *NO4, key="sk-or-v1-TESTKEY")
        self.assertEqual(cfg["embed_url"], "http://127.0.0.1:1234/v1")
        self.assertEqual(cfg["distill_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(self.C.read_secret(self.C.DISTILL_KEY_FILE), "sk-or-v1-TESTKEY")
        self.assertFalse(self.C.EMBED_KEY_FILE.exists())

    def test_none_skips_straight_past_the_model_question(self):
        cfg = self._run(NONE, NONE, *NO4)
        self.assertEqual(cfg["embed_model"], "")
        self.assertEqual(cfg["bg_model"], "")
        self.assertFalse(cfg["features"]["dense"])
        self.assertNotIn("embed_url", cfg)
        self.assertNotIn("distill_url", cfg)

    def test_walking_back_clears_the_endpoint_it_walked_away_from(self):
        """Otherwise a stale LM Studio URL keeps aiming the daemon at a runtime
        the user just abandoned."""
        cfg = self._run(LMSTUDIO, "b",        # LM Studio -> back
                        NONE,                 # ...lexical-only instead
                        NONE, *NO4)
        self.assertEqual(cfg["embed_model"], "")
        self.assertNotIn("embed_backend", cfg)
        self.assertNotIn("embed_url", cfg)


class WizardDownloadTest(WizardBase):
    """A model the runtime doesn't have yet is downloaded, and the id that lands
    in config.json is the one the server reveals afterwards."""

    def test_a_red_row_triggers_a_download_and_writes_the_resolved_id(self):
        calls = []

        def fake(prov, spec, kind):
            calls.append((prov.key, spec, kind))
            return "text-embedding-bge-m3"

        with mock.patch.object(s._providers, "pull_and_resolve", fake):
            # embedding picker: 1 nomic, 2 mpnet (both on disk), then the
            # downloads — all-minilm, embeddinggemma, bge-m3.
            cfg = self._run(LMSTUDIO, "5", LMSTUDIO, LLM_QWEN3B, *NO4, DL_YES)
        self.assertEqual(calls, [("lmstudio", "bge-m3", "embed")])
        self.assertEqual(cfg["embed_model"], "text-embedding-bge-m3")

    def test_a_failed_download_leaves_the_model_unset_rather_than_wrong(self):
        with mock.patch.object(s._providers, "pull_and_resolve",
                               lambda prov, spec, kind: None):
            cfg = self._run(LMSTUDIO, "5", LMSTUDIO, LLM_QWEN3B, *NO4, DL_YES)
        self.assertEqual(cfg["embed_model"], "")
        self.assertFalse(cfg["features"]["dense"])

    def test_nothing_is_downloaded_when_every_pick_is_already_on_disk(self):
        with mock.patch.object(s._providers, "pull_and_resolve",
                               mock.Mock(side_effect=AssertionError("must not download"))):
            self._run(LMSTUDIO, EMBED_MPNET, LMSTUDIO, LLM_QWEN3B, *NO4)

    def test_the_wizard_tells_service_install_not_to_pull(self):
        """The wizard already fetched through the right runtime; `ollama pull` on
        an LM Studio id only produces a confusing failure."""
        import yggdrasil.service as service
        seen = {}
        real = service.install
        service.install = lambda *a, **k: (seen.update(k), 0)[1]
        it = iter([LMSTUDIO, EMBED_MPNET, LMSTUDIO, LLM_QWEN3B, *NO4])
        builtins.input = lambda *a, **k: next(it)
        try:
            with redirect_stdout(io.StringIO()):
                s.wizard()
        finally:
            service.install = real
        self.assertIs(seen.get("pull"), False)


class WizardStartTest(WizardBase):
    """An installed-but-idle runtime is one keystroke from useful — the single
    most common shape of "Yggdrasil doesn't work"."""

    def setUp(self):
        super().setUp()
        self.provs[:] = _providers_fixture(ollama_installed=True)

    def test_offers_to_start_an_idle_runtime_up_front(self):
        started = []
        with mock.patch.object(s._providers, "start",
                               lambda p, wait=25.0: (started.append(p.key), True)[1]):
            self._run("y", LMSTUDIO, EMBED_MPNET, LMSTUDIO, LLM_QWEN3B, *NO4)
        self.assertEqual(started, ["ollama"])   # LM Studio is already up

    def test_declining_the_offer_is_not_an_error(self):
        with mock.patch.object(s._providers, "start",
                               mock.Mock(side_effect=AssertionError("must not start"))):
            cfg = self._run("n", LMSTUDIO, EMBED_MPNET, LMSTUDIO, LLM_QWEN3B, *NO4)
        self.assertEqual(cfg["bg_model"], "qwen2.5-3b-instruct")


class WizardConfigMergeTest(WizardBase):
    """Re-running `ygg install` must not eat settings the wizard never asks about.

    It used to write config.json from scratch, silently dropping the pinned
    user_id/namespace (which strands existing memory — the exact failure the
    0.11.0 identity migration exists to prevent) and sync_repo. embed_backend /
    embed_url / distill_url are deliberately NOT in here: the wizard owns those
    now, and clearing them when you walk away from a runtime is the point."""

    PRESET = {"user_id": "local", "namespace": "personal",
              "sync_repo": "git@github.com:me/mem.git"}

    def test_preserves_settings_it_never_asks_about(self):
        self.cfg.write_text(json.dumps(self.PRESET))
        after = self._run(LMSTUDIO, EMBED_MPNET, LMSTUDIO, LLM_QWEN3B, *NO4)
        for key, value in self.PRESET.items():
            self.assertEqual(after.get(key), value, f"wizard dropped {key}")

    def test_survives_a_corrupt_config(self):
        self.cfg.write_text("{ not json")
        after = self._run(LMSTUDIO, EMBED_MPNET, LMSTUDIO, LLM_QWEN3B, *NO4)
        self.assertEqual(after["bg_model"], "qwen2.5-3b-instruct")   # rebuilt, not crashed

    def test_works_with_no_config_yet(self):
        after = self._run(LMSTUDIO, EMBED_MPNET, LMSTUDIO, LLM_QWEN3B, *NO4)
        self.assertIn("features", after)


class HwClassifierTest(unittest.TestCase):
    def test_hw_reports_tier_and_warn_fields(self):
        h = s.hw()  # real machine — we only assert the shape/contract
        self.assertIn(h["accel_tier"], ("cpu", "metal", "cuda", "rocm/vulkan"))
        self.assertIsInstance(h["accel_warn"], str)
        # An Intel Mac must always explain why inference is CPU-only.
        if h["os"] == "Darwin" and not h["apple_silicon"]:
            self.assertTrue(h["accel_warn"])


if __name__ == "__main__":
    unittest.main()


class LargeStoreEmbedderTest(unittest.TestCase):
    """Recall decays with corpus size and a weak embedder decays fast: on this
    benchmark paraphrase-multilingual fell 0.94 -> 0.550 recall@1 between 232 and
    4,799 memories (the lexical baseline), while bge-m3 held 0.775. Past a
    threshold the wizard should stop recommending the light default."""

    GPU = {"ram_gb": 32, "accel_tier": "cuda"}
    SMALL_CPU = {"ram_gb": 8, "accel_tier": "cpu"}

    def _recommend_with_store(self, size, hw):
        with mock.patch.object(s, "_store_size", lambda: size):
            return s.recommend(hw)[0]

    def test_small_store_keeps_the_light_default(self):
        self.assertEqual(self._recommend_with_store(50, self.GPU), "paraphrase-multilingual")

    def test_large_store_on_capable_hardware_gets_bge_m3(self):
        self.assertEqual(self._recommend_with_store(5000, self.GPU), "bge-m3")

    def test_large_store_on_weak_hardware_is_not_pushed_to_a_heavy_model(self):
        self.assertEqual(self._recommend_with_store(5000, self.SMALL_CPU),
                         "paraphrase-multilingual")

    def test_missing_db_reports_zero_not_a_crash(self):
        with mock.patch.object(s, "YGG_HOME", pathlib.Path("/nonexistent-ygg-home")):
            self.assertEqual(s._store_size(), 0)


class DownloadConsentTest(unittest.TestCase):
    """Picking a red row chooses WHICH model to use; it isn't yet consent to spend
    the disk and the wait. Both picks are named with their sizes and asked once,
    right before the only slow, hard-to-undo step of the wizard."""

    class _P:
        name = "LM Studio"
        key = "lmstudio"

        def __getattr__(self, _):  # palette stand-in: any colour is identity
            return lambda t: t

    def _confirm(self, answer, picks):
        asked = {}

        def fake_confirm(prompt, default, **kw):  # noqa: ARG001
            asked["prompt"] = prompt
            return answer

        a = {"embed_prov": self._P(), "bg_prov": self._P(), **picks}
        with mock.patch.object(s._prompt, "confirm", fake_confirm), \
             mock.patch.object(s, "_catalog_for",
                               lambda prov, kind: [("bge-m3", "BGE-M3", "1.2 GB", "d", "heavy")]), \
             redirect_stdout(io.StringIO()) as out:
            ok = s._confirm_downloads(a, self._P())
        return ok, out.getvalue(), asked

    def test_nothing_pending_asks_nothing(self):
        ok, printed, asked = self._confirm(True, {"embed": "text-embedding-bge-m3", "bg": "qwen"})
        self.assertTrue(ok)
        self.assertNotIn("prompt", asked)
        self.assertEqual(printed, "")

    def test_pending_download_is_named_with_its_size(self):
        ok, printed, asked = self._confirm(True, {"embed": s._DL + "bge-m3", "bg": "qwen"})
        self.assertTrue(ok)
        self.assertIn("BGE-M3", printed)
        self.assertIn("1.2 GB", printed)
        self.assertIn("prompt", asked)

    def test_declining_leaves_the_model_unset_rather_than_half_configured(self):
        ok, _printed, _asked = self._confirm(False, {"embed": s._DL + "bge-m3", "bg": "qwen"})
        self.assertFalse(ok)


class ReasoningLabelTest(unittest.TestCase):
    """A model already on disk carries no catalog blurb, so the thing that decides
    whether distillation takes 7s or 60s a file would otherwise be invisible."""

    def test_installed_thinking_model_is_labelled(self):
        from yggdrasil import ygg_providers as P
        prov = P.Provider("lmstudio", "LM Studio", "http://x:1234",
                          [P.Model("qwen3.6-35b-a3b", "llm", "", "Q3_K_M")], dialect="openai")
        with mock.patch.object(s, "_catalog_for", lambda prov, kind: []):
            opts = s._model_options(prov, s.LLM, {"accel_tier": "cuda", "ram_gb": 32})
        self.assertIn("thinking model", opts[0].note)

    def test_instruct_build_is_not_labelled(self):
        from yggdrasil import ygg_providers as P
        prov = P.Provider("lmstudio", "LM Studio", "http://x:1234",
                          [P.Model("qwen2.5-3b-instruct", "llm", "", "Q4")], dialect="openai")
        with mock.patch.object(s, "_catalog_for", lambda prov, kind: []):
            opts = s._model_options(prov, s.LLM, {"accel_tier": "cuda", "ram_gb": 32})
        self.assertNotIn("thinking model", opts[0].note)

    def test_embedders_are_never_labelled(self):
        from yggdrasil import ygg_providers as P
        prov = P.Provider("lmstudio", "LM Studio", "http://x:1234",
                          [P.Model("text-embedding-qwen3-embedding-0.6b", "embed")],
                          dialect="openai")
        with mock.patch.object(s, "_catalog_for", lambda prov, kind: []):
            opts = s._model_options(prov, s.EMBED, {"accel_tier": "cuda", "ram_gb": 32})
        self.assertNotIn("thinking model", opts[0].note)
