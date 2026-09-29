"""Regression round 48: the upload moves the bar and the phases are spoken (v1.8.4).

Reported by the owner after the 1.8.3 long-video test (29 Sep 2026):

  1. While a video was sent to the provider the bar sat at 0% and only
     a seconds counter moved: GLM sent the whole part as one JSON body
     with no way to tell how far it got, and the model's minutes-long
     wait that follows had no progress at all.
  2. A change of phase ("uploading" -> "the AI is watching") was never
     read by NVDA: the dialog keeps focus on Cancel, and a screen reader
     does not read text changing away from the focus.
  3. Found while fixing it: at the START of part 1 of 2 the app said
     "overall 55%" (it counted the part as already done).

Now the body is streamed with a byte count, the wait is estimated from
what this model took before (core/timing_store), and each phase is said
through Prism, which speaks through the screen reader.
"""
import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ["ODC_CONFIG_DIR"] = tempfile.mkdtemp(prefix="odc_t48_cfg_")
os.environ.setdefault("ODC_PROJECTS_DIR", tempfile.mkdtemp(prefix="odc_t48_prj_"))

from omni_describer_custom.core import timing_store  # noqa: E402
from omni_describer_custom.core.ai_engine import GLMProvider  # noqa: E402
from omni_describer_custom.core.tools import find_tool  # noqa: E402

results: list[tuple[str, bool]] = []


def check(name, fn):
    try:
        fn()
        results.append((name, True))
        print(f"PASS  {name}")
    except Exception as e:
        results.append((name, False))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc()


def _clip(seconds=3) -> Path:
    path = Path(tempfile.mkdtemp(prefix="odc_t48_v_")) / "clip.mp4"
    subprocess.run([find_tool("ffmpeg"), "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"testsrc=size=160x120:rate=5:duration={seconds}",
                    "-c:v", "libx264", str(path)], check=True, timeout=120)
    return path


def test_timing_store_learns():
    key = "glm:test-model"
    assert timing_store.ratio(key) == timing_store.DEFAULT_RATIO
    assert timing_store.expected_seconds(key, 0) == 0.0
    over = timing_store.OVERHEAD_SECONDS
    # The 29 Sep 2026 measurement: 50 s of video, 80 s of waiting.
    assert 60 <= timing_store.expected_seconds(key, 50) <= 100,         timing_store.expected_seconds(key, 50)
    timing_store.record(key, 100.0, over + 50.0)
    assert abs(timing_store.ratio(key) - 0.5) < 1e-6, timing_store.ratio(key)
    timing_store.record(key, 100.0, over + 100.0)
    assert abs(timing_store.ratio(key) - 0.75) < 1e-6, "not an average"
    timing_store.record(key, 2.0, 500.0)
    assert abs(timing_store.ratio(key) - 0.75) < 1e-6, "a 2 s clip moved it"
    assert timing_store.expected_seconds(key, 100) == over + 75.0
    (Path(os.environ["ODC_CONFIG_DIR"]) / "timing.json").write_text("{ broken")
    assert timing_store.ratio(key) == timing_store.DEFAULT_RATIO


def test_chat_streams_with_a_byte_count():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    seen = {}

    class Chat(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            seen["length"] = self.headers.get("Content-Length")
            seen["chunked"] = self.headers.get("Transfer-Encoding")
            seen["body"] = self.rfile.read(int(self.headers["Content-Length"]))
            out = json.dumps({"choices": [{"message": {"content": "[00:01] ok"}}]}
                             ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Chat)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        prov = GLMProvider(api_key="k",
                           base_url=f"http://127.0.0.1:{server.server_address[1]}")
        payload = {"model": "m", "blob": "x" * (3 * 1024 * 1024)}
        shares = []
        text = asyncio.run(prov._chat(payload, timeout=30, on_sent=shares.append))
    finally:
        server.shutdown()
    assert text == "[00:01] ok"
    assert json.loads(seen["body"]) == payload, "the streamed body was damaged"
    assert seen["length"] and not seen["chunked"], seen
    assert len(shares) > 5 and shares == sorted(shares) and shares[-1] == 1.0, shares


def test_a_part_reports_upload_then_the_wait():
    key = "glm:m"
    before = timing_store.ratio(key)
    real = timing_store.OVERHEAD_SECONDS
    timing_store.OVERHEAD_SECONDS = 0.0       # keep the test to seconds
    prov = GLMProvider(api_key="k")
    statuses, reports = [], []

    async def fake_chat(payload, timeout, on_sent=None):
        on_sent(0.5)
        on_sent(1.0)
        await asyncio.sleep(2.5)
        return "[00:01] a thing"
    prov._chat = fake_chat
    try:
        pairs = asyncio.run(prov._describe_one_part(
            _clip(), "p", "m", on_status=statuses.append, is_cancelled=None,
            part_seconds=10.0,
            on_part_progress=lambda f, e: reports.append((f, e))))
    finally:
        timing_store.OVERHEAD_SECONDS = real
    assert pairs == [(1.0, "a thing")], pairs
    assert statuses[-3:] == ["uploading", "waiting", "parsing"], statuses
    upload = [f for f, e in reports if f <= prov.UPLOAD_SHARE]
    wait = [(f, e) for f, e in reports if f > prov.UPLOAD_SHARE]
    assert upload == [0.05, 0.1], upload
    assert len(wait) >= 2, reports
    assert [f for f, _ in wait] == sorted(f for f, _ in wait), "the bar went back"
    assert all(f < 1.0 for f, _ in wait), "a guess reported the part finished"
    etas = [e for _, e in wait]
    assert etas[0] is not None and 0 < etas[0] < 4.0 and etas == sorted(etas, reverse=True), etas
    assert timing_store.ratio(key) != before, "the wait was not learned from"


def test_the_whole_job_moves_one_bar():
    prov = GLMProvider(api_key="k")
    overall = []

    async def fake_chat(payload, timeout, on_sent=None):
        for share in (0.25, 0.5, 1.0):
            on_sent(share)
        await asyncio.sleep(1.2)
        return "[00:01] a"
    prov._chat = fake_chat
    parts = []
    asyncio.run(prov.describe_video_full(
        str(_clip(12)), "p", "m", chunk_seconds=5,
        on_part=lambda i, n: parts.append((i, n)),
        on_eta=lambda pct, eta: overall.append(pct)))
    assert len(parts) >= 2, parts
    assert overall and overall == sorted(overall), overall
    assert 10.0 <= overall[0] < 20.0 and overall[-1] < 100.0, overall


def test_wiring_reaches_the_window():
    src = ROOT / "src" / "omni_describer_custom"
    ui = (src / "ui" / "main_frame.py").read_text(encoding="utf-8")
    engine = (src / "core" / "ai_engine.py").read_text(encoding="utf-8")
    assert "on_eta=veta" in ui, "the window does not ask for progress"
    assert '{"on_eta": on_eta}' in engine, "the engine drops on_eta"


def test_window_bar_and_speech():
    import wx
    import wx.adv  # noqa: F401
    from omni_describer_custom.i18n.strings import I18n, t
    from omni_describer_custom.ui.main_frame import MainFrame
    app = wx.GetApp() or wx.App(False)
    I18n.set_language("en")
    frame = MainFrame()
    frame.Show(False)
    spoken = []
    frame._speak_progress = spoken.append

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            wx.Yield()
            time.sleep(0.02)

    try:
        frame._ensure_download_progress()
        frame._video_part_tick(1, 2)
        assert "10%" in frame.GetStatusBar().GetStatusText(), \
            frame.GetStatusBar().GetStatusText()
        frame._video_status_tick("encoding")
        frame._video_status_tick("uploading")
        pump(1.2)
        assert spoken == [f'{t("video.part_start", part=1, total=2)} '
                          f'{t("video.phase_uploading")}'], spoken
        frame._video_eta_tick(12.0, None)
        frame._video_status_tick("waiting")
        pump(1.2)
        assert len(spoken) == 1, f"the wait was said before its estimate: {spoken}"
        dlg = frame._dl_dialog
        real_update, updates = dlg.Update, []
        dlg.Update = lambda *a: updates.append(a) or real_update(*a)
        frame._video_eta_tick(30.0, 200.0)
        frame._video_eta_tick(31.0, 199.0)
        # Same words a second later: the bar moves, the text is left
        # alone (NVDA re-read unchanged text every second, 1.8.4 run).
        assert [len(a) for a in updates] == [2, 1], updates
        dlg.Update = real_update
        pump(1.2)
        assert len(spoken) == 2 and spoken[1].startswith(t("video.phase_waiting")) \
            and t("video.eta_minutes", minutes=3) in spoken[1], spoken
        status = frame.GetStatusBar().GetStatusText()
        assert t("video.eta_minutes", minutes=3) in status, status
        assert "31%" in frame._dl_dialog.GetTitle(), frame._dl_dialog.GetTitle()
        frame._video_eta_tick(40.0, None)
        assert t("video.eta_over") in frame.GetStatusBar().GetStatusText()
        I18n.set_language("ms")
        assert "minit" in frame._eta_text(600) and frame._eta_text(-1.0) == ""
    finally:
        I18n.set_language("en")
        frame._dl_done = True
        frame._close_download_progress()
        pump(0.5)
        frame.Destroy()
        pump(0.2)
        del app


def main() -> int:
    check("the timing store learns and survives a broken file",
          test_timing_store_learns)
    check("a chat request streams with a byte count",
          test_chat_streams_with_a_byte_count)
    check("a part reports its upload, then its estimated wait",
          test_a_part_reports_upload_then_the_wait)
    check("the whole job moves one bar forward",
          test_the_whole_job_moves_one_bar)
    check("the window asks the engine for progress", test_wiring_reaches_the_window)
    check("the window moves the bar and speaks each phase once",
          test_window_bar_and_speech)
    failed = [n for n, ok in results if not ok]
    print(f"\nRESULT: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
