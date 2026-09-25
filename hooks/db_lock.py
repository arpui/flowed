"""Advisory file locks for the Fluent databases.

The 6 databases are plain JSON files and several scripts can write them
(update-db.py via the session.idle hook, the server's idle sweeper, or a
manual migration). Each individual file write is already atomic (tmp +
os.replace), but a read-modify-write cycle across the 6 files is not: two
concurrent update-db.py runs can interleave and lose one update. This module
provides a small advisory lock (``<data-dir>/.db.lock``) so those cycles run
one at a time.

Notes:
- ``fcntl.flock`` is used on POSIX. Locks are advisory (cooperating processes
  only) and are released automatically by the OS when the holder dies, so a
  crashed writer never wedges the system.
- On platforms without ``fcntl`` the lock degrades to a no-op — no worse than
  the pre-lock behavior.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

try:  # POSIX only
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore[assignment]

LOCK_FILE = ".db.lock"
DEFAULT_TIMEOUT = 10.0
POLL_SECONDS = 0.05


def _timeout(timeout: float | None) -> float:
    if timeout is not None:
        return float(timeout)
    raw = os.environ.get("FLOWED_DB_LOCK_TIMEOUT", "")
    try:
        return float(raw) if raw else DEFAULT_TIMEOUT
    except ValueError:
        return DEFAULT_TIMEOUT


@contextmanager
def data_lock(data_dir, exclusive: bool = True, timeout: float | None = None):
    """Block until the advisory lock on ``<data_dir>/.db.lock`` is acquired.

    ``exclusive=True`` (default) serializes writers; ``exclusive=False`` takes
    a shared lock that allows concurrent readers. Raises ``TimeoutError`` if
    the lock is still held after ``timeout`` seconds (or
    ``$FLOWED_DB_LOCK_TIMEOUT``, default 10s).
    """
    if fcntl is None:  # pragma: no cover - non-POSIX fallback
        yield None
        return

    lock_path = Path(data_dir) / LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+", encoding="utf-8")
    flags = (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB
    deadline = time.monotonic() + _timeout(timeout)
    acquired = False
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), flags)
                acquired = True
                break
            except OSError as e:
                if time.monotonic() >= deadline:
                    who = "exclusive" if exclusive else "shared"
                    limit = _timeout(timeout)
                    raise TimeoutError(
                        f"Could not acquire {who} lock on {lock_path} "
                        f"within {limit:.1f}s — is another Fluent writer stuck?"
                    ) from e
                time.sleep(POLL_SECONDS)
        yield handle
    finally:
        if acquired:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:  # pragma: no cover - best-effort release
                pass
        handle.close()
