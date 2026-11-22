"""Native JavaScript target contracts beside the canonical workflow plan."""
from dataclasses import dataclass

COMPLETIONS = frozenset({"immediate", "suspend"})
SCHEDULES = frozenset({"inline"})
EXECUTORS = frozenset({"current", "event_loop", "thread"})
TARGETS = frozenset({"browser", "node"})
PROFILES = frozenset({"esm-module", "single-esm", "web-app"})
