from __future__ import annotations

from typing import Callable, Generic, TypeVar


T = TypeVar("T")


class RegistryBase(Generic[T]):
    def __init__(self) -> None:
        self._registry: dict[str, T] = {}

    def register(self, key: str, value: T | None = None, *, overwrite: bool = False) -> T | Callable[[T], T]:
        if value is None:
            return self._decorator_for(key, overwrite=overwrite)
        self._register(key, value, overwrite=overwrite)
        return value

    def get(self, key: str) -> T:
        normalized = self._normalize_key(key)
        try:
            return self._registry[normalized]
        except KeyError as exc:
            raise self._unknown_error(normalized) from exc

    def available(self) -> list[str]:
        return sorted(self._registry)

    def _decorator_for(self, key: str, *, overwrite: bool) -> Callable[[T], T]:
        def decorator(value: T) -> T:
            self._register(key, value, overwrite=overwrite)
            return value

        return decorator

    def _register(self, key: str, value: T, *, overwrite: bool) -> None:
        normalized = self._normalize_key(key)
        self._validate_value(normalized, value)
        if normalized in self._registry and not overwrite:
            raise self._duplicate_error(normalized)
        self._registry[normalized] = value

    def _normalize_key(self, key: str) -> str:
        normalized = str(key).strip()
        if not normalized:
            raise self._empty_key_error()
        return normalized

    def _validate_value(self, normalized: str, value: T) -> None:
        return None

    def _empty_key_error(self) -> Exception:
        raise NotImplementedError

    def _duplicate_error(self, normalized: str) -> Exception:
        raise NotImplementedError

    def _unknown_error(self, normalized: str) -> Exception:
        raise NotImplementedError
