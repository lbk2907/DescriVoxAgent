"""
Omni Describer Custom — Entry point.

Accessible audio description tool for the blind and visually impaired.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import wx
import wx.adv


def setup_logging():
    """Configure application logging."""
    log_dir = Path.home() / "AppData" / "Local" / "OmniDescriber" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "omni_describer.log"

    handlers = [logging.FileHandler(log_file, encoding="utf-8")]
    # Under a windowed PyInstaller build sys.stdout/stderr are None; a
    # StreamHandler on None silently drops all console log output.
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.info("Logging initialized: %s", log_file)


def main():
    """Application entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Windowed PyInstaller builds have no stderr, so unhandled exceptions
    # (e.g. inside wx event handlers after MainLoop starts) would vanish
    # silently. Route them into the log file instead.
    def _log_unhandled(exc_type, exc_value, exc_tb):
        logger.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _log_unhandled

    # Create wx App
    app = wx.App(False)

    # Add src/ to path for package imports (before any omni_describer imports).
    # In a PyInstaller bundle the package lives in the PYZ archive, so the
    # src/ path hack is neither needed nor possible.
    if not getattr(sys, "frozen", False):
        src_dir = str(Path(__file__).parent / "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

    # Before anything can start ffmpeg or yt-dlp: no console windows.
    from omni_describer_custom.core.no_console import install as _no_console
    _no_console()

    try:
        # v1.6.5: ffmpeg and friends ship with the app now, but a
        # corrupted unzip or an antivirus quarantine can still remove
        # them. Say so once, plainly, instead of letting each feature
        # fail separately later with its own obscure error.
        from omni_describer_custom.core.tools import (
            log_tool_status, missing_tools)
        log_tool_status()
        absent = missing_tools()
        if absent:
            detail = "\n".join(f"• {name} — needed for {why}"
                               for name, why in absent)
            logger.error("Missing external tools:\n%s", detail)
            wx.MessageBox(
                "Some programs this app needs are missing:\n\n"
                f"{detail}\n\n"
                "They normally ship inside the app's own bin folder. If "
                "that folder is empty, the download or unzip did not "
                "finish, or antivirus removed the files. Re-extract the "
                "app, or install ffmpeg and yt-dlp yourself.\n\n"
                "The app will still start, but these features will fail.",
                "Omni Describer Custom", wx.OK | wx.ICON_WARNING)

        # v1.6.7: a crashed or killed run leaves its temp folders
        # behind and nothing ever came back for them — 806 MB of
        # abandoned downloads had built up on the author's machine.
        # Only this app's own folders, only ones a day old or more.
        try:
            from omni_describer_custom.core.housekeeping import (
                sweep_stale_temp)
            sweep_stale_temp()
        except Exception as e:
            logger.warning("Temp cleanup skipped: %s", e)

        from omni_describer_custom.ui.main_frame import MainFrame
        frame = MainFrame()
        frame.Show(True)
        frame.Maximize(True)
        logger.info("Application started")
        # v1.7.7: once a week, say if a newer yt-dlp exists. Late, so it
        # never competes with the window's own start-up announcements.
        wx.CallLater(8000, frame.check_updates_in_background)
        app.MainLoop()
    except Exception as e:
        logger.error("Application error: %s", e)
        wx.MessageBox(f"Error starting application:\n{e}", "Omni Describer Custom",
                      wx.OK | wx.ICON_ERROR)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
