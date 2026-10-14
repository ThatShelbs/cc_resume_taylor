"""Talking to the operating system: is Word installed (for PDF export), and open a
folder in the file manager."""

import os
import subprocess
import sys
from pathlib import Path

from ..storage.fs import plain_path


def word_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID"))
        return True
    except OSError:
        return False


def open_path(target: Path) -> None:
    """Open a folder in the system file manager, creating it first if needed."""
    target.mkdir(parents=True, exist_ok=True)
    target = plain_path(target)
    if sys.platform == "win32":
        os.startfile(str(target))  # noqa: S606 - opening a local folder for the user
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
