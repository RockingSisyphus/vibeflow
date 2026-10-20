"""Warm public Python AOT calls; optional process-local metadata experiments."""
from pathlib import Path
import argparse
import cProfile
from contextlib import contextmanager
import json
import statistics
import sys
import tempfile
import time
import uuid
from zipfile import ZipFile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))


def run(bundle_path, work, rounds):
    from vibeflow.tooling.application.python.bundle import load_bundle, PythonBundle
    from vibeflow.targets.python.sdk.plugin import Plugin
    started = time.perf_counter()
    bundle = load_bundle(bundle_path)
    load_seconds = time.perf_counter() - started
    descriptor = PythonBundle._descriptor
    bindings = Plugin.bindings
    descriptions, indexes = {}, {}

    def cached_descriptor(owner, record):
        key = (id(owner), id(record))
        if key not in descriptions:
            descriptions[key] = descriptor(owner, record)
        return descriptions[key]

    def cached_bindings(owner):
        key = id(owner)
        if key not in indexes:
            indexes[key] = bindings(owner)
        return indexes[key]

    @contextmanager
    def mode(name):
        PythonBundle._descriptor = cached_descriptor if name in {'descriptors', 'both'} else descriptor
        Plugin.bindings = cached_bindings if name in {'bindings', 'both'} else bindings
        try:
            yield
        finally:
            PythonBundle._descriptor, Plugin.bindings = descriptor, bindings

    def call():
        started = time.perf_counter()
        runtime = bundle.create_runtime(run_dir=work / 'runs' / uuid.uuid4().hex,
            runtime_options={'execution': 'compiled', 'trace': 'off'})
        prepared = time.perf_counter()
        context = runtime.run({
            'core.request': {'operation': 'settings.get', 'params': {},
                'caller': {'actor': 'ai', 'binding': {'harness': 'codex',
                    'instance': 'aot-sandbox', 'conversation': 'synthetic'}}},
            'core.runtime': {'state_dir': str(work / 'state'), 'invocation_id': uuid.uuid4().hex,
                'now': time.time(), 'mono': time.monotonic(), 'timezone': 'UTC',
                'default_profile': {'id': 'aot-sandbox', 'overrides': {}}}})
        ended = time.perf_counter()
        result = context.get('core.request_result')['value']
        assert result['status'] == 'ok', result
        return result['settings'], {'prepare_ms': (prepared-started)*1000,
            'run_ms': (ended-prepared)*1000, 'total_ms': (ended-started)*1000}

    expected, _ = call()
    # Separate profiling from latency measurements: profile overhead is not a latency result.
    profile = cProfile.Profile()
    profile.enable()
    for _ in range(5):
        value, _ = call()
        assert value == expected
    profile.disable()
    selected = {'_descriptor', '_registry', 'bindings', 'decode_resource',
        '_discard_foreign_project_modules', 'bind_python_workflow'}
    counts = [{'file': row.code.co_filename, 'function': row.code.co_name, 'calls': row.callcount}
        for row in profile.getstats() if not isinstance(row.code, str) and row.code.co_name in selected]
    for name in ['descriptors', 'bindings', 'both']:
        with mode(name):
            value, _ = call()
            assert value == expected
    samples = []
    # Reverse order on alternating rounds rather than timing all baselines first.
    for index in range(rounds):
        names = ['normal', 'descriptors', 'bindings', 'both']
        for name in names if index % 2 == 0 else reversed(names):
            with mode(name):
                value, sample = call()
                assert value == expected
            samples.append({'mode': name, **sample})
    return {'platform': sys.platform, 'python': sys.version.split()[0],
        'framework': str(Path(sys.modules[PythonBundle.__module__].__file__).resolve()),
        'node_types': len(bundle.data['nodes']), 'load_seconds': load_seconds,
        'runtime_instances_reused': False, 'profile_warm_calls': 5, 'profile_counts': counts,
        'scope': 'Real handoff settings.get, private empty state. Cached modes are diagnostic only; no SDK files changed.',
        'medians_ms': {name: {field: statistics.median(s[field] for s in samples if s['mode'] == name)
            for field in ['prepare_ms', 'run_ms', 'total_ms']} for name in ['normal', 'descriptors', 'bindings', 'both']},
        'samples': samples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoff', type=Path, required=True, help='Original author handoff ZIP')
    parser.add_argument('--rounds', type=int, default=8)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='python-aot-preparation-') as name:
        work = Path(name)
        with ZipFile(args.handoff) as archive:
            archive.extractall(work)
        report = run(work / 'vibeflow-author-handoff/bundle', work, args.rounds)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({k: v for k, v in report.items() if k not in {'samples', 'profile_counts'}}, ensure_ascii=False))
        print(json.dumps(report['profile_counts'], ensure_ascii=False))


if __name__ == '__main__':
    main()
