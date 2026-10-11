#!/usr/bin/env python3
"""Run the self-checker's tests without leaving bytecode in the repository."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


QUALITY_ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(QUALITY_ROOT / "src"))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(str(QUALITY_ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)

