import sys, io, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "src")

from omni_describer_custom.core.ai_engine import AIEngine, CustomProvider, FORMAT_ANTHROPIC
from omni_describer_custom.core.tts_engine import TTSEngine
from omni_describer_custom.core.project_store import ProjectStore, Description
from omni_describer_custom.core.settings_store import SettingsStore
from omni_describer_custom.core.prompt_manager import PromptManager
from omni_describer_custom.core.video_processor import VideoProcessor
from omni_describer_custom.i18n.strings import I18n, t

ok = 0
fail = 0

def check(name, fn):
    global ok, fail
    try:
        fn()
        print(f"PASS: {name}")
        ok += 1
    except Exception as e:
        print(f"FAIL: {name}: {e}")
        traceback.print_exc()
        fail += 1

# 1. Settings store round-trip with temp dir
import tempfile, json
from pathlib import Path

def test_settings():
    with tempfile.TemporaryDirectory() as d:
        s = SettingsStore(config_dir=d)
        s.set_ai_provider("gemini", {"api_key": "test-key-123", "model": "gemini-2.5-flash"})
        s2 = SettingsStore(config_dir=d)
        cfg = s2.get_ai_provider("gemini")
        assert cfg["api_key"] == "test-key-123", cfg
        assert cfg["model"] == "gemini-2.5-flash"
check("settings_store encrypt/decrypt round-trip", test_settings)

# 2. Prompt manager defaults
def test_prompts():
    with tempfile.TemporaryDirectory() as d:
        s = SettingsStore(config_dir=d)
        pm = PromptManager(s)
        names = pm.get_preset_names()
        assert "default" in names, names
        text = pm.get_preset("default")
        assert text, "empty default prompt"
check("prompt_manager defaults", test_prompts)

# 3. Project store CRUD
def test_project_store():
    with tempfile.TemporaryDirectory() as d:
        ps = ProjectStore(projects_dir=d)
        p = ps.create_project("Test Proj", "video.mp4")
        assert p.id == 1, p.id
        desc = Description(start_time=0.0, end_time=2.0, text="Hello")
        added = ps.add_description(desc)
        assert added.id > 0
        p2 = ps.open_project(p.id)
        assert p2 is not None and len(p2.descriptions) == 1
        assert p2.descriptions[0].text == "Hello"
        lst = ps.list_projects()
        assert len(lst) == 1 and lst[0]["name"] == "Test Proj"
        ps.delete_project(p.id)
        assert ps.open_project(p.id) is None
check("project_store CRUD", test_project_store)

# 4. CustomProvider anthropic payload shape (no network)
def test_custom_provider():
    cp = CustomProvider(api_key="k", base_url="https://claude.example.com/v1", model="m1")
    assert cp._detect_format() == FORMAT_ANTHROPIC, cp._detect_format()
    cp2 = CustomProvider(api_key="k", base_url="https://api.example.com/v1", model="m1")
    assert cp2._detect_format() != FORMAT_ANTHROPIC
check("custom provider format detection", test_custom_provider)

# 5. VTT parsing
def test_vtt():
    with tempfile.TemporaryDirectory() as d:
        vtt = Path(d) / "sub.vtt"
        vtt.write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello world\n\n00:00:04.000 --> 00:00:06.000\nSecond line\n",
            encoding="utf-8",
        )
        vp = VideoProcessor(ffmpeg_path="ffmpeg", ytdlp_path="yt-dlp")
        segs = vp._parse_vtt(str(vtt))
        texts = [s.text for s in segs]
        assert "Hello world" in texts, texts
        assert segs[0].start == 1.0 and segs[0].end == 3.0
check("vtt parsing", test_vtt)

# 6. i18n
def test_i18n():
    I18n.set_language("ms")
    assert t("main.ready") == "Sedia"
    I18n.set_language("en")
    assert t("main.ready") == "Ready"
    msg = t("status.no_api_key", provider="opus")
    assert "opus" in msg
check("i18n translations", test_i18n)

# 7. TTS engine init (no actual speech)
def test_tts():
    eng = TTSEngine({})
    avail = eng.get_available_engines()
    print(f"  available TTS engines: {avail}")
    assert isinstance(avail, list)
check("tts engine init", test_tts)

# 8. AI engine provider mgmt
def test_ai_engine():
    eng = AIEngine()
    eng.set_provider("opus", api_key="fake", base_url="https://opus.abhibots.com/v1")
    assert eng.get_available_providers() == ["opus"]
    try:
        eng.describe_frame.__wrapped__ if hasattr(eng.describe_frame, "__wrapped__") else None
    except Exception:
        pass
check("ai engine provider mgmt", test_ai_engine)

print(f"\nRESULT: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
