from __future__ import annotations

import os
import sys
from ctypes import windll

from rich import box
from rich.console import Console
from rich.table import Table


def configure_terminal() -> None:
    if os.name != "nt":
        return
    try:
        windll.kernel32.SetConsoleOutputCP(65001)
        windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def create_console() -> Console:
    configure_terminal()
    return Console(safe_box=True)


def create_table(title: str) -> Table:
    return Table(title=title, box=box.ASCII, safe_box=True)
