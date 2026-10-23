"""CLI for an already built Python artifact; no workspace is required."""
import argparse
import json
from pathlib import Path
import sys

from vibeflow.tooling.application.python.bundle import load_bundle


def main(path, argv=None):
    from vibeflow.tooling.application.python.cli import _add_runtime_options, _runtime_options_from_args
    from vibeflow.tooling.application.python.run_directory import parse_run_id_argument
    parser = argparse.ArgumentParser(description='Run a prepared Python workflow', allow_abbrev=False)
    sub = parser.add_subparsers(dest='command',required=True)
    for command in ('run','delegate-cli'):
        child = sub.add_parser(command, allow_abbrev=False)
        if command == 'run':
            child.add_argument('--input')
        child.add_argument('--run-root')
        child.add_argument('--run-id', type=parse_run_id_argument)
        child.add_argument('--entry', help='named workflow entry')
        _add_runtime_options(child)
    values = list(sys.argv[1:] if argv is None else argv)
    delegated = []
    if '--' in values and values[0] == 'delegate-cli':
        separator = values.index('--')
        values,delegated = values[:separator],values[separator + 1:]
    args = parser.parse_args(values)
    delegate = args.command == 'delegate-cli'
    from vibeflow.tooling.application.python.run_directory import prepare_run_dir as _prepare_run_dir
    from vibeflow.tooling.application.python.execution import (_new_run_id, _write_execution_report, _checked_run_error_payload, CheckedRunError)
    from vibeflow.targets.python.runtime.observation import observe_run
    from vibeflow.targets.python.runtime.console_capture import capture_process_console
    from vibeflow.tooling.project.diagnostic_sink import core_diagnostic_sink
    from vibeflow.tooling.application.python.run_observation import print_run_report
    from vibeflow.tooling.application.python.cli.delegate_cli import _finish_with_log, _artifact_line, _single_line
    directory = None
    try:
        bundle = load_bundle(path)
        options = bundle.effective_options(_runtime_options_from_args(args))
        run_id = _new_run_id() if args.run_id is None else args.run_id
        directory = _prepare_run_dir(Path(args.run_root or 'runs').resolve(), run_id)
        with observe_run(directory, options) as observer:
            with core_diagnostic_sink(observer.write_kernel), capture_process_console(observer):
                try:
                    initial = {'cli.argv':delegated} if delegate else {}
                    if not delegate and args.input:
                        initial = json.loads(Path(args.input).read_text(encoding='utf-8'))
                    run = bundle.run
                    if bundle.workflow.entry_mode == 'async':
                        import asyncio
                        run = lambda *values, **settings: asyncio.run(bundle.run_async(*values, **settings))
                    result = run(initial,runtime_options=options,
                        run_id=run_id,delegate_cli=delegate,_prepared_run_dir=directory,entry=args.entry)
                    if delegate:
                        from vibeflow.tooling.application.python.delegate_contract import extract_delegate_cli_exit_code
                        code,error = extract_delegate_cli_exit_code(result.context)
                        if error:
                            raise ValueError(error)
                        return _finish_with_log(directory,[_artifact_line(directory),
                            f'INFO CLI.DELEGATE.END status={result.health.status} exit_code={code}'],code)
                    from vibeflow.targets.python.runtime.summaries import summarize_mapping
                    payload = _write_execution_report(result)
                    payload['output'] = summarize_mapping(result.context.to_dict())
                    print_run_report(payload)
                    return 0
                except (Exception, SystemExit) as error:
                    observer.transition('failed', str(error))
                    if delegate:
                        return _finish_with_log(directory,[f'ERROR CLI.DELEGATE.FAIL stage=runtime type={type(error).__name__}',
                            _artifact_line(directory),'INFO CLI.DELEGATE.END status=ERROR exit_code=1'],1)
                    print_run_report(_checked_run_error_payload(error) if isinstance(error,CheckedRunError) else
                        {'status':'ERROR','error':str(error),'run_dir':str(directory)})
                    return 1
    except Exception as error:
        if delegate:
            print(f'vibeflow delegate-cli: {_single_line(error)}',file=sys.stderr)
        else:
            print_run_report({'status':'ERROR','error':str(error)})
        return 1
