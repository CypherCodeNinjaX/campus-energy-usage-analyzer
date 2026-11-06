"""Application entry point.

Run from the repository root (after `pip install -r requirements.txt`):
    python -m campus_energy.main
"""
from __future__ import annotations

import logging

from .config import LOG_FILE


def setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))
    except OSError:
        pass  # logging to file is optional (e.g. read-only home directory)
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    setup_logging()
    from .dashboard import EnergyApp   # imported here so tests of logic never need Tk
    app = EnergyApp()
    app.mainloop()


if __name__ == "__main__":
    main()
