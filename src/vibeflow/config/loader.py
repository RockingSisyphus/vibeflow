from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import sys
import time
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
    return _load_config_document(path, import_stack=(), cache={}, workspace=None, expand_nodeset_imports=True)


def load_workspace_config_document(path: Path, *, workspace: object) -> ConfigDocument:
    return _load_config_document(path, import_stack=(), cache={}, workspace=workspace, expand_nodeset_imports=True)


def load_raw_config_document(path: Path) -> ConfigDocument:
    return _load_config_document(path, import_stack=(), cache={}, workspace=None, expand_nodeset_imports=False)


def _load_config_document(
    path: Path,
    *,
    import_stack: tuple[Path, ...],
    cache: dict[Path, ConfigDocument],
    workspace: object | None,
    expand_nodeset_imports: bool,
) -> ConfigDocument:
    path = path.resolve()
    if path in import_stack:
        raise ConfigLoadError(
            rule_id="CONFIG.NODESET_IMPORT.CYCLE",
            message=f"nodeset import cycle detected: {path}",
            failure_layer="source",
            source_location={"path": str(path)},
        )
    cached = cache.get(path)
    if cached is not None:
        _trace_config_load(f"cache hit path={path}")
        return cached
    started = time.perf_counter()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigLoadError(
            rule_id="CONFIG.READ",
            message=str(exc),
            failure_layer="source",
            source_location={"path": str(path)},
        ) from exc

    if expand_nodeset_imports and _is_architecture_document(text):
        raise _architecture_document_error(path, workspace=workspace)

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
    if expand_nodeset_imports and _is_architecture_document_payload(data):
        raise _architecture_document_error(path, workspace=workspace)
    if expand_nodeset_imports:
        data, nodeset_imports = _expand_nodeset_imports(data, path=path, import_stack=(*import_stack, path), cache=cache, workspace=workspace)
    else:
        data, nodeset_imports = data, ()
    document = ConfigDocument(path=path, data=data, format=config_format, nodeset_imports=nodeset_imports)
    cache[path] = document
    _trace_config_load(
        f"loaded path={path} format={config_format} nodesets={len(data.get('nodesets', [])) if isinstance(data.get('nodesets'), list) else 0} "
        f"imports={len(nodeset_imports)} elapsed={_elapsed_ms(started)}ms"
    )
    return document


def _is_architecture_document(text: str) -> bool:
    from vibeflow.rendering.architecture_document import ARCHITECTURE_DOCUMENT_HEADER

    header = "\n".join(text.splitlines()[:4])
    return text.startswith(ARCHITECTURE_DOCUMENT_HEADER) or "NON-EXECUTABLE ARCHITECTURE REVIEW DOCUMENT." in header


def _is_architecture_document_payload(data: Mapping[str, Any]) -> bool:
    return set(data) == {"workflow", "nodesets", "node_types", "resources"} and all(
        isinstance(data.get(field), Mapping)
        for field in ("workflow", "nodesets", "node_types", "resources")
    )


def _architecture_document_error(path: Path, *, workspace: object | None) -> ConfigLoadError:
    workflow_path = ""
    project_config_path = ""
    for root in getattr(workspace, "roots", ()):
        for spec in getattr(root, "architecture_documents", ()):
            if Path(getattr(spec, "document_path", "")).resolve() != path:
                continue
            workflow_path = str(Path(getattr(spec, "workflow_path", "")).resolve())
            project_config_path = str(Path(getattr(root, "config_path", "")).resolve())
            break
        if workflow_path:
            break
    if workflow_path:
        instruction = f"use the registered workflow {workflow_path} from {project_config_path}"
    else:
        instruction = "use the workflow registered for this document in vibeflow_project.jsonc"
    return ConfigLoadError(
        rule_id="CONFIG.ARCHITECTURE_DOCUMENT.NON_EXECUTABLE",
        message=f"architecture review document is not executable: {path}; {instruction}",
        failure_layer="source",
        source_location={"path": str(path), "line": 1, "column": 1},
    )


def _expand_nodeset_imports(
    data: Mapping[str, Any],
    *,
    path: Path,
    import_stack: tuple[Path, ...],
    cache: dict[Path, ConfigDocument],
    workspace: object | None,
) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...]]:
    imports = data.get("nodeset_imports")
    if "nodesets" in data:
        raise _nodeset_import_error("CONFIG.NODESETS.INLINE_REMOVED", "inline nodesets are removed; import one nodeset JSONC file per type_key with nodeset_imports", path)
    if imports is None:
        if _is_nodeset_definition(data):
            return {str(key): deepcopy(value) for key, value in data.items()}, ()
        return data, ()
    if not isinstance(imports, list):
        raise _nodeset_import_error("CONFIG.NODESET_IMPORTS.SHAPE", "nodeset_imports must be a list", path)

    imported_nodesets: list[object] = []
    import_records: list[Mapping[str, Any]] = []
    for index, item in enumerate(imports):
        import_path, import_root = _parse_nodeset_import(item, path=path, index=index, workspace=workspace)
        document = _load_config_document(import_path, import_stack=import_stack, cache=cache, workspace=workspace, expand_nodeset_imports=True)
        selected = _nodeset_definitions_from_document(document.data, import_path)
        selected = _nodesets_with_source(selected, path=import_path, root=import_root)
        imported_nodesets.extend(_nodesets_with_file_global_config(selected, document.data.get("global_config")))
        record: dict[str, object] = {
            "path": str(import_path),
            "type_keys": [str(node.get("type_key", "")) for node in selected if isinstance(node, Mapping)],
        }
        if import_root is not None:
            record.update(_root_record(import_root))
            record["source_path"] = str(import_path)
        import_records.append(
            record
        )
        import_records.extend(document.nodeset_imports)

    expanded_nodesets = [*imported_nodesets]
    _validate_unique_nodeset_type_keys(expanded_nodesets, path)
    expanded = {str(key): deepcopy(value) for key, value in data.items() if key != "nodeset_imports"}
    expanded["nodesets"] = expanded_nodesets
    expanded["__vibeflow_expanded_nodesets__"] = True
    return expanded, tuple(import_records)


def _parse_nodeset_import(item: object, *, path: Path, index: int, workspace: object | None) -> tuple[Path, object | None]:
    if isinstance(item, str):
        if not item.strip():
            raise _nodeset_import_error("CONFIG.NODESET_IMPORT.PATH", f"nodeset_imports[{index}] path must be non-empty", path)
        return _resolve_import_path(item, path), _workspace_root_for_path(workspace, _resolve_import_path(item, path))
    if not isinstance(item, Mapping):
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.SHAPE", f"nodeset_imports[{index}] must be a string or object", path)
    raw_path = item.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.PATH", f"nodeset_imports[{index}].path must be a non-empty string", path)
    if "names" in item:
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.NAMES_REMOVED", f"nodeset_imports[{index}].names is removed; each nodeset file defines exactly one type_key", path)
    raw_root = item.get("root")
    if raw_root is None:
        import_path = _resolve_import_path(raw_path, path)
        return import_path, _workspace_root_for_path(workspace, import_path)
    if not isinstance(raw_root, str) or not raw_root.strip():
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.ROOT", f"nodeset_imports[{index}].root must be a non-empty string", path)
    if workspace is None:
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.ROOT", f"nodeset_imports[{index}].root requires a workspace config", path)
    try:
        root = workspace.root_by_id(raw_root)
        import_path = workspace.resolve_root_path(raw_root, raw_path)
    except Exception as exc:
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.ROOT", str(exc), path) from exc
    return import_path, root


def _resolve_import_path(value: str, base_path: Path) -> Path:
    import_path = Path(value)
    if not import_path.is_absolute():
        import_path = base_path.parent / import_path
    return import_path.resolve()


def _workspace_root_for_path(workspace: object | None, path: Path) -> object | None:
    if workspace is None:
        return None
    method = getattr(workspace, "root_for_path", None)
    if not callable(method):
        return None
    return method(path)


def _root_record(root: object) -> dict[str, object]:
    return {
        "root_id": str(getattr(root, "id", "")),
        "root_path": str(getattr(root, "path", "")),
    }


def _nodesets_with_source(nodesets: list[object], *, path: Path, root: object | None) -> list[object]:
    copied = deepcopy(nodesets)
    for item in copied:
        if not isinstance(item, dict):
            continue
        item.setdefault("__vibeflow_source_path__", str(path))
        if root is not None:
            item.setdefault("__vibeflow_root_id__", str(getattr(root, "id", "")))
            item.setdefault("__vibeflow_root_path__", str(getattr(root, "path", "")))
    return copied


def _nodeset_definitions_from_document(data: Mapping[str, Any], path: Path) -> list[object]:
    definitions: list[object] = []
    nested = data.get("nodesets", ())
    if isinstance(nested, list):
        definitions.extend(deepcopy(nested))
    if _is_nodeset_definition(data):
        definitions.append({str(key): deepcopy(value) for key, value in data.items() if key not in {"nodesets", "__vibeflow_expanded_nodesets__"}})
    if not definitions:
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.EMPTY", f"nodeset import must point to a nodeset definition file: {path}", path)
    return definitions


def _is_nodeset_definition(data: Mapping[str, Any]) -> bool:
    return isinstance(data.get("type_key"), str)


def _nodesets_with_file_global_config(nodesets: list[object], global_config: object) -> list[object]:
    copied = deepcopy(nodesets)
    if not isinstance(global_config, Mapping) or not global_config:
        return copied
    for item in copied:
        if isinstance(item, dict) and "global_config" not in item:
            item["global_config"] = deepcopy(global_config)
    return copied


def _validate_unique_nodeset_type_keys(nodesets: list[object], path: Path) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in nodesets:
        if not isinstance(item, Mapping):
            continue
        type_key = str(item.get("type_key", "")).strip()
        if not type_key:
            continue
        if type_key in seen:
            duplicates.add(type_key)
        seen.add(type_key)
    if duplicates:
        raise _nodeset_import_error("CONFIG.NODESET_IMPORT.DUPLICATE", f"duplicate nodeset type_key after imports: {sorted(duplicates)}", path)


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


def _trace_config_load(message: str) -> None:
    if str(os.environ.get("VIBEFLOW_CONFIG_TRACE", "")).lower() not in {"1", "true", "yes", "on"}:
        return
    print(f"[vibeflow config] {message}", file=sys.stderr)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


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
