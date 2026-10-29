"""Locate the independent browser acceptance-test runtime."""
import os
from pathlib import Path


def browser_runtime_manifest():
    root = Path(os.environ.get("VIBEFLOW_BROWSER_RUNTIME_ROOT", Path(__file__).resolve().parents[2] / "browser-runtime"))
    if not (root / "node_modules/puppeteer").is_dir():
        raise FileNotFoundError("Install tests/browser-runtime dependencies for browser acceptance tests")
    return root / "package.json"


def browser_runtime_available():
    try:
        browser_runtime_manifest()
        return True
    except FileNotFoundError:
        return False
