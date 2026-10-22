"""Source-only checks for implicit platform encodings in owned Python code."""
from __future__ import annotations

import ast
from pathlib import Path

from .models import Finding, SourceLocation


def text_encoding_findings(tree: ast.Module, path: Path, root: Path) -> list[Finding]:
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases.update((item.asname or item.name.split('.')[0], item.name if item.asname else item.name.split('.')[0]) for item in node.names)
        elif isinstance(node, ast.ImportFrom):
            aliases.update((item.asname or item.name, f"{node.module}.{item.name}") for item in node.names)

    def symbol(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return symbol(node.value) + '.' + node.attr
        return ''

    paths = set()
    def is_path(node):
        if ast.dump(node) in paths:
            return True
        if isinstance(node, ast.Call):
            return symbol(node.func) == 'pathlib.Path' or (isinstance(node.func, ast.Attribute)
                and node.func.attr in {'resolve', 'absolute', 'expanduser', 'joinpath', 'with_name', 'with_suffix'} and is_path(node.func.value))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return is_path(node.left) or is_path(node.right)
        if isinstance(node, ast.Attribute) and node.attr in {'parent', 'parents'}:
            return is_path(node.value)
        return isinstance(node, ast.Subscript) and is_path(node.value)

    # Track direct Path assignments and annotations, without guessing arbitrary open methods.
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation and symbol(node.annotation) == 'pathlib.Path':
            paths.add(ast.dump(ast.Name(id=node.arg, ctx=ast.Load())))
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None or not is_path(node.value):
                continue
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                # Context does not affect the identity of a named Path binding.
                target = ast.parse(ast.unparse(target), mode='eval').body
                key = ast.dump(target)
                if key not in paths:
                    paths.add(key)
                    changed = True

    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = symbol(node.func)
        keywords = {item.arg:item.value for item in node.keywords}
        position, mode_position, default_mode = None, None, 'r'
        method = node.func.attr if isinstance(node.func, ast.Attribute) else ''
        if method in {'read_text', 'write_text'}:
            # Imported module helpers may deliberately own their encoding internally.
            if isinstance(node.func.value, ast.Name) and node.func.value.id in aliases and symbol(node.func.value) != 'pathlib.Path':
                continue
            position = (0 if method == 'read_text' else 1) + (symbol(node.func.value) == 'pathlib.Path')
        elif name in {'open', 'builtins.open', 'io.open', 'codecs.open', 'gzip.open', 'bz2.open', 'lzma.open'}:
            position, mode_position = (2 if name == 'codecs.open' else 3), 1
            if name in {'gzip.open', 'bz2.open', 'lzma.open'}:
                default_mode = 'rb'
        elif method == 'open' and is_path(node.func.value):
            position, mode_position = 2, 0
        elif name in {'tempfile.TemporaryFile', 'tempfile.NamedTemporaryFile', 'tempfile.SpooledTemporaryFile'}:
            position, mode_position, default_mode = (3, 1, 'w+b') if name.endswith('SpooledTemporaryFile') else (2, 0, 'w+b')
        elif name == 'io.TextIOWrapper':
            position = 1
        elif name.startswith('subprocess.') and name.rsplit('.', 1)[-1] in {'run', 'Popen', 'check_output', 'check_call'}:
            text = keywords.get('text', keywords.get('universal_newlines'))
            if not isinstance(text, ast.Constant) or text.value is not True:
                continue
            position = len(node.args)
        else:
            continue
        if mode_position is not None:
            mode = keywords.get('mode', node.args[mode_position] if len(node.args) > mode_position else ast.Constant(default_mode))
            if not isinstance(mode, ast.Constant) or not isinstance(mode.value, str) or 'b' in mode.value:
                continue
        encoding = keywords.get('encoding', node.args[position] if len(node.args) > position else None)
        if encoding is not None and not (isinstance(encoding, ast.Constant) and encoding.value in {None, '', 'locale'}):
            continue
        relative = path.relative_to(root).as_posix()
        findings.append(Finding(code='TEXT_ENCODING_UNSPECIFIED', severity='error', subject_type='source_file',
            subject_id=relative, source_location=SourceLocation(relative, node.lineno, node.col_offset),
            message='Text I/O relies on the platform default encoding.',
            suggested_fix='Specify encoding="utf-8" for owned text formats, or the explicit encoding of the external format; use binary I/O for bytes.'))
    return findings
