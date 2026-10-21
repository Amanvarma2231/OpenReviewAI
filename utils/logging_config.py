"""
OpenReview AI - Logging Configuration
====================================
Standardized logging with timestamps, log levels, and clean format.
"""

import logging
import sys
import os
from typing import Optional


def setup_logger(name: str = "OpenReviewAI", level: Optional[str] = None) -> logging.Logger:
    """Configures and returns a named logger instance."""
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO").upper()

    numeric_level = getattr(logging, level, logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(numeric_level)

    # Avoid duplicate handlers if setup_logger is called repeatedly
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(numeric_level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
