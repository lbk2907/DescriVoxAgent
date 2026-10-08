"""Hear when a screen reader stops talking, on any version of it.

The player's narration hold pauses the video while a description is
spoken and resumes it when the speech ends. For voices the app renders
itself that is easy — it plays the file and knows when the file ends.
A screen reader gives no such signal: Prism hands it the text and
returns at once.

NVDA 2024.1 added a synchronous speakSsml that is meant to block until
the speech is done. Measured on this machine's NVDA 2025.3 it HUNG on
the first call and never returned — the race NV Access fixed only in
2026.2 (nvaccess/nvda#20220), and a normal keypress in NVDA is enough
to trigger it. isSpeaking arrives in 2026.3, which is not yet released.
So an API answer would work only for users on the newest NVDA.

This listens instead. Windows keeps a peak-level meter on every audio
session, and every session belongs to a process. When the reader's
process goes quiet, the sentence is over. Measured, speaking through
Prism to NVDA 2025.3:

    6 words   sound ended at 0.98 s
   23 words   sound ended at 4.03 s

It needs nothing from the screen reader beyond making sound, so it does
not depend on the reader's version at all.

Two things learned the hard way, both kept in the code below:

- Search EVERY output device, not the default one. NVDA here is routed
  to device 0 while the Windows default is device 1 — a common setup
  for a blind user who keeps speech apart from media — and a
  default-only search found no NVDA session at all.
- Find the meter BEFORE speaking. Looking it up afterwards missed
  short sentences outright: the lookup used tasklist, which took 0.83 s,
  and a three-word description is over in half a second at this user's
  NVDA rate. The name now comes straight from Win32 (about 0.03 s for
  the whole search), and the search runs before the speech starts.
- A reader has no audio session until it has spoken once since it
  started, so if none exists beforehand it is searched for again while
  listening.

Built on comtypes, which the app already bundles; no new dependency.
"""

from __future__ import annotations

import ctypes
import logging
import time
from ctypes import HRESULT, POINTER, byref, c_float, c_uint, c_void_p
from ctypes.wintypes import BOOL, DWORD, LPCWSTR

logger = logging.getLogger(__name__)

# Above this peak level the reader is making sound. Measured baseline
# for a silent NVDA session: 0.000; while speaking: 0.18 to 0.30.
SPEAKING_LEVEL = 0.01

# Silence must last this long before the speech counts as finished.
# A reader pauses at commas and full stops for well under this, so a
# sentence is not cut off at its own punctuation.
SILENCE_TO_FINISH = 0.6

# If no sound appears within this long after speaking, the meter is not
# hearing this reader (muted, routed elsewhere, unusual audio path) and
# the caller should fall back rather than wait for sound that will
# never come.
START_GRACE = 1.5

_POLL = 0.03

try:
    import comtypes
    from comtypes import COMMETHOD, GUID, IUnknown

    _CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")

    class _IAudioMeterInformation(IUnknown):
        _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetPeakValue", (["out"], POINTER(c_float), "peak")),
            COMMETHOD([], HRESULT, "GetMeteringChannelCount", (["out"], POINTER(c_uint), "n")),
            COMMETHOD(
                [],
                HRESULT,
                "GetChannelsPeakValues",
                (["in"], c_uint, "n"),
                (["in"], POINTER(c_float), "v"),
            ),
            COMMETHOD([], HRESULT, "QueryHardwareSupport", (["out"], POINTER(DWORD), "mask")),
        ]

    class _IAudioSessionControl(IUnknown):
        _iid_ = GUID("{F4B1A599-7266-4319-A8CA-E70ACB11E8CD}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetState", (["out"], POINTER(c_uint), "s")),
            COMMETHOD([], HRESULT, "GetDisplayName", (["out"], POINTER(ctypes.c_wchar_p), "n")),
            COMMETHOD(
                [], HRESULT, "SetDisplayName", (["in"], LPCWSTR, "v"), (["in"], POINTER(GUID), "c")
            ),
            COMMETHOD([], HRESULT, "GetIconPath", (["out"], POINTER(ctypes.c_wchar_p), "p")),
            COMMETHOD(
                [], HRESULT, "SetIconPath", (["in"], LPCWSTR, "v"), (["in"], POINTER(GUID), "c")
            ),
            COMMETHOD([], HRESULT, "GetGroupingParam", (["out"], POINTER(GUID), "g")),
            COMMETHOD(
                [],
                HRESULT,
                "SetGroupingParam",
                (["in"], POINTER(GUID), "g"),
                (["in"], POINTER(GUID), "c"),
            ),
            COMMETHOD([], HRESULT, "RegisterAudioSessionNotification", (["in"], c_void_p, "n")),
            COMMETHOD([], HRESULT, "UnregisterAudioSessionNotification", (["in"], c_void_p, "n")),
        ]

    class _IAudioSessionControl2(_IAudioSessionControl):
        _iid_ = GUID("{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}")
        _methods_ = [
            COMMETHOD(
                [], HRESULT, "GetSessionIdentifier", (["out"], POINTER(ctypes.c_wchar_p), "i")
            ),
            COMMETHOD(
                [],
                HRESULT,
                "GetSessionInstanceIdentifier",
                (["out"], POINTER(ctypes.c_wchar_p), "i"),
            ),
            COMMETHOD([], HRESULT, "GetProcessId", (["out"], POINTER(DWORD), "pid")),
            COMMETHOD([], HRESULT, "IsSystemSoundsSession"),
            COMMETHOD([], HRESULT, "SetDuckingPreference", (["in"], BOOL, "o")),
        ]

    class _IAudioSessionEnumerator(IUnknown):
        _iid_ = GUID("{E2F5BB11-0570-40CA-ACDD-3AA01277DEE8}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(ctypes.c_int), "n")),
            COMMETHOD(
                [],
                HRESULT,
                "GetSession",
                (["in"], ctypes.c_int, "i"),
                (["out"], POINTER(POINTER(_IAudioSessionControl)), "s"),
            ),
        ]

    class _IAudioSessionManager2(IUnknown):
        _iid_ = GUID("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
        _methods_ = [
            COMMETHOD(
                [],
                HRESULT,
                "GetAudioSessionControl",
                (["in"], POINTER(GUID), "g"),
                (["in"], DWORD, "f"),
                (["out"], POINTER(c_void_p), "c"),
            ),
            COMMETHOD(
                [],
                HRESULT,
                "GetSimpleAudioVolume",
                (["in"], POINTER(GUID), "g"),
                (["in"], DWORD, "f"),
                (["out"], POINTER(c_void_p), "v"),
            ),
            COMMETHOD(
                [],
                HRESULT,
                "GetSessionEnumerator",
                (["out"], POINTER(POINTER(_IAudioSessionEnumerator)), "e"),
            ),
            COMMETHOD([], HRESULT, "RegisterSessionNotification", (["in"], c_void_p, "n")),
            COMMETHOD([], HRESULT, "UnregisterSessionNotification", (["in"], c_void_p, "n")),
            COMMETHOD(
                [],
                HRESULT,
                "RegisterDuckNotification",
                (["in"], LPCWSTR, "s"),
                (["in"], c_void_p, "n"),
            ),
            COMMETHOD([], HRESULT, "UnregisterDuckNotification", (["in"], c_void_p, "n")),
        ]

    class _IMMDevice(IUnknown):
        _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
        _methods_ = [
            COMMETHOD(
                [],
                HRESULT,
                "Activate",
                (["in"], POINTER(GUID), "iid"),
                (["in"], DWORD, "ctx"),
                (["in"], c_void_p, "p"),
                (["out"], POINTER(c_void_p), "i"),
            ),
            COMMETHOD(
                [],
                HRESULT,
                "OpenPropertyStore",
                (["in"], DWORD, "a"),
                (["out"], POINTER(c_void_p), "p"),
            ),
            COMMETHOD([], HRESULT, "GetId", (["out"], POINTER(ctypes.c_wchar_p), "i")),
            COMMETHOD([], HRESULT, "GetState", (["out"], POINTER(DWORD), "s")),
        ]

    class _IMMDeviceCollection(IUnknown):
        _iid_ = GUID("{0BD7A1BE-7A1A-44DB-8397-CC5392387B5E}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(c_uint), "n")),
            COMMETHOD(
                [],
                HRESULT,
                "Item",
                (["in"], c_uint, "i"),
                (["out"], POINTER(POINTER(_IMMDevice)), "d"),
            ),
        ]

    class _IMMDeviceEnumerator(IUnknown):
        _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        _methods_ = [
            COMMETHOD(
                [],
                HRESULT,
                "EnumAudioEndpoints",
                (["in"], c_uint, "flow"),
                (["in"], DWORD, "mask"),
                (["out"], POINTER(POINTER(_IMMDeviceCollection)), "d"),
            ),
            COMMETHOD(
                [],
                HRESULT,
                "GetDefaultAudioEndpoint",
                (["in"], c_uint, "flow"),
                (["in"], c_uint, "role"),
                (["out"], POINTER(POINTER(_IMMDevice)), "d"),
            ),
        ]

    _AVAILABLE = True
except Exception as _e:  # not Windows, or comtypes missing
    logger.info("Audio metering unavailable: %s", _e)
    _AVAILABLE = False

_eRender = 0
_DEVICE_STATE_ACTIVE = 1


def available() -> bool:
    return _AVAILABLE


def _process_name(pid: int) -> str:
    """Image name of a process, straight from Win32.

    Replaces a tasklist call that took 0.83 s — longer than a short
    description takes NVDA to say. By the time tasklist answered, a
    three-word sentence was already over and the meter reported that it
    had heard nothing.
    """
    if pid <= 0:
        return ""
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, byref(size)):
            return buf.value.rsplit("\\", 1)[-1]
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _meters(image_names: tuple[str, ...]) -> list:
    """Peak meters for these processes on every active output device.

    Every device, because a reader is often routed apart from media —
    NVDA here is on device 0 while the Windows default is device 1.
    Measured cost: about 0.03 s for three devices.
    """
    if not _AVAILABLE or not image_names:
        return []
    wanted = {name.lower() for name in image_names}
    found = []
    names: dict[int, str] = {}
    enum = comtypes.CoCreateInstance(
        _CLSID_MMDeviceEnumerator, _IMMDeviceEnumerator, comtypes.CLSCTX_ALL
    )
    devices = enum.EnumAudioEndpoints(_eRender, _DEVICE_STATE_ACTIVE)
    for d in range(devices.GetCount()):
        try:
            raw = devices.Item(d).Activate(
                byref(_IAudioSessionManager2._iid_), comtypes.CLSCTX_ALL, None
            )
            manager = ctypes.cast(raw, POINTER(_IAudioSessionManager2))
            sessions = manager.GetSessionEnumerator()
            for i in range(sessions.GetCount()):
                control = sessions.GetSession(i)
                try:
                    pid = control.QueryInterface(_IAudioSessionControl2).GetProcessId()
                except Exception:
                    continue
                if pid not in names:
                    names[pid] = _process_name(pid).lower()
                if names[pid] in wanted:
                    found.append(control.QueryInterface(_IAudioMeterInformation))
        except Exception as e:
            logger.debug("Skipping an audio device: %s", e)
    return found


class ReaderMeter:
    """Watches the audio of one screen reader's process."""

    def __init__(self, image_names: tuple[str, ...]):
        self.image_names = image_names

    def speak_and_wait(self, speak, timeout: float) -> str:
        """Find the meter, THEN speak, then listen for the end.

        The order matters. Looking the session up after speaking missed
        short sentences entirely: a three-word description is over in
        half a second at this user's NVDA rate.

        Returns why it stopped waiting, so the caller can log the truth:
          "finished"  sound was heard and then silence held
          "no-sound"  nothing was heard at all — caller should fall back
          "timeout"   still talking at the limit — let the video go on
          "no-meter"  metering is not possible here — caller falls back
          "not-spoken" the speak callable reported failure
        Never raises, and never waits longer than `timeout`.
        """
        if not _AVAILABLE:
            return "no-meter" if speak() else "not-spoken"
        initialised = False
        try:
            comtypes.CoInitialize()
            initialised = True
        except Exception:
            pass  # already initialised on this thread
        try:
            try:
                meters = _meters(self.image_names)
            except Exception as e:
                logger.debug("Audio meter lookup failed: %s", e)
                meters = []
            if not speak():
                return "not-spoken"
            return self._listen(meters, timeout)
        except Exception as e:
            logger.debug("Audio meter failed: %s", e)
            return "no-meter"
        finally:
            if initialised:
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass

    def _listen(self, meters: list, timeout: float) -> str:
        t0 = time.monotonic()
        heard = False
        quiet_since: float | None = None
        while time.monotonic() - t0 < timeout:
            now = time.monotonic()
            # A reader has no session until it first speaks since it
            # started; if none existed before speaking, look again now.
            if not meters:
                meters = _meters(self.image_names)
                if not meters:
                    if now - t0 > START_GRACE:
                        return "no-sound"
                    time.sleep(0.05)
                    continue
            level = max((m.GetPeakValue() for m in meters), default=0.0)
            if level > SPEAKING_LEVEL:
                heard = True
                quiet_since = None
            elif heard:
                if quiet_since is None:
                    quiet_since = now
                elif now - quiet_since >= SILENCE_TO_FINISH:
                    return "finished"
            elif now - t0 > START_GRACE:
                return "no-sound"
            time.sleep(_POLL)
        return "timeout"
