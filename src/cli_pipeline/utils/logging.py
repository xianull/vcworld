#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Structured logging for pipeline stages.

Replaces scattered print() calls with JSON-structured log entries
that can be parsed by agents and monitoring tools.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, Dict, Optional


def _setup_root_logger() -> None:
    """Configure the root logger once (idempotent)."""
    root = logging.getLogger("vcworld")
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_setup_root_logger()


class StageLogger:
    """Structured logger for a single pipeline stage.

    Usage::

        log = StageLogger("retrieve")
        log.start(data_csv="path/to/data.csv", budget=10)
        log.progress(current=5, total=100)
        log.complete(cases=100, output="path/to/out.json")

    All entries are emitted as single-line JSON to stderr.
    """

    def __init__(self, stage: str) -> None:
        self.stage = stage
        self._logger = logging.getLogger(f"vcworld.{stage}")
        self._start_time: Optional[float] = None

    def _emit(self, status: str, data: Optional[Dict[str, Any]] = None) -> None:
        entry: Dict[str, Any] = {
            "stage": self.stage,
            "status": status,
        }
        if self._start_time is not None:
            entry["elapsed_s"] = round(time.time() - self._start_time, 2)
        if data:
            entry["data"] = data
        self._logger.info(json.dumps(entry, ensure_ascii=False))

    def start(self, **kwargs: Any) -> None:
        """Log stage start with optional context."""
        self._start_time = time.time()
        self._emit("start", kwargs if kwargs else None)

    def progress(self, **kwargs: Any) -> None:
        """Log intermediate progress."""
        self._emit("progress", kwargs if kwargs else None)

    def complete(self, **kwargs: Any) -> None:
        """Log successful stage completion."""
        self._emit("complete", kwargs if kwargs else None)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error."""
        data = {"message": message}
        data.update(kwargs)
        self._emit("error", data)

    def warn(self, message: str, **kwargs: Any) -> None:
        """Log a warning."""
        data = {"message": message}
        data.update(kwargs)
        self._emit("warning", data)
