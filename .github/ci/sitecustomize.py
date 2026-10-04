"""CI headless guard, loaded via PYTHONPATH in .github/workflows/ci.yml.

The light CI job runs only the gate scripts that were proven to pass with
NO GUI and NO network. This guard keeps it that way: importing wx/vlc or
opening a socket fails loudly instead of silently needing a desktop or the
internet. The full gate (run_gate.bat / `pytest tests`) stays local.
"""
import builtins
import socket

_real_import = builtins.__import__


def _guarded_import(name, *args, **kwargs):
    if name == "wx" or name.startswith("wx.") or name == "vlc":
        raise ImportError(f"CI-HEADLESS: {name} is blocked in the light CI job")
    return _real_import(name, *args, **kwargs)


def _no_network(*args, **kwargs):
    raise OSError("CI-HEADLESS: network is blocked in the light CI job")


builtins.__import__ = _guarded_import
socket.socket.connect = _no_network
socket.create_connection = _no_network
socket.getaddrinfo = _no_network
