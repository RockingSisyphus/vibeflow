from __future__ import annotations

from .code_quality_types import FileQuality, FunctionQuality, QualityFinding


def duplicate_function_findings(files: tuple[FileQuality, ...]) -> list[QualityFinding]:
    groups: dict[str, list[tuple[str, FunctionQuality]]] = {}
    for file in files:
        for function in file.functions:
            if function.lines >= 3:
                groups.setdefault(function.ast_fingerprint, []).append((file.path, function))
    return [_duplicate_group_finding(matches) for matches in groups.values() if len(matches) >= 2]


def _duplicate_group_finding(matches: list[tuple[str, FunctionQuality]]) -> QualityFinding:
    targets = [f"{path}:{function.qualname}" for path, function in matches]
    function_details = [
        {
            "path": path,
            "qualname": function.qualname,
            "line_start": function.line_start,
            "line_end": function.line_end,
            "lines": function.lines,
            "branches": function.branches,
            "params": function.param_count,
        }
        for path, function in matches
    ]
    return QualityFinding(
        "QUALITY.DUPLICATE.AST_FINGERPRINT",
        "warning",
        "function_group",
        ", ".join(targets),
        "similar function AST fingerprint detected",
        suggested_fix_type="extract_shared_helper",
        details={
            "functions": targets,
            "function_details": function_details,
            "fingerprint": matches[0][1].ast_fingerprint if matches else "",
            "group_size": len(matches),
        },
    )
