"""Regression round 14: GLM provider (OpenRouter) as a GUI AI provider.

User request: "saya guna openrouter dengan glm 5.3 flash" — add GLM as
a first-class GUI provider. Verified against the public OpenRouter
catalog before implementation: z-ai/glm-5.3-flash exists, its
architecture is text+image+video -> text (vision capable), so frame
mode works with data-URL images.

Covered here WITHOUT any network access:
1. GLMProvider.describe_image drives a local HTTP loopback that mimics
   the OpenAI-compatible /chat/completions contract (Bearer auth,
   data:image/...;base64 image block) and returns the text content.
2. ask_text reuses the same endpoint with text-only messages.
3. AIEngine registry wires glm end to end (set_provider -> describe).
4. Settings dialog: glm appears in the provider choice, its model list
   contains z-ai/glm-5.3-flash, config persists via SettingsStore with
   the OpenRouter base_url default.
"""
import isolate  # noqa: F401  (first: never the owner's real data, pitfall 19)
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


# ── 1. Loopback that mimics the OpenAI-compatible contract ──────────

class _GLMStub(BaseHTTPRequestHandler):
    captured: dict = {}

    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        auth = self.headers.get("Authorization", "")
        self.__class__.captured = {
            "path": self.path,
            "auth": auth,
            "body": body,
        }
        # Accept ONLY the exact Bearer key the test sets.
        if auth != "Bearer sk-or-v1-test":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"bad key"}}')
            return
        reply = "Kucing duduk di atas meja."
        payload = json.dumps({
            "id": "chatcmpl-glm1",
            "model": body.get("model", ""),
            "choices": [
                {"index": 0,
                 "message": {"role": "assistant", "content": reply},
                 "finish_reason": "stop"}
            ],
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


def _make_image(tmp: Path) -> Path:
    from PIL import Image
    p = tmp / "glm_frame.jpg"
    Image.new("RGB", (64, 64), (200, 30, 30)).save(p, "JPEG")
    return p


def test_glm_describe_image():
    from omni_describer_custom.core.ai_engine import GLMProvider

    with tempfile.TemporaryDirectory() as td:
        img = _make_image(Path(td))
        server = HTTPServer(("127.0.0.1", 0), _GLMStub)
        port = server.server_address[1]
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        try:
            prov = GLMProvider(
                api_key="sk-or-v1-test",
                base_url=f"http://127.0.0.1:{port}")
            text = _run(lambda: prov.describe_image(
                str(img), "Describe this frame."))
            assert text == "Kucing duduk di atas meja.", text
            cap = _GLMStub.captured
            # OpenAI-compatible contract
            assert cap["path"] == "/chat/completions", cap["path"]
            assert cap["auth"] == "Bearer sk-or-v1-test", cap["auth"]
            body = cap["body"]
            assert body["model"] == "z-ai/glm-5.3-flash", body["model"]
            content = body["messages"][0]["content"]
            kinds = [b["type"] for b in content]
            assert kinds == ["text", "image_url"], kinds
            url = content[1]["image_url"]["url"]
            assert url.startswith("data:image/jpeg;base64,"), url[:40]
        finally:
            server.shutdown()


def test_glm_ask_text():
    from omni_describer_custom.core.ai_engine import GLMProvider

    server = HTTPServer(("127.0.0.1", 0), _GLMStub)
    port = server.server_address[1]
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    try:
        prov = GLMProvider(api_key="sk-or-v1-test",
                           base_url=f"http://127.0.0.1:{port}")
        text = _run(lambda: prov.ask_text("Say OK"))
        assert text == "Kucing duduk di atas meja.", text
        body = _GLMStub.captured["body"]
        msgs = body["messages"]
        assert msgs[-1] == {"role": "user", "content": "Say OK"}, msgs
        # text-only messages (no image blocks)
        assert all(isinstance(m["content"], str) for m in msgs), msgs
    finally:
        server.shutdown()


# ── 3. Engine registry wiring ────────────────────────────────────────

def test_engine_wires_glm():
    from omni_describer_custom.core.ai_engine import AIEngine, GLMProvider

    assert AIEngine.PROVIDERS.get("glm") is GLMProvider
    server = HTTPServer(("127.0.0.1", 0), _GLMStub)
    port = server.server_address[1]
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    try:
        with tempfile.TemporaryDirectory() as td:
            img = _make_image(Path(td))
            engine = AIEngine()
            engine.set_provider(
                "glm", api_key="sk-or-v1-test",
                base_url=f"http://127.0.0.1:{port}")
            desc = _run(lambda: engine.describe_frame(
                str(img), "Describe this frame."))
            assert desc == "Kucing duduk di atas meja.", desc
    finally:
        server.shutdown()


# ── 4. Settings dialog + store ──────────────────────────────────────

def test_settings_glm_ui():
    from omni_describer_custom.core.settings_store import SettingsStore
    from omni_describer_custom.ui.settings_dialog import SettingsDialog

    with tempfile.TemporaryDirectory() as td:
        store = SettingsStore(config_dir=td)
        frame = wx.Frame(None)
        try:
            dlg = SettingsDialog(frame, store)
            # glm offered as a provider choice
            assert dlg.provider_choice.GetItems(), "items must be non-empty"
            # model list contains the OpenRouter-prefixed id
            dlg.select_provider("glm")
            # v1.8.5: the label may say "Recommended: ..." first; the
            # id is still in it, and the VALUE saved is the bare id.
            assert any("z-ai/glm-5.3-flash" in i
                       for i in dlg.model_choice.GetItems()), \
                dlg.model_choice.GetItems()
            # default selection comes from the store preset
            assert dlg._choice_value(dlg.model_choice) == \
                "z-ai/glm-5.3-flash", dlg._choice_value(dlg.model_choice)
            # persist selection + key
            store.set("ai.default_provider", "glm")
            store.set_ai_provider("glm", {
                "api_key": "sk-or-v1-abc",
                "model": "z-ai/glm-5.3-flash",
                "base_url": "https://openrouter.ai/api/v1",
            })
            cfg = store.get_ai_provider("glm")
            assert cfg["api_key"] == "sk-or-v1-abc", cfg
            assert cfg["base_url"] == "https://openrouter.ai/api/v1", cfg
            # reopening the dialog preselects glm with its model
            dlg.Destroy()
            dlg2 = SettingsDialog(frame, store)
            assert dlg2._selected_provider() == "glm"
            assert dlg2._choice_value(dlg2.model_choice) == \
                "z-ai/glm-5.3-flash"
            dlg2.Destroy()
        finally:
            frame.Destroy()


def main() -> int:
    check("glm describe_image (loopback, OpenAI contract)",
          test_glm_describe_image)
    check("glm ask_text (loopback)", test_glm_ask_text)
    check("engine wires glm end to end", test_engine_wires_glm)
    check("settings glm UI + persistence", test_settings_glm_ui)
    print(f"RESULT: {ok} passed, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
