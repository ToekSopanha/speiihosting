"""Follow log paths across rotation, truncation and partial UTF-8 writes."""

from __future__ import annotations

import codecs
import io
import os
from collections import deque
from pathlib import Path


class LogReader:
    def __init__(self, path: Path):
        self.path = path
        self.offset = 0
        self.identity: tuple[int, int] | None = None
        self.anchor = b""
        self.decoder = io.IncrementalNewlineDecoder(
            codecs.getincrementaldecoder("utf-8")(errors="replace"), translate=True
        )

    def read_tail(self, lines: int) -> str:
        return self._read(lines)

    def read_new(self) -> str:
        return self._read()

    def _read(self, lines: int | None = None) -> str:
        try:
            # Reopen each poll so readers do not hold a Windows log open while
            # the writer needs to rotate it. Stat the opened file, not its path.
            with self.path.open("rb") as handle:
                stat = os.fstat(handle.fileno())
                identity = (stat.st_dev, stat.st_ino)
                reset = identity != self.identity or stat.st_size < self.offset
                if not reset and self.anchor:
                    # A clear followed by rapid writes can exceed the old size
                    # between polls. Detect changed bytes at the last position.
                    handle.seek(self.offset - len(self.anchor))
                    reset = handle.read(len(self.anchor)) != self.anchor
                if reset or lines is not None:
                    self.offset = 0
                    self.anchor = b""
                    self.decoder.reset()
                handle.seek(self.offset)
                if lines == 0:
                    handle.seek(0, os.SEEK_END)
                    data = b""
                elif lines is not None:
                    data = b"".join(deque(handle, maxlen=lines))
                else:
                    data = handle.read()
                self.offset = handle.tell()
                self.identity = identity
                if data:
                    self.anchor = (self.anchor + data)[-128:]
                elif lines == 0:
                    anchor_size = min(self.offset, 128)
                    handle.seek(self.offset - anchor_size)
                    self.anchor = handle.read(anchor_size)
                return self.decoder.decode(data)
        except FileNotFoundError:
            # Rotation can remove a path between any existence check and open.
            # The next poll will follow the replacement or a newly created log.
            return ""
