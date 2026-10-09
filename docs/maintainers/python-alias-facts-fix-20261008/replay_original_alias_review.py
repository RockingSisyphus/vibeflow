"""Run the untouched 36-case historical review; preserve all original expectations.

The separate origin report classifies diagnostic kinds and explicitly records
unknown .write() I/O-only mismatches. It never rewrites the historical report or
converts them into 36/36 passes. Use -I -B and exactly one selected product.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import runpy
import sys
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selected = parser.add_mutually_exclusive_group()
    selected.add_argument('--source', type=Path)
    selected.add_argument('--kernel', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--origin-report', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    protected = json.loads((Path(__file__).parent / 'before-source-and-audits.json').read_text())['protected_original_audit_and_probes']
    assert all(hashlib.sha256((repo / r['path']).read_bytes()).hexdigest() == r['sha256'] for r in protected)
    review = repo / 'docs/maintainers/python-comprehension-scope-review-20261008/reproduce_alias_escape.py'
    original_hash = hashlib.sha256(review.read_bytes()).hexdigest()
    if args.source:
        product, kind = args.source.resolve(strict=True), 'source_snapshot'
    elif args.kernel:
        product, kind = args.kernel.resolve(strict=True), 'kernel_zip'
    else:
        distribution = importlib.metadata.distribution('vibeflow')
        assert distribution.read_text('WHEEL')
        assert not json.loads(distribution.read_text('direct_url.json') or '{}').get('dir_info', {}).get('editable')
        product, kind = Path(distribution.locate_file('')).resolve(strict=True), 'installed_wheel'
    sys.path.insert(0, str(product))
    expected = str(product / 'vibeflow') + '/'
    original_argv = sys.argv
    sys.argv = [str(review), '--report', str(args.report.resolve())]
    if args.kernel:
        sys.argv += ['--kernel', str(product)]
    try:
        runpy.run_path(str(review))['main']()
    finally:
        sys.argv = original_argv
    raw = json.loads(args.report.read_text())
    modules = {name: str(getattr(module, '__file__', '')) for name, module in sys.modules.items() if name == 'vibeflow' or name.startswith('vibeflow.')}
    foreign = {name: path for name, path in modules.items() if not path or not path.startswith(expected)}
    assert not foreign
    deviations = []
    for row in raw['rows']:
        if row['matched']:
            continue
        messages = [finding['message'] for finding in row['findings']]
        host = any('banned process argument access:' in m or 'banned terminal stream access:' in m or 'banned call: sys.' in m for m in messages)
        owned = any('mutate inputs' in m for m in messages)
        preserved_io = row['case'] == 'local_sys_attribute' and not host and not owned and bool(messages) and all('banned call:' in m and 'write' in m for m in messages)
        deviations.append({'case': row['case'], 'kind': row['kind'], 'original_expected_findings': row['expected_findings'], 'host_diagnostic': host, 'input_diagnostic': owned, 'preserved_unknown_write_io_only': preserved_io, 'messages': messages})
    if args.kernel:
        with zipfile.ZipFile(product) as archive:
            hashes = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist() if name.startswith('vibeflow/') and not name.endswith('/')}
    else:
        directory = product / 'vibeflow'
        hashes = {'vibeflow/' + p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}
    record = {'product': {'kind': kind, 'path': str(product), 'origin': modules['vibeflow']}, 'script_sha256': original_hash, 'original_count': raw['count'], 'original_mismatches': raw['mismatches'], 'deviations': deviations, 'preserved_unknown_write_only_count': sum(r['preserved_unknown_write_io_only'] for r in deviations), 'other_semantic_mismatch_count': sum(not r['preserved_unknown_write_io_only'] for r in deviations), 'loaded_product_modules': modules, 'foreign_product_modules': foreign, 'product_files_sha256': hashes, 'original_script_and_audit_unchanged': all(hashlib.sha256((repo / r['path']).read_bytes()).hexdigest() == r['sha256'] for r in protected), 'original_expectations_modified': False}
    args.origin_report.parent.mkdir(parents=True, exist_ok=True)
    args.origin_report.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    assert hashlib.sha256(review.read_bytes()).hexdigest() == original_hash
    print(json.dumps({key: record[key] for key in ('original_count', 'original_mismatches', 'preserved_unknown_write_only_count', 'other_semantic_mismatch_count', 'foreign_product_modules')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
