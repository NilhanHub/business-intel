from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from filelock import FileLock


class JsonStore:
    """Small locked JSON store with same-directory atomic replacement."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._thread_lock = threading.RLock()

    def ensure_ready(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, filename: str) -> Path:
        if Path(filename).name != filename or not filename.endswith(".json"):
            raise ValueError("JSON store filenames must be simple .json names")
        return self.root / filename

    def exists(self, filename: str) -> bool:
        return self._path(filename).exists()

    def _read_unlocked(self, path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return default

    def read(self, filename: str, default: Any) -> Any:
        self.ensure_ready()
        path = self._path(filename)
        with self._thread_lock, FileLock(f"{path}.lock", timeout=10):
            return self._read_unlocked(path, default)

    def _write_unlocked(self, path: Path, data: Any) -> None:
        temp_path: Path | None = None
        try:
            fd, raw_temp_path = tempfile.mkstemp(
                dir=self.root,
                prefix=f".{path.stem}-",
                suffix=".tmp",
            )
            temp_path = Path(raw_temp_path)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            temp_path = None
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def write(self, filename: str, data: Any) -> None:
        self.ensure_ready()
        path = self._path(filename)
        with self._thread_lock, FileLock(f"{path}.lock", timeout=10):
            self._write_unlocked(path, data)

    def update(
        self,
        filename: str,
        default: Any,
        mutator: Callable[[Any], Any],
    ) -> Any:
        """Atomically read, transform, and replace one JSON document."""
        self.ensure_ready()
        path = self._path(filename)
        with self._thread_lock, FileLock(f"{path}.lock", timeout=10):
            current = self._read_unlocked(path, default)
            updated = mutator(current)
            self._write_unlocked(path, updated)
            return updated
