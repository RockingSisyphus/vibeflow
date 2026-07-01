from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ConfigDocument:
    path: Path
    data: Mapping[str, Any]
    format: str
    nodeset_imports: tuple[Mapping[str, Any], ...] = ()


@dataclass
class ConfigLoadError(ValueError):
    rule_id: str
    message: str
    failure_layer: str
    source_location: dict[str, object]

    def __str__(self) -> str:
        return self.message


def load_config_document(path: Path) -> ConfigDocument:
    return _load_config_document(path, import_stack=())


def _load_config_document(path: Path, *, import_stack: tuple[Path, ...]) -> ConfigDocument:
    path = path.resolve()
    if path in import_stack:
        raise ConfigLoadError(
            rule_id="CONFIG.NODESET_IMPORT.CYCLE",
            message=f"nodeset import cycle detected: {path}",
            failure_layer="source",
            source_location={"path": str(path)},
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigLoadError(
            rule_id="CONFIG.READ",
            message=str(exc),
            failure_layer="source",
            source_location={"path": str(path)},
        ) from exc

    suffix = path.suffix.lower()
    config_format = "jsonc" if suffix == ".jsonc" else "json"
    if config_format == "jsonc":
        text = strip_jsonc_comments(text, path=path)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigLoadError(
            rule_id="CONFIG.JSON",
            message=exc.msg,
            failure_layer="syntax",
            source_location={"path": str(path), "line": exc.lineno, "column": exc.colno},
        ) from exc

    if not isinstance(data, Mapping):
        raise ConfigLoadError(
            rule_id="CONFIG.ROOT_OBJECT",
            message="config root must be an object",
            failure_layer="syntax",
            source_location={"path": str(path), "line": 1, "column": 1},
        )
    data, nodeset_imports = _expand_nodeset_imports(data, path=path, import_stack=(*import_stack, path))
    return ConfigDocument(path=path, data=data, format=config_format, nodeset_imports=nodeset_imports)


def _expand_nodeset_imports(
    data: Mapping[str, Any],
    *,
    path: Path,
    import_stack: tuple[Path, ...],
) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...]]:
    imports = data.get("nodeset_imports")
    if imports is None:
        return data, ()
    if not isinstance(imports, list):
        raise _nodeset_import_error("CONFIG.NODESET_IMPORTS.SHAPE", "nodeset_imports must be a list", path)

    imported_nodesets: list[object] = []
    import_records: list[Mapping[str, Any]] = []
    for index, item in enumerate(imports):
        import_path, names = _parse_nodeset_import(item, path=path, index=index)
        document = _load_config_document(import_path, import_stack=import_stack)
        raw_nodesets = document.data.get("nodesets")
        if not isinstance(raw_nodesets, list) or not raw_nodesets:
            raise _nodeset_import_error("CONFIG.NODESET_IMPORT.EMPTY", f"nodeset import has no nodesets: {import_path}", import_path)
        selected = _select_imported_nodesets(raw_nodesets, names, import_path)
        imported_nodesets.extend(deepcopy(selected))
        import_records.append(
            {
                "path": str(import_path),
                "names": [str(node.get("name", "")) for node in selected if isinstance(node, Mapping)],
                "requested_names": list(names),
            }
        )
        import_records.extend(document.nodeset_imports)

    local_nodesets = data.get("nodesets", [])
    if local_nodesets is None:
        local_nodesets = []
    if not isinstance(local_nodesets, list):
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.LOCAL_NODESETS", "nodesets must be a list when using nodeset_imports", path)
    expanded_nodesets = [*imported_nodesets, *deepcopy(local_nodesets)]
    _validate_unique_nodeset_names(expanded_nodesets, path)
    expanded = {str(key): deepcopy(value) for key, value in data.items() if key != "nodeset_imports"}
    expanded["nodesets"] = expanded_nodesets
    return expanded, tuple(import_records)


def _parse_nodeset_import(item: object, *, path: Path, index: int) -> tuple[Path, tuple[str, ...]]:
    if isinstance(item, str):
        if not item.strip():
            raise _nodeset_import_error("CONFIG.NODESET_IMPORT.PATH", f"nodeset_imports[{index}] path must be non-empty", path)
        return _resolve_import_path(item, path), ()
    if not isinstance(item, Mapping):
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.SHAPE", f"nodeset_imports[{index}] must be a string or object", path)
    raw_path = item.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.PATH", f"nodeset_imports[{index}].path must be a non-empty string", path)
    raw_names = item.get("names", [])
    if raw_names is None:
        raw_names = []
    if not isinstance(raw_names, list) or any(not isinstance(name, str) or not name.strip() for name in raw_names):
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.NAMES", f"nodeset_imports[{index}].names must be a list of non-empty strings", path)
    return _resolve_import_path(raw_path, path), tuple(str(name).strip() for name in raw_names)


def _resolve_import_path(value: str, base_path: Path) -> Path:
    import_path = Path(value)
    if not import_path.is_absolute():
        import_path = base_path.parent / import_path
    return import_path.resolve()


def _select_imported_nodesets(nodesets: list[object], names: tuple[str, ...], path: Path) -> list[object]:
    if not names:
        return list(nodesets)
    by_name = {str(item.get("name", "")): item for item in nodesets if isinstance(item, Mapping)}
    missing = [name for name in names if name not in by_name]
    if missing:
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.MISSING_NAME", f"nodeset import missing names {missing}: {path}", path)
    return [by_name[name] for name in names]


def _validate_unique_nodeset_names(nodesets: list[object], path: Path) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in nodesets:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    if duplicates:
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.DUPLICATE", f"duplicate nodeset after imports: {sorted(duplicates)}", path)


def _nodeset_import_error(rule_id: str, message: str, path: Path) -> ConfigLoadError:
    return ConfigLoadError(
        rule_id=rule_id,
        message=message,
        failure_layer="source",
        source_location={"path": str(path)},
    )


def strip_jsonc_comments(text: str, *, path: Path | None = None) -> str:
    out: list[str] = []
    index = 0
    line = 1
    column = 1
    in_string = False
    escape = False
    length = len(text)
    while index < length:
        char = text[index]
        next_char = text[index + 1] if index + 1 < length else ""

        if in_string:
            index, line, column, in_string, escape = _consume_string_char(text, index, line, column, out, escape)
            continue

        if char == '"':
            in_string = True
            out.append(char)
            line, column = _advance_position(char, line, column)
            index += 1
            continue

        if char == "/" and next_char == "/":
            index, line, column = _consume_line_comment(text, index, line, column, out)
            continue

        if char == "/" and next_char == "*":
            index, line, column = _consume_block_comment(text, index, line, column, out, path=path)
            continue

        out.append(char)
        line, column = _advance_position(char, line, column)
        index += 1
    return "".join(out)


def _consume_string_char(text: str, index: int, line: int, column: int, out: list[str], escape: bool) -> tuple[int, int, int, bool, bool]:
    char = text[index]
    out.append(char)
    in_string = True
    if escape:
        escape = False
    elif char == "\\":
        escape = True
    elif char == '"':
        in_string = False
    line, column = _advance_position(char, line, column)
    return index + 1, line, column, in_string, escape


def _consume_line_comment(text: str, index: int, line: int, column: int, out: list[str]) -> tuple[int, int, int]:
    out.extend((" ", " "))
    line, column = _advance_position("/", line, column)
    line, column = _advance_position("/", line, column)
    index += 2
    while index < len(text) and text[index] not in "\r\n":
        out.append(" ")
        line, column = _advance_position(text[index], line, column)
        index += 1
    return index, line, column


def _consume_block_comment(text: str, index: int, line: int, column: int, out: list[str], *, path: Path | None) -> tuple[int, int, int]:
    start_line = line
    start_column = column
    out.extend((" ", " "))
    line, column = _advance_position("/", line, column)
    line, column = _advance_position("*", line, column)
    index += 2
    while index < len(text):
        block_char = text[index]
        block_next = text[index + 1] if index + 1 < len(text) else ""
        if block_char == "*" and block_next == "/":
            out.extend((" ", " "))
            line, column = _advance_position("*", line, column)
            line, column = _advance_position("/", line, column)
            return index + 2, line, column
        out.append(block_char if block_char in "\r\n" else " ")
        line, column = _advance_position(block_char, line, column)
        index += 1
    raise ConfigLoadError(
        rule_id="CONFIG.JSONC.UNTERMINATED_BLOCK_COMMENT",
        message="unterminated JSONC block comment",
        failure_layer="syntax",
        source_location={"path": str(path) if path else "", "line": start_line, "column": start_column},
    )


def _advance_position(char: str, line: int, column: int) -> tuple[int, int]:
    if char == "\n":
        return line + 1, 1
    return line, column + 1
