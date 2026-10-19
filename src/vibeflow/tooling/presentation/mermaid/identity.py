"""Stable Mermaid aliases without collisions between punctuation or Unicode IDs."""
import re

_ENCODED = "vf_encoded_"


def mermaid_identity(value):
    if not re.fullmatch(r"[A-Za-z0-9_]+", value) or value.startswith(_ENCODED):
        return _ENCODED + value.encode("utf-8").hex()
    return value
