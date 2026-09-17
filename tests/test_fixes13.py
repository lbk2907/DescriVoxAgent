"""Regression round 13: MiniMax as a second full-video provider.

User request: "model lain boleh juga support video macam Claude ke
OpenAI ke MiniMax ke" -> research showed MiniMax accepts whole-video
files (Files API, purpose=video_understanding, mm_file://{file_id})
while Claude/OpenAI/Z.ai do not accept local video files. This round
adds MiniMaxProvider and enables full-video mode for gemini OR minimax.

Covered here WITHOUT any network access:
1. _strip_think removes MiniMax <think> reasoning blocks (full, absent,
   truncated-mid-thinking) so the timestamp parser only sees the answer.
2. MiniMaxProvider.describe_video_full drives the full flow against a
   local HTTP loopback mimicking the Files API: multipart upload with
   purpose=video_understanding -> chat with mm_file:// reference ->
   <think>-stripped, parsed (seconds, text) pairs.
3. AIEngine registry wires minimax end to end (same loopback).
4. Settings dialog: minimax appears in the provider choice, model list
   contains MiniMax-M3, and the full-video checkbox is enabled for
   gemini AND minimax, disabled for others.
5. Bilingual strings: provider-neutral full-video wording and the new
   mm_file error key exist in BOTH languages.
"""
import asyncio
import io
import json
import sys
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import wx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace",
                              line_buffering=True)
sys.path.insert(0, "src")

ok = 0
fail = 0
_app = None


def check(name, fn):
    global ok, fail, _app
    try:
        import wx
        _app = wx.GetApp() or wx.App(False)
        fn()
        print(f"PASS: {name}")
        ok += 1
    except Exception as e:
        print(f"FAIL: {name}: {e}")
        traceback.print_exc()
        fail += 1


# ── 1. <think> stripping ─────────────────────────────────────────────

def test_strip_think():
    from omni_describer_custom.core.ai_engine import _strip_think

    full = "<think>\nUser wants a description.\nLet me look.\n</think>\n[00:00] The answer."
    assert _strip_think(full) == "[00:00] The answer.", repr(_strip_think(full))
    assert _strip_think("no think block at all") == "no think block at all"
    # Truncated mid-thinking: keep only text before the block
    trunc = "<think>partial reasoning without a closing tag"
    assert _strip_think(trunc) == "", repr(_strip_think(trunc))
    assert _strip_think("") == ""
    # Multi-line timestamps after think survive intact
    multi = ("<think>x</think>\n"
             "[00:00] A red car drives past green hills.\n"
             "[00:10] The narrator greets the audience.")
    out = _strip_think(multi)
    assert out.startswith("[00:00] A red car"), repr(out)


# ── 2. Full MiniMax flow over a loopback ──────────────────────────────

_CHAT_SEEN: list[dict] = []
_UPLOAD_SEEN: list[bytes] = []


class _MiniMaxStub(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        if self.path.endswith("/v1/files/upload"):
            _UPLOAD_SEEN.append(body)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "file": {"file_id": "file_abc123", "bytes": length,
                         "filename": "clip.mp4",
                         "purpose": "video_understanding"},
                "base_resp": {"status_code": 0, "status_msg": "success"},
            }).encode())
            return
        if self.path.endswith("/v1/chat/completions"):
            payload = json.loads(body)
            _CHAT_SEEN.append(payload)
            content = "<think>\nThe user wants a timestamped description.\n</think>\n" \
                      "[00:00] A red car drives past green hills.\n" \
                      "[00:10] The narrator greets the audience."
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "id": "resp1", "model": "MiniMax-M3",
                "choices": [{"finish_reason": "stop", "index": 0,
                             "message": {"role": "assistant",
                                         "content": content}}],
                "usage": {"total_tokens": 100},
                "base_resp": {"status_code": 0, "status_msg": ""},
            }).encode())
            return
        self.send_response(404)
        self.end_headers()


def test_minimax_full_flow():
    from omni_describer_custom.core.ai_engine import MiniMaxProvider

    _UPLOAD_SEEN.clear()
    _CHAT_SEEN.clear()
    server = HTTPServer(("127.0.0.1", 0), _MiniMaxStub)
    port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        tmp = Path(tempfile.mkdtemp(prefix="odc_mm_")) / "clip.mp4"
        tmp.write_bytes(b"\x00" * 4096)

        statuses: list[str] = []
        progress: list[float] = []

        async def run():
            prov = MiniMaxProvider(
                api_key="test-key", base_url=f"http://127.0.0.1:{port}")
            return await prov.describe_video_full(
                str(tmp), "Describe this video.",
                on_status=statuses.append,
                on_upload_progress=progress.append)

        pairs = asyncio.new_event_loop().run_until_complete(run())

        assert statuses == ["uploading", "describing"], statuses
        assert pairs == [
            (0.0, "A red car drives past green hills."),
            (10.0, "The narrator greets the audience."),
        ], pairs
        assert any(p == 100.0 for p in progress), progress

        # Upload was multipart with the documented purpose + the bytes
        assert len(_UPLOAD_SEEN) == 1, len(_UPLOAD_SEEN)
        up = _UPLOAD_SEEN[0]
        assert b'name="purpose"' in up and b"video_understanding" in up, up[:200]
        assert b'filename="clip.mp4"' in up, up[:200]

        # Chat referenced the uploaded file via mm_file:// and carried
        # the timestamp-format instruction
        assert len(_CHAT_SEEN) == 1, len(_CHAT_SEEN)
        chat = _CHAT_SEEN[0]
        assert chat["model"] == "MiniMax-M3", chat["model"]
        content = chat["messages"][0]["content"]
        assert content[0]["type"] == "video_url", content
        assert content[0]["video_url"]["url"] == "mm_file://file_abc123", content
        assert content[1]["type"] == "text" and "[MM:SS]" in content[1]["text"]
    finally:
        server.shutdown()


def test_engine_wires_minimax():
    from omni_describer_custom.core.ai_engine import AIEngine, MiniMaxProvider

    assert AIEngine.PROVIDERS.get("minimax") is MiniMaxProvider
    _UPLOAD_SEEN.clear()
    _CHAT_SEEN.clear()
    server = HTTPServer(("127.0.0.1", 0), _MiniMaxStub)
    port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        tmp = Path(tempfile.mkdtemp(prefix="odc_mm_eng_")) / "clip.mp4"
        tmp.write_bytes(b"\x00" * 2048)

        async def run():
            engine = AIEngine()
            engine.set_provider(
                "minimax", api_key="k",
                base_url=f"http://127.0.0.1:{port}")
            return await engine.describe_video_full(str(tmp), "Describe.")

        pairs = asyncio.new_event_loop().run_until_complete(run())
        assert pairs and pairs[0][0] == 0.0 and pairs[0][1].startswith(
            "A red car"), pairs
    finally:
        server.shutdown()


def test_engine_still_rejects_frame_only_providers():
    from omni_describer_custom.core.ai_engine import AIEngine

    engine = AIEngine()
    engine.set_provider("openai", api_key="k")
    loop = asyncio.new_event_loop()
    try:
        try:
            loop.run_until_complete(
                engine.describe_video_full("x.mp4", "p"))
        except ValueError as e:
            assert "full-video" in str(e), e
        else:
            raise AssertionError("expected ValueError for openai")
    finally:
        loop.close()


# ── 4. Settings UI ───────────────────────────────────────────────────

def test_settings_minimax_ui():
    from unittest.mock import patch

    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.ui.settings_dialog import SettingsDialog

    tmpdir = tempfile.mkdtemp(prefix="odc_mm_settings_")
    store = SettingsStore(config_dir=tmpdir)
    dlg = SettingsDialog(None, store)

    mb_patch = patch.object(wx, "MessageBox", lambda *a, **k: wx.OK)
    mb_patch.start()
    try:
        # minimax is offered as a provider choice
        assert dlg.provider_choice.GetItems(), "items must be non-empty"

        # Full-video checkbox: enabled for minimax AND gemini, disabled
        # for frame-only providers
        dlg.select_provider("minimax")
        assert dlg.video_mode_cb.IsEnabled(), "minimax must enable video mode"
        dlg.select_provider("gemini")
        assert dlg.video_mode_cb.IsEnabled(), "gemini must enable video mode"
        for prov in ("openai", "custom"):
            dlg.select_provider(prov)
            assert not dlg.video_mode_cb.IsEnabled(), prov
            assert not dlg.video_mode_cb.GetValue(), prov

        # Model list for minimax contains MiniMax-M3
        dlg.select_provider("minimax")
        assert "MiniMax-M3" in dlg.model_choice.GetItems(), \
            dlg.model_choice.GetItems()

        # Persist minimax selection with video mode on
        dlg.video_mode_cb.SetValue(True)
        store.set("ai.default_provider", "minimax")
        store.set_ai_provider("minimax", {"api_key": "k", "model": "MiniMax-M3"})
        dlg._on_apply(None)
        assert store.get("ai.video_mode") == "full", store.get("ai.video_mode")
    finally:
        mb_patch.stop()
        dlg.Destroy()


# ── 5. Bilingual strings ─────────────────────────────────────────────

def test_bilingual_strings():
    from omni_describer_custom.i18n import strings as s

    for key in ("video.mm_file_error", "video.phase_uploading",
                "video.phase_processing", "video.phase_describing",
                "video.uploading_progress", "video.parsed_count",
                "status.analyzing_video", "settings.video_mode"):
        assert key in s.EN_STRINGS, key
        assert key in s.MS_STRINGS, key

    # Full-video wording names both capable providers, in both languages
    assert "Gemini" in s.EN_STRINGS["settings.video_mode"]
    assert "MiniMax" in s.EN_STRINGS["settings.video_mode"]
    assert "Gemini" in s.MS_STRINGS["settings.video_mode"]
    assert "MiniMax" in s.MS_STRINGS["settings.video_mode"]

    # Status phases remain distinct (screen-reader clarity) in both
    for table in (s.EN_STRINGS, s.MS_STRINGS):
        phases = [table[f"video.phase_{p}"]
                  for p in ("uploading", "processing", "describing")]
        assert len(set(phases)) == 3, phases


# ── runner ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    check("minimax think-stripping", test_strip_think)
    check("minimax full-video flow (loopback)", test_minimax_full_flow)
    check("engine wires minimax end to end", test_engine_wires_minimax)
    check("engine still rejects frame-only providers",
          test_engine_still_rejects_frame_only_providers)
    check("settings minimax UI + persistence", test_settings_minimax_ui)
    check("bilingual strings neutral + mm_file error",
          test_bilingual_strings)
    print(f"\nRESULT: {ok} passed, {fail} failed")
    sys.exit(1 if fail else 0)
