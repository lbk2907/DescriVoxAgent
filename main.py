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

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.info("Logging initialized: %s", log_file)


def main():
    """Application entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Create wx App
    app = wx.App(False)

    # Add src/ to path for package imports (before any omni_describer imports).
    # In a PyInstaller bundle the package lives in the PYZ archive, so the
    # src/ path hack is neither needed nor possible.
    if not getattr(sys, "frozen", False):
        src_dir = str(Path(__file__).parent / "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

    try:
        from omni_describer_custom.ui.main_frame import MainFrame
        frame = MainFrame()
        frame.Show(True)
        frame.Maximize(True)
        logger.info("Application started")
        app.MainLoop()
    except Exception as e:
        logger.error("Application error: %s", e)
        wx.MessageBox(f"Error starting application:\n{e}", "Omni Describer Custom",
                      wx.OK | wx.ICON_ERROR)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
