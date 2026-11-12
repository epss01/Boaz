"""Run with `uv run python -m boaz`."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def main():
    local = Path.cwd() / "local"
    (local / "logs").mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(local / "logs" / "boaz.log", maxBytes=1000000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger("boaz")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    from .dashboard import serve

    serve(local)


if __name__ == "__main__":
    main()
