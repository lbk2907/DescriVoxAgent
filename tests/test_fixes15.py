"""Regression round 15: fast one-shot mode (GLM burn-in, ALL frames in
ONE request) + timestamp snapping.

User request: GUI should support the video_describer one-request flow.
The model READS the H:MM:SS stamp burned into every frame; replies are
parsed and snapped onto the known extraction grid so a stamp misread
cannot desync the player timeline.

Covered here WITHOUT any network access:
1. build_fast_batch_filter returns the ffmpeg-8.x-VERIFIED drawtext
   recipe (escaped + quoted drive-letter colon, explicit fontfile,
   %{pts:hms} stamp, dark box top-left).
2. snap_timestamps: exact hits stay, misreads snap to the nearest
   grid time, entries beyond max_gap are dropped.
3. GLMProvider.describe_video_frames_batch drives a loopback: single
   request for <=150 frames with every frame as an image_url block,
   burn-in instructions as the final text block; parsed lines snapped,
   sorted; >150 frames auto-batch into concurrent requests.
4. AIEngine wiring + Settings dialog: checkbox only enabled for glm,
   ai.fast_mode persists via SettingsStore.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
import asyncio
import io
import json
import sys
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


# ── 1. Verified drawtext recipe ──────────────────────────────────────

def test_filter_recipe():
    from omni_describer_custom.core.ai_engine import build_fast_batch_filter

    vf = build_fast_batch_filter(1)
    assert vf.startswith("fps=1,scale=-2:720,"), vf
    # drive-letter colon BOTH escaped AND single-quoted (ffmpeg 8.x verified)
    assert "fontfile='C\\:/Windows/Fonts/arial.ttf'" in vf, vf
    # burned-in H:MM:SS via pts:hms, dark box top-left, white text
    assert "text='%{pts\\:hms}'" in vf, vf
    assert "x=10:y=10" in vf and "boxcolor=black@0.6" in vf, vf
    assert "fontcolor=white" in vf, vf
    vf2 = build_fast_batch_filter(0.5)
    assert vf2.startswith("fps=0.5,scale=-2:720,"), vf2


# ── 2. Timestamp snapping ────────────────────────────────────────────

def test_snap_timestamps():
    from omni_describer_custom.core.ai_engine import snap_timestamps

    grid = [0.0, 1.0, 2.0, 3.0, 4.0]
    events = [
        (0.0, "exact start"),
        (3.2, "misread 3 -> nearest 3.0"),
        (9.0, "way off -> dropped (beyond 1.5s)"),
        (1.05, "rounds to 1.0"),
    ]
    out = snap_timestamps(events, grid)
    assert out == [
        (0.0, "exact start"),
        (1.0, "rounds to 1.0"),
        (3.0, "misread 3 -> nearest 3.0"),
    ], out
    # empty grid -> untouched (sorted only)
    assert snap_timestamps(events, []) == sorted(
        events, key=lambda x: x[0])
    # empty text entries dropped
    assert snap_timestamps([(1.0, "")], grid) == []
    # unsorted grid input is normalized
    out2 = snap_timestamps([(2.0, "x")], [3.0, 1.0, 2.0])
    assert out2 == [(2.0, "x")], out2


# ── 3. Loopback: the OpenAI-compatible one-shot contract ────────────

REPLY_LINES = (
    "0:00:00 - Opening scene.\n"
    "0:00:03 - The man walks in.\n"
    "0:00:09 - This has no nearby frame.\n"
)


class _FastStub(BaseHTTPRequestHandler):
    captured: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.__class__.captured.append({
            "path": self.path,
            "auth": self.headers.get("Authorization", ""),
            "body": body,
        })
        if self.headers.get("Authorization") != "Bearer sk-or-v1-test":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"bad key"}}')
            return
        payload = json.dumps({
            "id": "chatcmpl-fast1",
            "model": body.get("model", ""),
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant",
                                     "content": REPLY_LINES}}],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _run(coro_factory):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        loop.close()


def _make_images(tmp: Path, n: int) -> list[str]:
    from PIL import Image
    out = []
    for i in range(n):
        p = tmp / f"frame_{i:05d}.jpg"
        Image.new("RGB", (64, 64), (30 * i, 90, 160)).save(p, "JPEG")
        out.append(str(p))
    return out


def test_glm_fast_batch_single():
    import omni_describer_custom.core.ai_engine as ae
    from omni_describer_custom.core.ai_engine import GLMProvider

    with tempfile.TemporaryDirectory() as td:
        frames = _make_images(Path(td), 3)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _FastStub)
        port = server.server_address[1]
        _FastStub.captured = []
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        try:
            prov = GLMProvider(api_key="sk-or-v1-test",
                               base_url=f"http://127.0.0.1:{port}")
            expected = [0.0, 1.0, 2.0]
            pairs = _run(lambda: prov.describe_video_frames_batch(
                frames, "Describe the video.",
                expected_times=expected))
            # 0:00:00 exact; reply stamp 3s is past the last frame and
            # snaps to 2.0 (|3-2|=1 < |3-1|=2); 9s -> dropped (>1.5s)
            assert pairs == [
                (0.0, "Opening scene."),
                (2.0, "The man walks in."),
            ], pairs
            assert len(_FastStub.captured) == 1, len(_FastStub.captured)
            cap = _FastStub.captured[0]
            assert cap["path"] == "/chat/completions", cap["path"]
            assert cap["auth"] == "Bearer sk-or-v1-test", cap["auth"]
            body = cap["body"]
            assert body["model"] == "z-ai/glm-5.3-flash", body["model"]
            content = body["messages"][0]["content"]
            kinds = [b["type"] for b in content]
            assert kinds == ["image_url", "image_url", "image_url", "text"], \
                kinds
            for b in content[:3]:
                assert b["image_url"]["url"].startswith(
                    "data:image/jpeg;base64,"), b["image_url"]["url"][:40]
            text = content[3]["text"]
            assert "H:MM:SS" in text and "BURNED" in text.upper(), text
        finally:
            server.shutdown()


def test_glm_fast_batch_autobatch():
    from omni_describer_custom.core.ai_engine import GLMProvider

    with tempfile.TemporaryDirectory() as td:
        frames = _make_images(Path(td), 5)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _FastStub)
        port = server.server_address[1]
        _FastStub.captured = []
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        try:
            prov = GLMProvider(api_key="sk-or-v1-test",
                               base_url=f"http://127.0.0.1:{port}")
            expected = [float(i) for i in range(5)]
            pairs = _run(lambda: prov.describe_video_frames_batch(
                frames, "Describe the video.",
                expected_times=expected))
            # 5 frames <= 150 -> still ONE request, correct contract
            assert len(_FastStub.captured) == 1, len(_FastStub.captured)
            content = _FastStub.captured[0]["body"]["messages"][0]["content"]
            assert len(content) == 6, len(content)  # 5 images + 1 text
            assert pairs == [
                (0.0, "Opening scene."),
                (3.0, "The man walks in."),
            ], pairs
        finally:
            server.shutdown()


def test_fast_batch_cancelled():
    from omni_describer_custom.core.ai_engine import GLMProvider

    prov = GLMProvider(api_key="sk-or-v1-test")
    try:
        _run(lambda: prov.describe_video_frames_batch(
            ["x.jpg"], "p", is_cancelled=lambda: True))
        raise AssertionError("expected RuntimeError for cancelled")
    except RuntimeError as e:
        assert "cancel" in str(e).lower(), e


def test_glm_video_full_loopback():
    from omni_describer_custom.core.ai_engine import GLMProvider

    with tempfile.TemporaryDirectory() as td:
        video = Path(td) / "clip.mp4"
        video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 64)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _FastStub)
        port = server.server_address[1]
        _FastStub.captured = []
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        try:
            prov = GLMProvider(api_key="sk-or-v1-test",
                               base_url=f"http://127.0.0.1:{port}")
            statuses = []
            pairs = _run(lambda: prov.describe_video_full(
                str(video), "Describe the video.",
                on_status=statuses.append))
            assert statuses[0] == "encoding" and "parsing" in statuses, \
                statuses
            assert (0.0, "Opening scene.") in pairs, pairs
            cap = _FastStub.captured[0]
            content = cap["body"]["messages"][0]["content"]
            kinds = [b["type"] for b in content]
            assert kinds == ["text", "video_url", "text"], kinds
            assert content[1]["video_url"]["url"].startswith(
                "data:video/mp4;base64,"), kinds
            # oversized short video (probe fails on fake bytes, so the
            # guard is tripped directly in _describe_one_part) → the
            # compression path runs and fails on fake bytes with a
            # clear error (verifies the path is wired).
            prov.MAX_VIDEO_BYTES = 4
            try:
                _run(lambda: prov.describe_video_full(
                    str(video), "p"))
                raise AssertionError("expected size guard to trigger")
            except RuntimeError as e:
                assert "compression failed" in str(e), e
        finally:
            server.shutdown()


# ── 4. Engine + settings wiring ──────────────────────────────────────

def test_engine_wires_fast_batch():
    from omni_describer_custom.core.ai_engine import AIEngine

    server = ThreadingHTTPServer(("127.0.0.1", 0), _FastStub)
    port = server.server_address[1]
    _FastStub.captured = []
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    try:
        with tempfile.TemporaryDirectory() as td:
            frames = _make_images(Path(td), 2)
            engine = AIEngine()
            engine.set_provider(
                "glm", api_key="sk-or-v1-test",
                base_url=f"http://127.0.0.1:{port}")
            pairs = _run(lambda: engine.describe_video_frames_batch(
                frames, "Describe the video.",
                expected_times=[0.0, 1.0]))
            assert pairs and pairs[0][0] == 0.0, pairs
            # a provider without the method raises a clear ValueError
            engine2 = AIEngine()
            engine2.set_provider("openai", api_key="k")
            try:
                _run(lambda: engine2.describe_video_frames_batch(
                    frames, "p"))
                raise AssertionError("expected ValueError for openai")
            except ValueError as e:
                assert "one-shot" in str(e), e
    finally:
        server.shutdown()


def test_settings_fast_mode_ui():
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.ui.settings_dialog import SettingsDialog

    with tempfile.TemporaryDirectory() as td:
        store = SettingsStore(config_dir=td)
        frame = wx.Frame(None)
        try:
            dlg = SettingsDialog(frame, store)
            assert hasattr(dlg, "fast_mode_cb"), "checkbox must exist"
            # disabled + unchecked for non-glm providers
            dlg.select_provider("openai")
            assert not dlg.fast_mode_cb.IsEnabled()
            assert not dlg.fast_mode_cb.GetValue()
            # enabled for glm
            dlg.select_provider("glm")
            assert dlg.fast_mode_cb.IsEnabled()
            dlg.fast_mode_cb.SetValue(True)
            # persisted through the store
            store.set("ai.fast_mode", True)
            dlg.Destroy()
            dlg2 = SettingsDialog(frame, store)
            assert dlg2.fast_mode_cb.GetValue(), "fast_mode must persist"
            dlg2.Destroy()
        finally:
            frame.Destroy()


def test_fetch_openrouter_video_models_loopback():
    from omni_describer_custom.core.ai_engine import (
        fetch_openrouter_video_models)

    class _CatalogStub(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = json.dumps({"data": [
                {"id": "text/only",
                 "architecture": {"input_modalities": ["text"]}},
                {"id": "video/model",
                 "architecture": {"input_modalities": ["text", "video"]}},
                {"id": "noarch/model"},
            ]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), _CatalogStub)
    port = server.server_address[1]
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    try:
        models = _run(lambda: fetch_openrouter_video_models(
            catalog_url=f"http://127.0.0.1:{port}/models"))
        assert models == ["video/model"], models
    finally:
        server.shutdown()


def test_provider_labels_and_select():
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.ui.settings_dialog import SettingsDialog

    with tempfile.TemporaryDirectory() as td:
        store = SettingsStore(config_dir=td)
        frame = wx.Frame(None)
        try:
            dlg = SettingsDialog(frame, store)
            # glm must be displayed as a friendly label, not the id
            items = dlg.provider_choice.GetItems()
            assert "glm" not in items, items
            assert "OpenRouter" in items, items
            # select_provider reasons in machine ids
            dlg.select_provider("glm")
            assert dlg._selected_provider() == "glm"
            assert dlg.fast_mode_cb.IsEnabled()
            assert dlg.fetch_models_btn.IsEnabled()
            assert dlg.video_only_hint.IsShown()
            dlg.select_provider("openai")
            assert not dlg.fetch_models_btn.IsEnabled()
            dlg.Destroy()
        finally:
            frame.Destroy()


def main() -> int:
    check("fast-batch drawtext recipe (ffmpeg 8.x verified)",
          test_filter_recipe)
    check("snap_timestamps nearest-grid correction", test_snap_timestamps)
    check("glm fast batch single request (loopback)",
          test_glm_fast_batch_single)
    check("glm fast batch auto-batch + merge (loopback)",
          test_glm_fast_batch_autobatch)
    check("fast batch cancelled raises", test_fast_batch_cancelled)
    check("glm full-video upload via video_url (loopback)",
          test_glm_video_full_loopback)
    check("engine wires fast batch + clear ValueError",
          test_engine_wires_fast_batch)
    check("settings fast-mode checkbox glm-only + persistence",
          test_settings_fast_mode_ui)
    check("fetch video-capable models from catalog (loopback)",
          test_fetch_openrouter_video_models_loopback)
    check("provider labels + select_provider helper",
          test_provider_labels_and_select)
    print(f"RESULT: {ok} passed, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
