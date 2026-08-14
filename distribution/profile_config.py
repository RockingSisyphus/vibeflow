from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

PROFILE_SCHEMA = "vibeflow.distribution-profiles.v1"
PROFILE_NAMES = ("collaborative", "autonomous")
PROTOCOL_KEYS = frozenset(
    {
        "change_inventory",
        "planned_review",
        "human_approval_gate",
        "required_review_artifact",
    }
)
AUTOMATION_KEYS = frozenset(
    {
        "refresh_architecture",
        "validate",
        "quality",
        "build",
        "workflow_execution_probe",
    }
)


class DistributionProfileError(ValueError):
    pass


@dataclass(frozen=True)
class DistributionProfile:
    name: str
    prompt_fragments: tuple[Path, ...]
    documents: tuple[Path, ...]
    agent_protocol: Mapping[str, Any]
    agent_automation: Mapping[str, bool]


def load_distribution_profiles(path: Path) -> dict[str, DistributionProfile]:
    repository_root = path.parent.parent.resolve()
    try:
        payload = json.loads(_strip_jsonc_comments(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise DistributionProfileError(f"cannot read distribution profiles: {exc}") from exc
    root = _mapping(payload, "distribution profiles")
    _reject_unknown(root, {"schema", "document_sets", "profiles"}, "distribution profiles")
    if root.get("schema") != PROFILE_SCHEMA:
        raise DistributionProfileError(f"distribution profile schema must be {PROFILE_SCHEMA!r}")

    raw_sets = _mapping(root.get("document_sets"), "document_sets")
    document_sets: dict[str, tuple[Path, ...]] = {}
    for set_name, raw_paths in raw_sets.items():
        document_sets[str(set_name)] = _paths(
            raw_paths,
            repository_root,
            f"document_sets.{set_name}",
            allowed_roots=(repository_root / "docs",),
        )

    raw_profiles = _mapping(root.get("profiles"), "profiles")
    if set(raw_profiles) != set(PROFILE_NAMES):
        raise DistributionProfileError(
            "profiles must define exactly collaborative and autonomous"
        )
    profiles: dict[str, DistributionProfile] = {}
    for name in PROFILE_NAMES:
        raw = _mapping(raw_profiles[name], f"profiles.{name}")
        _reject_unknown(
            raw,
            {"prompt_fragments", "document_sets", "agent_protocol", "agent_automation"},
            f"profiles.{name}",
        )
        prompts = _paths(
            raw.get("prompt_fragments"),
            repository_root,
            f"profiles.{name}.prompt_fragments",
            allowed_roots=(repository_root / "distribution" / "prompts",),
        )
        if len(prompts) != len(set(prompts)):
            raise DistributionProfileError(f"profiles.{name} contains duplicate prompt fragments")
        set_names = _strings(raw.get("document_sets"), f"profiles.{name}.document_sets")
        missing_sets = [item for item in set_names if item not in document_sets]
        if missing_sets:
            raise DistributionProfileError(
                f"profiles.{name} refers to unknown document sets: {', '.join(missing_sets)}"
            )
        documents = tuple(path for set_name in set_names for path in document_sets[set_name])
        if len(documents) != len(set(documents)):
            raise DistributionProfileError(f"profiles.{name} contains duplicate documents")

        protocol = _mapping(raw.get("agent_protocol"), f"profiles.{name}.agent_protocol")
        _require_exact_keys(protocol, PROTOCOL_KEYS, f"profiles.{name}.agent_protocol")
        automation = _mapping(raw.get("agent_automation"), f"profiles.{name}.agent_automation")
        _require_exact_keys(automation, AUTOMATION_KEYS, f"profiles.{name}.agent_automation")
        if any(not isinstance(value, bool) for value in automation.values()):
            raise DistributionProfileError(f"profiles.{name}.agent_automation values must be booleans")
        _validate_protocol(name, protocol)
        profiles[name] = DistributionProfile(
            name=name,
            prompt_fragments=prompts,
            documents=documents,
            agent_protocol=dict(protocol),
            agent_automation={key: bool(value) for key, value in automation.items()},
        )
    return profiles


def _strip_jsonc_comments(source: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and following == "/":
            output.extend((" ", " "))
            index += 2
            while index < len(source) and source[index] not in "\r\n":
                output.append(" ")
                index += 1
            continue
        if char == "/" and following == "*":
            output.extend((" ", " "))
            index += 2
            while index < len(source):
                if source[index : index + 2] == "*/":
                    output.extend((" ", " "))
                    index += 2
                    break
                output.append(source[index] if source[index] in "\r\n" else " ")
                index += 1
            else:
                raise DistributionProfileError("unterminated JSONC block comment")
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DistributionProfileError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise DistributionProfileError(f"{label} must be a non-empty array")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise DistributionProfileError(f"{label} entries must be non-empty strings")
    return tuple(item.strip() for item in value)


def _paths(
    value: Any,
    repository_root: Path,
    label: str,
    *,
    allowed_roots: tuple[Path, ...],
) -> tuple[Path, ...]:
    result: list[Path] = []
    for item in _strings(value, label):
        relative = Path(item)
        if relative.is_absolute() or ".." in relative.parts:
            raise DistributionProfileError(f"{label} contains an unsafe path: {item}")
        candidate = repository_root / relative
        resolved = candidate.resolve()
        allowed = any(resolved == root or root in resolved.parents for root in allowed_roots)
        if candidate.is_symlink() or not allowed or not resolved.is_file():
            raise DistributionProfileError(f"{label} contains a missing or external file: {item}")
        result.append(resolved)
    return tuple(result)


def _reject_unknown(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise DistributionProfileError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _require_exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    _reject_unknown(value, set(expected), label)
    missing = sorted(expected - set(value))
    if missing:
        raise DistributionProfileError(f"{label} is missing fields: {', '.join(missing)}")


def _validate_protocol(name: str, protocol: Mapping[str, Any]) -> None:
    if protocol["change_inventory"] not in {"required", "optional"}:
        raise DistributionProfileError(f"profiles.{name}.agent_protocol.change_inventory is invalid")
    if protocol["required_review_artifact"] not in {"expanded_svg", "on_demand"}:
        raise DistributionProfileError(
            f"profiles.{name}.agent_protocol.required_review_artifact is invalid"
        )
    if not isinstance(protocol["planned_review"], bool) or not isinstance(protocol["human_approval_gate"], bool):
        raise DistributionProfileError(f"profiles.{name}.agent_protocol boolean fields must be booleans")
    if name == "collaborative":
        expected = ("required", True, True, "expanded_svg")
    else:
        expected = ("optional", False, False, "on_demand")
    actual = (
        protocol["change_inventory"],
        protocol["planned_review"],
        protocol["human_approval_gate"],
        protocol["required_review_artifact"],
    )
    if actual != expected:
        raise DistributionProfileError(f"profiles.{name}.agent_protocol is contradictory")


__all__ = [
    "DistributionProfile",
    "DistributionProfileError",
    "PROFILE_NAMES",
    "PROFILE_SCHEMA",
    "load_distribution_profiles",
]
