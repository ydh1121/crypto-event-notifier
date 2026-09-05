from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO


RESEARCH_WORK_LOCK_PATH = Path(
    "b3_trader/data/research-platform/dex-forward-research-work.lock"
)


class ResearchWorkLock:
    """Small cross-process lock for listing/DEX research ownership.

    The lock is advisory and non-blocking. Windows uses ``msvcrt.locking`` and
    POSIX uses ``flock``; in both cases the operating system releases ownership
    automatically if a process exits. Callers that cannot acquire it must return
    a bounded no-op instead of starting network or SQLite work.
    """

    def __init__(self, path: Path | str = RESEARCH_WORK_LOCK_PATH) -> None:
        self.path = Path(path)
        self._handle: BinaryIO | None = None

    @property
    def acquired(self) -> bool:
        return self._handle is not None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b", buffering=0)
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() <= 0:
                handle.write(b"\0")
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self) -> "ResearchWorkLock":
        self.acquire()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.release()
