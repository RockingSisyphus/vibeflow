"""Python build arguments and application dispatch."""
import json
from vibeflow.tooling.application.result_scope import add_result_scope


def add_build_parser(subparsers):
    parser = subparsers.add_parser('build',help='build a relocatable Python workflow package')
    parser.add_argument('--workspace',required=True)
    parser.add_argument('--config',required=True)
    parser.add_argument('--out-dir',required=True)
    parser.add_argument('--profile',choices=('python-package',),default='python-package')
    parser.add_argument('--include',action='append',default=[])
    parser.add_argument('--replace',action='store_true')


def handle_build(args):
    from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
    try:
        result = build_python_aot(PythonBuildRequest(workspace=args.workspace,config=args.config,
            out_dir=args.out_dir,include=tuple(args.include),replace=args.replace))
        payload = {'status':result.health.status,'out_dir':str(result.out_dir),'entry':str(result.entry),
            'manifest':str(result.manifest),'files':list(result.files),
            'warnings':[item.to_dict() for item in result.health.warnings]}
        print(json.dumps(add_result_scope(payload,'vibeflow_build',checked_ids=(
            'config_registration','node_contract_shape','data_reachability','control_flow','target_build')),ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps(add_result_scope({'status':'ERROR','error':str(error)},'vibeflow_build',checked_ids=()),ensure_ascii=False))
        return 1
