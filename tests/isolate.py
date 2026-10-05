"""Keep every test away from the owner's real data (pitfall 19).

Imported FIRST by every test script. run_gate.bat already sets these
variables; this module makes a test safe when it is run on its own too.
On 1 Oct 2026 tests run directly (without the gate) wrote a loopback
Gemini URL into the owner's real settings.json, and every Gemini job
failed with "Cannot connect to host 127.0.0.1" until it was found.

setdefault: an isolation the caller already chose (the gate) wins.
"""
import os
import tempfile

for _name, _prefix in (("ODC_CONFIG_DIR", "odc_tcfg_"),
                       ("ODC_PROJECTS_DIR", "odc_tproj_"),
                       ("ODC_LOCALES_DIR", "odc_tloc_"),
                       ("ODC_TOOLS_DIR", "odc_ttools_"),
                       ("ODC_EVIDENCE_DIR", "odc_tevid_")):
    if not os.environ.get(_name):
        os.environ[_name] = tempfile.mkdtemp(prefix=_prefix)
