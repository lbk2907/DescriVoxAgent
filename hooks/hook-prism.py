"""Ship Prism's native extension, which PyInstaller cannot see.

prism/_native.py appends prism/_native/ to the package __path__ AT
RUNTIME, so `prism._prism_cffi` becomes importable from a directory no
static analysis ever walks. PyInstaller therefore collected the .py
files and prism.dll and silently dropped _prism_cffi.pyd — the frozen
app started fine and logged

    Prism speech unavailable: prism not installed
    (No module named 'prism._prism_cffi')

meaning the whole screen-reader voice added in v1.6.6 was dead in the
shipped build while every test passed. Found by reading the frozen
app's own log during a real run, 22 Sep 2026.

Everything in _native/ is copied verbatim, keeping the layout the
runtime path trick depends on.
"""

import os

from PyInstaller.utils.hooks import get_package_paths

_, package_dir = get_package_paths("prism")
_native = os.path.join(package_dir, "_native")

binaries = []
datas = []
if os.path.isdir(_native):
    for name in sorted(os.listdir(_native)):
        source = os.path.join(_native, name)
        if not os.path.isfile(source):
            continue
        # .pyd and .dll must be binaries so PyInstaller fixes up their
        # dependencies; .lib and anything else rides along as data.
        if name.lower().endswith((".pyd", ".dll")):
            binaries.append((source, "prism/_native"))
        else:
            datas.append((source, "prism/_native"))

# The extension is imported under the PACKAGE name, not the file's
# location, because of the __path__ append.
hiddenimports = ["prism._prism_cffi", "prism._native", "_cffi_backend"]
