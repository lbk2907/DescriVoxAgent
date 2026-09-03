"""Debug: probe + split a 7s clip directly."""
import glob
import sys
sys.path.insert(0, "src")
from pathlib import Path
from omni_describer_custom.core.ai_engine import GLMProvider

p = GLMProvider(api_key="k")
clips = glob.glob(str(Path.home() / "AppData/Local/Temp/odc_chunktest_*/clip7.mp4"))
print("clips found:", clips)
clip = Path(clips[0])
print("probe:", p._probe_duration(clip))
starts, parts = p.split_video_for_upload(clip, 3)
print("starts:", starts)
print("parts:", [x.name for x in parts])
for x in parts:
    print("  part dur:", p._probe_duration(x), "size:", x.stat().st_size)
