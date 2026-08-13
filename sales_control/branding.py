from __future__ import annotations

import sys
from pathlib import Path


def app_icon_png_path() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "assets" / "app_icon.png"
    return Path(__file__).resolve().parent.parent / "assets" / "app_icon.png"
