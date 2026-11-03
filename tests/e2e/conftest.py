"""External dependency locations supplied once by the test entrypoint."""
import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def browser_runtime():
    root = Path(os.environ["VIBEFLOW_BROWSER_RUNTIME_ROOT"])
    assert (root / "node_modules/puppeteer").is_dir(), "Browser environment is required"
    return root


@pytest.fixture(scope="session")
def toolchain():
    root = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    assert (root / "node_modules/typescript").is_dir(), "JavaScript environment is required"
    return root
