"""Per-run logging: every CLI invocation gets its own timestamped log file.

`configure_logging` wires the ``jd_analyser`` logger to write to both stdout
(plain, matching the previous ``print`` output) and a new file under
``LOG_DIR`` named after the run's start time.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from jd_analyser.config import LOG_DIR


def configure_logging(log_dir: Path = LOG_DIR) -> Path:
    """Set up the ``jd_analyser`` logger and return the path of its log file."""
    log_dir.mkdir(parents=True, exist_ok=True)
    filename = datetime.now().strftime("%Y-%m-%dT%H-%M-%S") + ".log"
    log_path = log_dir / filename

    logger = logging.getLogger("jd_analyser")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(file_handler)

    return log_path
