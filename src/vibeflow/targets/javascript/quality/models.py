"""Plain facts produced by the JavaScript/TypeScript quality frontend."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JavascriptImportFact:
    specifier: str
    destination_kind: str = "package"
    destination_id: str = ""
    declared: bool = True
    line: int = 1
    column: int = 1


@dataclass(frozen=True)
class JavascriptImplementationQualityFacts:
    implementation_id: str
    kind: str
    source_path: str
    target: str
    completion: str = "immediate"
    declared_async: bool = False
    returns_promise: bool = False
    hidden_promise_work: bool = False
    registers_listener: bool = False
    has_dynamic_import: bool = False
    imports: tuple[JavascriptImportFact, ...] = ()


__all__ = [
    "JavascriptImplementationQualityFacts",
    "JavascriptImportFact",
]
