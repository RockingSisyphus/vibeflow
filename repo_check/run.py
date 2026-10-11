#!/usr/bin/env python3
"""Run VibeFlow's repository checks without importing VibeFlow."""

from __future__ import annotations

from pathlib import Path
import sys


QUALITY_ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(QUALITY_ROOT / "src"))

from vibeflow_quality.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(default_root=QUALITY_ROOT.parent))
