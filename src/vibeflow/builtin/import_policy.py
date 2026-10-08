"""Portable import policy parameters shared by native Target handlers."""

from collections.abc import Mapping

IMPORT_POLICY_KEYS = ("allowed_roots", "banned_roots", "allowed_modules", "banned_modules")
IMPORT_POLICY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"imports": {"type": "object", "additionalProperties": False,
        "properties": {name: {"type": "array", "items": {"type": "string", "minLength": 1}}
                       for name in IMPORT_POLICY_KEYS}}},
}


def normalized_import_policy(params, *, effect_defaults=False):
    """Complete only omitted fields; an explicit empty array stays empty."""
    policy = params.get("policy", {})
    if not isinstance(policy, Mapping):
        raise ValueError("rule policy must be an object")
    unknown_sections = set(policy) - {"imports"}
    if unknown_sections:
        raise ValueError(f"unknown or unsupported rule policy sections: {sorted(unknown_sections)}")
    imports = policy.get("imports", {})
    if not isinstance(imports, Mapping):
        raise ValueError("rule policy imports must be an object")
    unknown = set(imports) - set(IMPORT_POLICY_KEYS)
    if unknown:
        raise ValueError(f"unknown rule policy import parameters: {sorted(unknown)}")
    defaults = {name: [] for name in IMPORT_POLICY_KEYS}
    if effect_defaults:
        defaults.update(banned_roots=["importlib"], allowed_modules=["urllib.parse", "vibeflow"])
    for name, value in imports.items():
        if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError(f"rule policy imports.{name} must be an array of non-empty strings")
        defaults[name] = list(value)
    return defaults


__all__ = ["IMPORT_POLICY_KEYS", "IMPORT_POLICY_SCHEMA", "normalized_import_policy"]
