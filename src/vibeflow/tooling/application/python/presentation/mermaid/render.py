"""Compatibility alias for the target-neutral Mermaid renderer."""

import sys

from vibeflow.tooling.presentation import mermaid as _implementation

sys.modules[__name__] = _implementation
