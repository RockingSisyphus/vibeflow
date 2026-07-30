from __future__ import annotations

from typing import Any, Mapping

from vibeflow.descriptors.models import DescriptorModelError


def check_fields(
    value: Mapping[str, Any],
    *,
    allowed: set[str],
    field: str,
) -> None:
    unknown = sorted(str(key) for key in value if str(key) not in allowed)
    if unknown:
        raise DescriptorModelError(
            f"{field} contains unknown fields: {unknown}"
        )


def required_mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DescriptorModelError(f"{field} must be an object")
    return value


def mapping_or_empty(value: object, *, field: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    return required_mapping(value, field=field)


def object_list(
    value: object,
    *,
    field: str,
) -> tuple[Mapping[str, Any], ...]:
    if value in (None, ()):
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise DescriptorModelError(f"{field} must be a list of objects")
    out: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise DescriptorModelError(f"{field}[{index}] must be an object")
        out.append(item)
    return tuple(out)


def mapping_list(
    value: object,
    *,
    field: str,
) -> tuple[Mapping[str, Any], ...]:
    return object_list(value, field=field)


def string_list(value: object, *, field: str) -> tuple[str, ...]:
    if value in (None, ()):
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise DescriptorModelError(f"{field} must be a list of strings")
    out = tuple(
        required_string(item, field=f"{field}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(out)) != len(out):
        raise DescriptorModelError(f"{field} contains duplicate values")
    return out


def required_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DescriptorModelError(f"{field} must be a non-empty string")
    return value.strip()


def optional_string(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise DescriptorModelError("optional string field must be a string")
    return value.strip()


def nullable_string(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DescriptorModelError(f"{field} must be a string or null")
    return value.strip() or None


def boolean(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise DescriptorModelError(f"{field} must be a boolean")
    return value
