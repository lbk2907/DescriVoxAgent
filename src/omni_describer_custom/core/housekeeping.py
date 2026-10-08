"""Clear up after runs that did not get to clear up after themselves.

The pipeline makes temporary directories for downloads, frames, split
parts and compressed upload copies. Each phase deletes its own on the
way out — but a crash, a kill, or a machine that loses power skips
that, and nothing ever came back for the remains.

Measured on the author's machine, 22 Sep 2026, before this existed:

    odc_video_*      115 directories   806 MB
    odc_frames_*     120 directories     2 MB
    odc_vsplit_*       1 directory       1 MB

v1.6.7 stopped downloads landing in a throwaway directory at all, so
the largest source is gone going forward. This removes what earlier
versions left, and keeps a crash from accumulating again.

Deliberately conservative: only directories this app names, only ones
untouched for a day, and never the one in use right now. A sweep that
might delete live work is worse than a full disk.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Prefixes this app creates with tempfile.mkdtemp. Anything else in the
# temp folder belongs to somebody else and is not ours to remove.
_OUR_PREFIXES = (
    "odc_video_",  # downloads (pre-v1.6.7 and non-GUI callers)
    "odc_frames_",  # extracted frames
    "odc_vcompress_",  # compressed upload copies without a project
    "odc_vsplit_",  # split parts for chunked upload
    "odc_sub_",  # subtitle fetches from yt-dlp
    "odc_esub_",  # subtitles pulled out of a local file
    "odc_explorer_",  # frames written for the scene explorer
    "odc_probe_",  # Settings > Test this model (v1.8.1)
    "odc_review_",  # frames for checking descriptions (v1.8.8)
    "odc_agent_",  # the Player agent's frames (v1.9.0)
)

# A day: long enough that a paused job, a slow download or a user who
# left the app open overnight is never touched.
_MIN_AGE_SECONDS = 24 * 60 * 60


def sweep_stale_temp(
    min_age_seconds: int = _MIN_AGE_SECONDS, temp_dir: str = ""
) -> tuple[int, int]:
    """Remove our abandoned temp directories. Returns (count, bytes).

    Never raises: housekeeping must not stop the app from starting.
    """
    root = Path(temp_dir or tempfile.gettempdir())
    cutoff = time.time() - max(0, min_age_seconds)
    removed = 0
    freed = 0
    try:
        candidates = list(root.iterdir())
    except OSError as e:
        logger.debug("Could not read the temp folder: %s", e)
        return (0, 0)

    for path in candidates:
        try:
            if not path.is_dir() or not path.name.startswith(_OUR_PREFIXES):
                continue
            if path.stat().st_mtime > cutoff:
                continue  # recent: could be a job running right now
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            shutil.rmtree(path, ignore_errors=True)
            if path.exists():
                continue  # in use, or locked — leave it alone
            removed += 1
            freed += size
        except OSError:
            continue  # locked by another process: not ours to force

    if removed:
        logger.info("Cleared %d abandoned temp folder(s), %.0f MB freed", removed, freed / 1e6)
    return (removed, freed)
