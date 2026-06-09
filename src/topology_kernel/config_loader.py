from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ConfigDocument:
    path: Path
    data: Mapping[str, Any]
    format: str


@dataclass
class ConfigLoadError(ValueError):
    rule_id: str
    message: str
    failure_layer: str
    source_location: dict[str, object]

    def __str__(self) -> str:
        return self.message


def load_config_document(path: Path) -> ConfigDocument:
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
    return ConfigDocument(path=path, data=data, format=config_format)


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
