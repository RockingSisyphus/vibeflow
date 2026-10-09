"""Replay unchanged F01/F02 originals through one isolated selected product.

Use -I -B; select --source or --kernel, or the installed wheel interpreter.
Historical code and expectations are byte-checked, never rewritten.
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
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group();choice.add_argument('--source',type=Path);choice.add_argument('--kernel',type=Path)
    parser.add_argument('--review',choices=('F01','F02'),required=True)
    parser.add_argument('--report',type=Path,required=True);parser.add_argument('--origin-report',type=Path,required=True)
    args=parser.parse_args();repo=Path(__file__).resolve().parents[3]
    names={'F01':'docs/maintainers/system-migration-remediation-review-20261008/reproduce_function_default_scope.py','F02':'docs/maintainers/python-function-definition-scope-review-20261008/reproduce_comprehension_scope.py'}
    review=repo/names[args.review]
    manifest=json.loads((Path(__file__).parent/'preserved-probe-scripts.json').read_text())
    expected=next(row['sha256'] for row in manifest if row.get('tracked_script')==names[args.review])
    actual=hashlib.sha256(review.read_bytes()).hexdigest();assert actual==expected
    if args.source:product,kind=args.source.resolve(strict=True),'source_snapshot'
    elif args.kernel:product,kind=args.kernel.resolve(strict=True),'kernel_zip'
    else:
        distribution=importlib.metadata.distribution('vibeflow');assert distribution.read_text('WHEEL')
        assert not json.loads(distribution.read_text('direct_url.json') or '{}').get('dir_info',{}).get('editable')
        product,kind=Path(distribution.locate_file('')).resolve(strict=True),'installed_wheel'
    prefix=str(product/'vibeflow')+'/'
    sys.path.insert(0,str(product));original=sys.argv
    args.report.parent.mkdir(parents=True,exist_ok=True)
    sys.argv=[str(review),'--report',str(args.report.resolve())]
    if args.kernel:sys.argv+=['--kernel',str(product)]
    try:status=runpy.run_path(str(review))['main']()
    finally:sys.argv=original
    loaded={name:str(getattr(module,'__file__','')) for name,module in sys.modules.items() if name=='vibeflow' or name.startswith('vibeflow.')}
    foreign={name:path for name,path in loaded.items() if not path or not path.startswith(prefix)}
    if args.kernel:
        with zipfile.ZipFile(product) as archive:hashes={name:hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist() if name.startswith('vibeflow/') and not name.endswith('/')}
    else:
        directory=product/'vibeflow';hashes={'vibeflow/'+p.relative_to(directory).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    raw=json.loads(args.report.read_text());record={'product':{'kind':kind,'path':str(product),'origin':loaded['vibeflow']},'review':args.review,'review_script':str(review),'review_script_sha256':actual,'original_exit':status,'cases':raw['count'],'mismatches':raw['mismatches'],'loaded_product_modules':loaded,'foreign_product_modules':foreign,'product_files_sha256':hashes,'original_expectations_modified':False}
    args.origin_report.parent.mkdir(parents=True,exist_ok=True);args.origin_report.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    assert hashlib.sha256(review.read_bytes()).hexdigest()==actual and not foreign
    return status


if __name__=='__main__':raise SystemExit(main())
