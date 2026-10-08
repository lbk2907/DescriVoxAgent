"""Keystrokes that can only land in the app under test.

28 Sep 2026: a Scene Explorer check failed to take focus, and the keys
it sent (arrows, "d", "l", Enter) went to whatever the owner had in
front — a chat app's message box. Enter may have sent a stray message.

Importing this module replaces pywinauto.keyboard.send_keys with a
guarded version: before every call it checks that the foreground window
belongs to a process registered with allow(), and raises ForeignFocus
without typing anything otherwise. With nothing registered it refuses
outright, so a tool that forgets to register cannot type at all.

Import it BEFORE any "from pywinauto.keyboard import send_keys".
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

import pywinauto.keyboard as _keyboard

_user32 = ctypes.windll.user32
_allowed: set[int] = set()
_original = getattr(_keyboard, "_odc_original_send_keys", _keyboard.send_keys)


class ForeignFocus(RuntimeError):
    """The foreground window is not the app under test; nothing typed."""


def allow(*pids: int) -> None:
    _allowed.update(int(p) for p in pids if p)


def foreground() -> tuple[int, str]:
    hwnd = _user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(hwnd, buf, 256)
    return pid.value, buf.value


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def keyboard_focus() -> tuple[int, str]:
    """(pid, title) of the control that really receives keystrokes.

    2 Oct 2026: the foreground check passed and the keys still landed in
    the Claude desktop app's message box (arrows, Space). The control
    holding the KEYBOARD focus is what counts, so it is checked too."""
    info = _GUITHREADINFO()
    info.cbSize = ctypes.sizeof(_GUITHREADINFO)
    if not _user32.GetGUIThreadInfo(0, ctypes.byref(info)) or not info.hwndFocus:
        return 0, ""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(info.hwndFocus, ctypes.byref(pid))
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(info.hwndFocus, buf, 256)
    return pid.value, buf.value


def send_keys(keys, *args, **kwargs):
    if not _allowed:
        raise ForeignFocus("no test process registered with safe_keys.allow()")
    # Checked for EVERY key: a multi-key string is sent one key at a time,
    # so focus taken away half way stops the rest.
    pid, title = foreground()
    if pid not in _allowed:
        raise ForeignFocus(
            f"refusing to type {keys!r}: the foreground window "
            f"({title!r}, pid {pid}) is not the app under test"
        )
    fpid, ftitle = keyboard_focus()
    if fpid not in _allowed:
        raise ForeignFocus(
            f"refusing to type {keys!r}: the keyboard focus "
            f"({ftitle!r}, pid {fpid}) is not in the app under test"
        )
    return _original(keys, *args, **kwargs)


_keyboard._odc_original_send_keys = _original
_keyboard.send_keys = send_keys
