"""Target-neutral workflow entry and coordination declarations."""
from .entries import EntrySpec, parse_entries, choose_entry, project_entry

__all__ = ["EntrySpec", "parse_entries", "choose_entry", "project_entry"]
