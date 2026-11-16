"""Run with `uv run python -m boaz`."""

import logging
import argparse
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Boaz farming workspace")
    parser.add_argument("--open-browser", action="store_true", help="Open the dashboard, reusing an existing Boaz server")
    options = parser.parse_args()
    if options.open_browser and open_existing():
        return
    local = Path.cwd() / "local"
    (local / "logs").mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(local / "logs" / "boaz.log", maxBytes=1000000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger("boaz")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    from .dashboard import serve

    serve(local, open_browser=options.open_browser)


def open_existing():
    url = "http://127.0.0.1:8080"
    try:
        with urlopen(url, timeout=2) as response:
            if b"<title>Boaz" not in response.read(65536):
                raise RuntimeError("Port 8080 is occupied by another application. Close it before starting Boaz.")
    except (URLError, TimeoutError):
        return False
    webbrowser.open(url)
    return True


if __name__ == "__main__":
    main()
