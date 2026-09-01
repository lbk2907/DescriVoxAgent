"""Regression round 12: Gemini full-video mode.

User request: AI that WATCHES the video itself and returns its own
timestamped descriptions (Gemini native video understanding), instead of
the app extracting frames and describing them one by one.

Covered here WITHOUT any network access:
1. parse_gemini_timestamp_lines parses the documented [MM:SS] output
   format (bullets, brackets, hours, milliseconds) and ignores noise.
2. GeminiProvider.describe_video_full drives the full flow against a
   local HTTP loopback that mimics the Files API (resumable upload ->
   ACTIVE state -> generateContent with timestamped text) and returns
   parsed (seconds, text) pairs in order.
3. Unsupported providers raise a clear ValueError from AIEngine.
4. Settings dialog: the checkbox exists in the AI tab, is disabled for
   non-Gemini providers, enabled for Gemini, and persists ai.video_mode.
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

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
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


# ── 1. Parser ────────────────────────────────────────────────────────

def test_parser():
    from omni_describer_custom.core.ai_engine import parse_gemini_timestamp_lines

    text = (
        "Here is the description:\n"
        "[00:00] A man in a red jacket enters a bright kitchen.\n"
        "- 00:15 - He pours coffee while talking on the phone.\n"
        "[01:02:03.500] Hours format with milliseconds works too.\n"
        "* (12:34) Bracketed minutes only.\n"
        "This line has no timestamp and must be ignored.\n"
        "[00:05]\n"  # timestamp with no text -> ignored
    )
    pairs = parse_gemini_timestamp_lines(text)
    assert pairs == [
        (0.0, "A man in a red jacket enters a bright kitchen."),
        (15.0, "He pours coffee while talking on the phone."),
        (3723.5, "Hours format with milliseconds works too."),
        (754.0, "Bracketed minutes only."),
    ], pairs
    assert parse_gemini_timestamp_lines("") == []
    assert parse_gemini_timestamp_lines("no timestamps at all") == []


# ── 2. Full flow over a loopback that mimics the Gemini API ─────────

class _GeminiStub(BaseHTTPRequestHandler):
    posted_bodies: list[bytes] = []

    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _GeminiStub.posted_bodies.append(body)
        # Step 1: resumable init -> hand back an upload URL on this server
        if "uploadType=resumable" in self.path:
            self.send_response(200)
            self.send_header("X-Goog-Upload-URL",
                             f"http://127.0.0.1:{self.server.server_port}/upload")
            self.end_headers()
            return
        # Step 2: chunk upload (finalize) -> file resource
        if self.path.startswith("/upload"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "file": {
                    "uri": (f"http://generativelanguage.googleapis.com/v1beta/"
                            f"files/demoabc123"),
                    "name": "files/demoabc123",
                    "state": "PROCESSING",
                }
            }).encode())
            return
        # Step 3: generateContent -> timestamped description text
        if ":generateContent" in self.path:
            payload = json.loads(body)
            parts = payload["contents"][0]["parts"]
            assert any("file_data" in p for p in parts), parts
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "candidates": [{"content": {"parts": [
                    {"text": "[00:00] A red car drives past green hills.\n"
                             "[00:10] The narrator greets the audience."}
                ]}}]
            }).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        # Files API status poll -> ACTIVE
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"name": "files/demoabc123",
                                     "state": "ACTIVE"}).encode())


def test_full_video_flow():
    from omni_describer_custom.core.ai_engine import GeminiProvider

    server = HTTPServer(("127.0.0.1", 0), _GeminiStub)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # Tiny real file as the upload payload
        tmp = Path(tempfile.mkdtemp(prefix="odc_test_")) / "video.mp4"
        tmp.write_bytes(b"\x00" * 4096)

        statuses: list[str] = []
        progress: list[float] = []

        async def run():
            prov = GeminiProvider(api_key="test-key",
                                  base_url=f"http://127.0.0.1:{port}/v1beta")
            return await prov.describe_video_full(
                str(tmp), "Describe this video.",
                on_status=statuses.append,
                on_upload_progress=progress.append)

        pairs = asyncio.new_event_loop().run_until_complete(run())
        assert statuses == ["uploading", "processing", "describing"], statuses
        assert pairs == [
            (0.0, "A red car drives past green hills."),
            (10.0, "The narrator greets the audience."),
        ], pairs
        assert any(p == 100.0 for p in progress), progress
    finally:
        server.shutdown()


def test_engine_rejects_non_gemini():
    from omni_describer_custom.core.ai_engine import AIEngine, OpenAIProvider

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
            raise AssertionError("expected ValueError for non-Gemini provider")
    finally:
        loop.close()


# ── 4. Settings UI ───────────────────────────────────────────────────

def test_settings_video_mode():
    from unittest.mock import patch

    import wx

    from omni_describer_custom.ui.settings_dialog import SettingsDialog
    from omni_describer_custom.core.settings_store import SettingsStore

    tmpdir = tempfile.mkdtemp(prefix="odc_settings_")
    store = SettingsStore(config_dir=tmpdir)
    dlg = SettingsDialog(None, store)

    # _on_apply pops a modal MessageBox; in tests nobody can click OK,
    # so stub it (no app-level change needed).
    mb_patch = patch.object(wx, "MessageBox", lambda *a, **k: wx.OK)
    mb_patch.start()

    try:
        _run_settings_checks(dlg, store)
    finally:
        mb_patch.stop()
        dlg.Destroy()


def _run_settings_checks(dlg, store) -> None:
    # Checkbox lives in the AI tab (parent chain: AI tab panel)
    cb = dlg.video_mode_cb
    assert cb.GetName() == "video_mode"
    ai_page = dlg.notebook.GetPage(1)
    parent = cb.GetParent()
    assert parent is ai_page, type(parent).__name__

    # Disabled for non-Gemini, enabled for Gemini
    dlg.provider_choice.SetStringSelection("openai")
    dlg._on_provider_changed(None)
    assert not cb.IsEnabled()
    assert not cb.GetValue()
    dlg.provider_choice.SetStringSelection("gemini")
    dlg._on_provider_changed(None)
    assert cb.IsEnabled()

    # Persist on apply
    dlg.provider_choice.SetStringSelection("gemini")
    dlg._on_provider_changed(None)
    cb.SetValue(True)
    store.set("ai.default_provider", "gemini")
    store.set_ai_provider("gemini", {"api_key": "k", "model": "gemini-2.5-flash"})
    dlg._on_apply(None)
    assert store.get("ai.video_mode") == "full", store.get("ai.video_mode")
    cb.SetValue(False)
    dlg._on_apply(None)
    assert store.get("ai.video_mode") == "frames"
    dlg.Destroy()


if __name__ == "__main__":
    check("gemini timestamp parser", test_parser)
    check("gemini full-video flow (loopback)", test_full_video_flow)
    check("non-gemini rejected clearly", test_engine_rejects_non_gemini)
    check("settings video-mode checkbox", test_settings_video_mode)
    print(f"\nRESULT: {ok} passed, {fail} failed")
    sys.exit(1 if fail else 0)
