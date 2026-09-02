"""CLI: python -m video_describer describe|parse|serve ..."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="video_describer",
        description="Burn-in timestamp frames -> one GLM-5.3-Flash "
                    "request -> parse -> SRT/JSON (+TTS) / HTTP API")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_desc = sub.add_parser("describe", help="describe a local video")
    p_desc.add_argument("video", help="path to the video file")
    p_desc.add_argument("--out", default="",
                        help="output dir (default: alongside the video)")
    p_desc.add_argument("--fps", type=float, default=1.0)
    p_desc.add_argument("--model", default="glm-5.3-flash")
    p_desc.add_argument("--base-url", default="https://open.bigmodel.cn/api/paas/v4")
    p_desc.add_argument("--api-key", default="",
                        help="or set GLM_API_KEY env var")
    p_desc.add_argument("--tts", action="store_true",
                        help="also synthesize narration audio")
    p_desc.add_argument("--tts-engine", choices=["edge", "sapi"], default="edge")
    p_desc.add_argument("--voice", default="ms-MY-OsmanNeural")
    p_desc.add_argument("--keep-frames", action="store_true")

    p_parse = sub.add_parser("parse", help="parse model text only")
    p_parse.add_argument("file", help="text file with H:MM:SS lines "
                                      "('-' for stdin)")

    p_serve = sub.add_parser("serve", help="start the HTTP API")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)

    if args.cmd == "describe":
        api_key = args.api_key or __import__("os").environ.get("GLM_API_KEY", "")
        if not api_key:
            print("GLM_API_KEY env var (or --api-key) required", file=sys.stderr)
            return 2
        out = (Path(args.out) if args.out
               else Path(args.video).parent / Path(args.video).stem)
        from .pipeline import run_pipeline
        result = asyncio.new_event_loop().run_until_complete(run_pipeline(
            args.video, out, api_key=api_key, base_url=args.base_url,
            model=args.model, fps=args.fps, tts=args.tts,
            tts_engine=args.tts_engine, tts_voice=args.voice,
            keep_frames=args.keep_frames))
        print(f"Events: {len(result.events)} (batches: {result.batches})")
        for s, t in result.events[:20]:
            h, rem = divmod(int(s), 3600)
            m, sec = divmod(rem, 60)
            print(f"  {h}:{m:02d}:{sec:02d} - {t}")
        if len(result.events) > 20:
            print(f"  ... and {len(result.events) - 20} more")
        print(f"SRT : {result.srt_path}")
        print(f"JSON: {result.json_path}")
        if result.audio_dir:
            print(f"Audio: {result.audio_dir}")
        return 0

    if args.cmd == "parse":
        text = (sys.stdin.read() if args.file == "-"
                else Path(args.file).read_text(encoding="utf-8"))
        from .parse_output import parse_events, to_srt
        events = parse_events(text)
        print(json.dumps({"events": [
            {"start": s, "description": t} for s, t in events]}, indent=2))
        print("\n--- SRT preview ---")
        print(to_srt(events))
        return 0

    if args.cmd == "serve":
        from .server import serve
        serve(args.host, args.port)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
