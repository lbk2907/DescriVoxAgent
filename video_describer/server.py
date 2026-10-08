"""Zero-dependency HTTP API for the pipeline (stdlib http.server).

Endpoints:
    GET  /health                          -> {"status": "ok"}
    POST /describe        JSON/FORM       -> full pipeline (local path)
    POST /describe/upload?name=v.mp4      -> upload raw video bytes
    POST /parse           {"text": ...}   -> parse only (no AI call)

Options (JSON body fields or query string):
    fps (default 1), tts ("1"/"true"), tts_engine ("edge"|"sapi"),
    model, base_url. API key: header X-API-Key or GLM_API_KEY env.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .pipeline import run_pipeline_sync
from .parse_output import parse_events, require_events


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


class _Handler(BaseHTTPRequestHandler):
    server_version = "VideoDescriber/0.1"

    def log_message(self, *a):  # quiet
        pass

    # ── helpers ──────────────────────────────────────────────────
    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _query(self) -> dict:
        parsed = urlparse(self.path)
        return parsed.path, {k: v[0] for k, v in
                             parse_qs(parsed.query).items()}

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        ctype = (self.headers.get("Content-Type") or "").lower()
        if "json" in ctype or not ctype:
            try:
                return json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return {}
        # form-encoded
        return {k: v[0] for k, v in parse_qs(raw.decode("utf-8")).items()}

    # ── routes ───────────────────────────────────────────────────
    def do_GET(self):
        path, _ = self._query()
        if path in ("/health", "/"):
            return self._send(200, {"status": "ok", "version": "0.1"})
        self._send(404, {"error": f"no route {path}"})

    def do_POST(self):
        path, qs = self._query()
        try:
            if path == "/describe":
                return self._describe(self._body(), qs)
            if path == "/describe/upload":
                return self._describe_upload(qs)
            if path == "/parse":
                body = self._body()
                text = body.get("text", "")
                events = require_events(text) if _truthy(
                    qs.get("strict")) else parse_events(text)
                return self._send(200, {
                    "events": [{"start": s, "description": t}
                               for s, t in events]})
            self._send(404, {"error": f"no route {path}"})
        except (ValueError, RuntimeError) as e:
            self._send(400, {"error": str(e)[:400]})
        except Exception as e:  # noqa: BLE001 - report, never crash server
            self._send(500, {"error": str(e)[:400]})

    # ── pipeline calls (threaded by ThreadingHTTPServer) ─────────
    def _describe(self, body: dict, qs: dict) -> None:
        video = body.get("video_path") or qs.get("video_path")
        if not video:
            return self._send(400, {"error": "video_path required"})
        result = run_pipeline_sync(
            video, _workdir(),
            api_key=self._api_key(body),
            base_url=body.get("base_url") or qs.get("base_url") or
            "https://open.bigmodel.cn/api/paas/v4",
            model=body.get("model") or qs.get("model") or "glm-5.3-flash",
            fps=float(body.get("fps", qs.get("fps", 1))),
            tts=_truthy(body.get("tts", qs.get("tts", False))),
            tts_engine=body.get("tts_engine") or qs.get("tts_engine") or "edge",
        )
        self._send(200, self._payload(result))

    def _describe_upload(self, qs: dict) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return self._send(400, {"error": "empty upload"})
        name = os.path.basename(qs.get("name") or "upload.mp4")
        work = _workdir()
        video = work / name
        remaining = length
        with open(video, "wb") as fh:
            while remaining > 0:
                chunk = self.rfile.read(min(1 << 20, remaining))
                if not chunk:
                    break
                fh.write(chunk)
                remaining -= len(chunk)
        result = run_pipeline_sync(
            video, work,
            api_key=self._api_key({}),
            base_url=qs.get("base_url") or
            "https://open.bigmodel.cn/api/paas/v4",
            model=qs.get("model") or "glm-5.3-flash",
            fps=float(qs.get("fps", 1)),
            tts=_truthy(qs.get("tts", False)),
            tts_engine=qs.get("tts_engine") or "edge",
            keep_frames=False,
        )
        self._send(200, self._payload(result))

    def _api_key(self, body: dict) -> str:
        return (body.get("api_key")
                or self.headers.get("X-API-Key")
                or os.environ.get("GLM_API_KEY", ""))

    @staticmethod
    def _payload(result) -> dict:
        return {
            "events": [{"start": s, "description": t}
                       for s, t in result.events],
            "srt": str(result.srt_path or ""),
            "json": str(result.json_path or ""),
            "audio_dir": str(result.audio_dir or ""),
            "frames": len(result.frames),
            "batches": result.batches,
        }


def _workdir() -> Path:
    d = Path(tempfile.gettempdir()) / "video_describer_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


class _Server(ThreadingHTTPServer):
    daemon_threads = True


def make_server(host: str = "127.0.0.1", port: int = 8765) -> _Server:
    """Build (not start) the server; exported for tests."""
    return _Server((host, port), _Handler)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = make_server(host, port)
    print(f"video_describer API on http://{host}:{port} (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
