"""Shared atomic publication of Tooling text documents and binary assets."""
import os
from pathlib import Path
from uuid import uuid4


def atomic_write(path: Path, content: str | bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid4().hex)
    try:
        if isinstance(content, bytes):
            temporary.write_bytes(content)
        else:
            temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
