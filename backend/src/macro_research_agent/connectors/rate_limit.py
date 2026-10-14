"""Process-safe provider request budgets for public connectors."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class ProviderRateLimitError(RuntimeError):
    def __init__(self, provider: str, retry_after_seconds: float) -> None:
        self.provider = provider
        self.retry_after_seconds = max(0.0, retry_after_seconds)
        super().__init__(
            f"{provider} request budget is exhausted; retry in "
            f"{self.retry_after_seconds:.1f} seconds."
        )


@dataclass(frozen=True)
class RateWindow:
    seconds: int
    max_requests: int


class PersistentRateLimiter:
    """Reserve a provider request under multiple rolling-window budgets.

    The timestamp ledger is shared by every session and guarded with an OS file
    lock. A budget failure is immediate so connector calls never hide a long
    provider-imposed wait inside an interactive workflow request.
    """

    def __init__(
        self,
        state_dir: Path,
        provider: str,
        windows: tuple[RateWindow, ...],
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not windows or any(item.seconds < 1 or item.max_requests < 1 for item in windows):
            raise ValueError("Rate limits require positive windows and request counts.")
        self.state_dir = state_dir
        self.provider = provider
        self.windows = windows
        self.clock = clock

    def acquire(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_dir / f"{self.provider}.lock"
        ledger_path = self.state_dir / f"{self.provider}.json"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                now = self.clock()
                timestamps = self._read(ledger_path)
                longest = max(item.seconds for item in self.windows)
                timestamps = [item for item in timestamps if item > now - longest]
                retry_after = 0.0
                for window in self.windows:
                    active = [item for item in timestamps if item > now - window.seconds]
                    if len(active) >= window.max_requests:
                        retry_after = max(
                            retry_after,
                            active[-window.max_requests] + window.seconds - now,
                        )
                if retry_after > 0:
                    raise ProviderRateLimitError(self.provider, retry_after)
                timestamps.append(now)
                self._write(ledger_path, timestamps)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _read(path: Path) -> list[float]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                return []
            return sorted(float(item) for item in payload if float(item) >= 0)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return []

    @staticmethod
    def _write(path: Path, timestamps: list[float]) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(timestamps, stream, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)
