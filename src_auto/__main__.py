import sys


def _configure_utf8_console():
    """Keep Chinese CLI text readable in Windows PowerShell/Windows Terminal."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            # Some embedded runners expose a read-only or already-closed stream.
            pass


_configure_utf8_console()

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
