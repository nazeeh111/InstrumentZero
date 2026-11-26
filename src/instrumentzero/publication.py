"""Exclusive publication for complete local evidence files."""

import os
import sys
import tempfile
from pathlib import Path


def publish(path, data):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".pending", dir=path.parent)
    published = False
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        published = True
    finally:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError as error:
            if not published:
                raise
            print(f"Export saved to {path}; could not remove staging file {temporary}: {error}", file=sys.stderr)
