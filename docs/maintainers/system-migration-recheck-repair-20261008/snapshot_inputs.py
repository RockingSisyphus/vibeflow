import hashlib
import json
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[3]
skip = {'__pycache__', '.pytest_cache', '.artifacts', 'node_modules', '.git', 'dist'}
paths = set()
for prefix in ('src', 'tests', 'sandbox', 'tools', 'quality', 'distribution', 'docs/user', 'docs/design'):
    for path in (root / prefix).rglob('*'):
        if path.is_file() and not skip.intersection(path.relative_to(root).parts) and path.suffix not in {'.pyc', '.pyo'}:
            paths.add(path)
for name in ('pyproject.toml', 'README.md', 'README.en.md', 'docs/README.md'):
    paths.add(root / name)
rows = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}
aggregate = hashlib.sha256(''.join(f'{key}\0{value}\n' for key, value in rows.items()).encode()).hexdigest()
result = {'files': len(rows), 'sha256': aggregate, 'excluded_generated_components': sorted(skip), 'file_sha256': rows}
Path(sys.argv[1]).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'files': len(rows), 'sha256': aggregate}))
