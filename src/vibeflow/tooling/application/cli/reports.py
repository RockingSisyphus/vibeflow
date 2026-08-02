"""Compatibility facade for application report helpers."""

import sys as _sys

from vibeflow.tooling.application import reports as _canonical

from vibeflow.tooling.application.reports import (
    config_load_error_report,
    dedupe_findings,
    error_report,
    fail_report,
    format_finding_text,
    graph_config_error_report,
    location_text,
)

__all__ = [
    "config_load_error_report",
    "dedupe_findings",
    "error_report",
    "fail_report",
    "format_finding_text",
    "graph_config_error_report",
    "location_text",
]

_sys.modules[__name__] = _canonical
