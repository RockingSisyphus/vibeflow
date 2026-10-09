"""A01/A08/S01 public SDK and typed-record sandbox observations."""

from pathlib import Path
import json

from tests.fixtures.adaptation_regressions.common import row, run_cli, run_probe
from tests.fixtures.adaptation_regressions.core_sdk_fixtures import implementation, write_project, write_workflow
from tests.fixtures.adaptation_regressions.core_sdk_probes import (
    CACHE_PROBE, CACHE_IDENTITY_PROBE, CLI_PROJECTION_PROBE, CONTRIBUTIONS_PROBE, RECORD_PROBE,
)


CONFLICT = "RESOURCE.IMPLEMENTATION.CONFLICT"
CONTRACT = {"provides": [{"key": "value", "type": "number", "display_name": "Value"}],
            "output_semantics": {"value": ["Standalone numeric result."]}}


def _diagnostics(payload):
    if not isinstance(payload, dict):
        return []
    health = payload.get("health", payload)
    return [item for key in ("errors", "warnings", "diagnostics") for item in health.get(key, [])]


def _cli(root, kernel, command="validate", *, name=None, config="workflow.jsonc"):
    args = [command, "--workspace", str(root / "vibeflow_config.jsonc"),
            "--config", str(root / config)]
    if command == "run":
        run_root = root / "runs"
        run_number = len(tuple(run_root.iterdir())) + 1 if run_root.exists() else 1
        args += ["--input", str(root / "input.json"), "--run-root", str(run_root), "--run-id", f"{name or command}-{run_number}"]
    else:
        args += ["--json"]
    result = run_cli(root, args, kernel, name=name or command, timeout=45)
    payload = result["payload"]
    if payload is None and result["stdout"].lstrip().startswith("{"):
        try:
            payload = json.JSONDecoder().raw_decode(result["stdout"].lstrip())[0]
        except json.JSONDecodeError:
            pass
    diagnostics = _diagnostics(payload)
    actual = {"exit_code":result["exit_code"], "status":payload.get("status") if isinstance(payload,dict) else None,
              "codes":[item.get("rule_id",item.get("code")) for item in diagnostics],
              "diagnostics":diagnostics, "stdout_path":result["stdout_path"], "stderr_path":result["stderr_path"]}
    return actual, payload


def _cli_row(identifier, title, root, kernel, *, code=None, command="validate", marker=None, target_warning=None):
    actual, payload = _cli(root, kernel, command)
    expected = {"exit_code":1 if code else 0}
    failures = []
    if actual["exit_code"] != expected["exit_code"]:
        failures.append(f"exit_code expected {expected['exit_code']}, got {actual['exit_code']}")
    errors = [item for item in actual["diagnostics"] if item.get("severity") == "error"]
    if code:
        expected["target_code"] = code
        targeted = [item for item in actual["diagnostics"] if item.get("rule_id",item.get("code")) == code]
        actual["target_code"] = code if targeted else None
        if not targeted:
            failures.append(f"missing target diagnostic {code}; observed {actual['codes']}")
        for item in targeted:
            location = item.get("source_location", {})
            if item.get("severity") != "error" or not location.get("path"):
                failures.append("target diagnostic lost error severity or declaration/source location")
        for item in errors:
            if item.get("rule_id",item.get("code")) != code:
                failures.append(f"unrelated error: {item.get('rule_id',item.get('code'))}")
    elif errors:
        failures.append(f"unexpected errors: {actual['codes']}")
    if target_warning:
        actual["target_warnings"] = [item.get("rule_id",item.get("code")) for item in actual["diagnostics"]
                                     if item.get("rule_id",item.get("code","")).startswith("CASE.")]
        expected["target_warnings"] = [target_warning]
        if actual["target_warnings"] != expected["target_warnings"]:
            failures.append(f"handler findings expected {expected['target_warnings']}, got {actual['target_warnings']}")
    if marker:
        actual["business_executed"] = (root / marker).exists()
        expected["business_executed"] = not bool(code)
        if actual["business_executed"] != expected["business_executed"]:
            failures.append("business execution did not match checked-run boundary")
    if command == "run":
        business = Path(payload["run_dir"]) / "business.log" if isinstance(payload,dict) and payload.get("run_dir") else None
        actual["unsafe_business_marker"] = bool(business and business.exists() and "UNREVIEWED_ACTUAL_IMPLEMENTATION" in business.read_text())
        expected["unsafe_business_marker"] = False
        if actual["unsafe_business_marker"]:
            failures.append("checked run executed an implementation rejected by the expected review")
    return row(identifier,"A01",title,expected,actual,failures,root)


def _node_identity_cases(work, kernel):
    rows = []
    for variant in ("other_file", "same_file_other_symbol", "auto_actual", "same_source_metadata", "relative_alias", "module_alias", "symbol_alias", "delayed"):
        root = work / ("node-" + variant)
        root.mkdir(parents=True, exist_ok=True)
        (root / "safe.py").write_text('class Safe:\n    def run_pure(self, inputs, params):\n        return {"value":7}\n')
        (root / "support.py").write_text('def seven():\n    return 7\n')
        selected = ["vibeflow.process"]
        body = ""
        option = ""
        symbol = "Step"
        if variant == "other_file":
            option = f", implementations={[implementation(root/'safe.py','Safe')]!r}"
        elif variant == "same_file_other_symbol":
            body = 'class Safe:\n    def run_pure(self, inputs, params):\n        return {"value":7}\n'
            option = f", implementations={[implementation(root/'plugin.py','Safe')]!r}"
        elif variant in {"same_source_metadata", "relative_alias", "module_alias", "symbol_alias"}:
            ref = "./plugin.py" if variant == "relative_alias" else "plugin" if variant == "module_alias" else root / "plugin.py"
            kind = "module" if variant == "module_alias" else "file"
            symbol = "StepAlias" if variant == "symbol_alias" else "Step"
            extra = {"completion":"immediate", "implementation_files":[{"kind":"file","ref":"support.py"}]}
            option = f", implementations={[implementation(ref,symbol,kind=kind,extra=extra)]!r}"
        unsafe = variant in {"other_file", "same_file_other_symbol", "auto_actual"}
        node = (f'@node(type_key="case.step", contract={CONTRACT!r}, rulesets={selected!r}{option})\n'
                'class Step:\n'
                '    def run_pure(self, inputs, params):\n'
                + ('        print("UNREVIEWED_ACTUAL_IMPLEMENTATION")\n' if unsafe else '')
                + '        return {"value":7}\n')
        if variant == "symbol_alias":
            node += "StepAlias = Step\n"
        if variant == "delayed":
            (root / "late.py").write_text('class Late:\n    def run_pure(self, inputs, params):\n        return {"value":7}\n')
            node = f'Step = node(type_key="case.step", contract={CONTRACT!r}, rulesets=[], source=SourceLocator("file", "late.py", "Late"))\n'
        write_project(root, body=body, node_source=node)
        target = CONFLICT if variant in {"other_file","same_file_other_symbol"} else "NODE.EFFECT.CALL_FORBIDDEN" if unsafe else None
        rows.append(_cli_row("A01.node."+variant,"Node implementation identity: "+variant,root,kernel,code=target))
        if variant in {"other_file","auto_actual","same_source_metadata","delayed"}:
            rows.append(_cli_row("A01.node."+variant+".checked_run","Checked run uses the reviewed Node: "+variant,root,kernel,command="run",code=target))
        if variant == "same_source_metadata":
            result = run_cli(root,["inspect-resources","--workspace",str(root/'vibeflow_config.jsonc'),"--config",str(root/'workflow.jsonc'),"--kind","node","--id","case.step","--json"],kernel,name="resources")
            payload = result["payload"] or {}
            descriptors = [item['descriptor'] for item in payload.get('resources',[])]
            entry = descriptors[0]['implementations'][0] if descriptors else {}
            actual = {'exit_code':result['exit_code'],'completion':entry.get('completion'),
                      'targets':entry.get('targets'), 'support_files':[part['ref'] for part in entry.get('implementation_files',[])],
                      'source':entry.get('source')}
            expected = {'exit_code':0,'completion':'immediate','targets':['python'],
                        'support_files':[str(root/'support.py')], 'source':{'kind':'file','ref':str(root/'plugin.py'),'export':'Step'}}
            rows.append(row('A01.node.metadata_preserved','A01','Same-source explicit metadata remains public',expected,actual,project=root))
    return rows


def _rule_identity_cases(work, kernel):
    rows = []
    for variant in ("other_file", "auto", "same_source", "delayed", "builtin_alias", "handler_with_direct", "handler_with_source"):
        root = work / ("rule-" + variant)
        root.mkdir(parents=True, exist_ok=True)
        declared = root / "declared.py"
        declared.write_text('def declared_check(context,inputs,params):\n    return {"findings":[{"code":"CASE.DECLARED","severity":"warning","message":"Declared check ran","file":__file__,"line":1}]}\n')
        options = ""
        resources = ["actual_check", "checks"]
        if variant == "other_file":
            options = ", implementations=" + repr([{'language':'python','source':{'kind':'file','ref':str(declared),'export':'declared_check'}}])
        if variant in {"same_source","handler_with_direct"}:
            options = ", implementations=" + repr([{'language':'python','source':{'kind':'file','ref':str(root/'plugin.py'),'export':'actual_check'}}])
        if variant == "handler_with_direct":
            options += ', handler="vibeflow.quality.files"'
        body = (f'@rule(id="case.check"{options})\n'
                'def actual_check(context, inputs, params):\n'
                '    return {"findings":[{"code":"CASE.ACTUAL","severity":"warning","message":"Actual check ran","file":__file__,"line":1}]}\n')
        if variant in {"delayed","handler_with_source"}:
            extra = ', handler="vibeflow.quality.files"' if variant == "handler_with_source" else ''
            body = f'actual_check = rule(id="case.check", source=SourceLocator("file","declared.py","declared_check"){extra})\n'
        if variant == "builtin_alias":
            body = ('from dataclasses import replace\nfrom vibeflow.builtin import builtin_rule_resources\n'
                    'from vibeflow.targets.python.sdk import ResourceDefinition\n'
                    'builtin = next(item for item in builtin_rule_resources()[0] if item.id=="vibeflow.quality.files")\n'
                    'actual_check = ResourceDefinition(replace(builtin,id="case.check",handler=builtin.id))\n')
        params = {"max_file_lines":1} if variant == "builtin_alias" else {}
        body += f'checks = ruleset(id="case.checks",calls=[{{"id":"check","rule_id":"case.check","params":{params!r}}}],entrypoints={{"static":["check"]}})\n'
        write_project(root,body=body,resources=resources,selections=['case.checks'])
        code = CONFLICT if variant in {"other_file","handler_with_direct","handler_with_source"} else "QUALITY.FILE.MAX_LINES" if variant == "builtin_alias" else None
        warning = "CASE.DECLARED" if variant == "delayed" else "CASE.ACTUAL" if code is None else None
        rows.append(_cli_row('A01.rule.'+variant,'Rule implementation identity: '+variant,root,kernel,code=code,target_warning=warning))
    return rows


def _record_cases(work, kernel):
    root = work / 'records'
    result = run_probe(root,RECORD_PROBE,kernel,name='record_snapshot')
    payload = result['payload'] or {}
    expectations = {'tuple':{'input_objects':12,'record_objects':12,'context_objects':12,'shared':True},
        'mapping':{'input_objects':12,'record_objects':12,'context_objects':12,'shared':True},
        'mixed':{'record_objects':4,'shared':True,'readonly':True,'isolated':True},
        'native':{'type_preserved':True,'shared':True},
        **{'cycle_'+kind:{'rejected':True,'cycle_message':True} for kind in ('list','mapping','tuple_list','dataclass')},
        'json_boundary':{'value':[[1,2],[1,2]],'ordinary_json':True}}
    rows = [row('A08.snapshot.'+name,'A08','Record snapshot: '+name,{'probe_exit':0,**expected},
                {'probe_exit':result['exit_code'],**payload.get(name,{})},project=root) for name,expected in expectations.items()]
    for variant in ('same_dag','equal_tree','different_leaf','mapping_order','integer_float','integer_boolean','signed_zero','native_types','native_vs_json','set_vs_sequence'):
        result = run_probe(root,CACHE_PROBE,kernel,args=[variant],name='cache_'+variant)
        expected = {'status':'PASS','provider':2,'consumer':1 if variant in {'same_dag','equal_tree','mapping_order'} else 2,
                    'internal_record_projection':0}
        rows.append(row('A08.cache.'+variant,'A08','Cache retains content and type semantics: '+variant,expected,result['payload'] or {'probe_exit':result['exit_code']},project=root))
    for variant in ('port','type_id','params','source','target','phase','rule_id','no_source_identity','call_scope'):
        result = run_probe(root,CACHE_IDENTITY_PROBE,kernel,args=[variant],name='cache_identity_'+variant)
        rows.append(row('A08.cache_identity.'+variant,'A08','Cache eligibility and identity boundary: '+variant,
                        {'statuses':['PASS','PASS'],'provider':2,'consumer':2},result['payload'] or {'probe_exit':result['exit_code']},project=root))
    return rows


RECORD_RULES = '''
from pathlib import Path
from collections.abc import Mapping
import json
from vibeflow.core.findings import HealthFinding

def mark(value):
    with Path(__file__).with_name("record.marker").open("a") as stream:
        stream.write(json.dumps(value)+"\\n")

@rule(id="case.provider", outputs={"data":"case.data"})
def provide(context, inputs, params):
    mark({"kind":"provider"})
    value = 1
    for _ in range(8):
        value = (value, value)
    CYCLE
    return RuleResult({"data":RuleRecord("case.data",value)})

@rule(id="case.consumer", inputs={"data":"case.data"}, scope="source")
def consume(context, inputs, params):
    seen, pending = set(), [inputs["data"].value]
    while pending:
        current = pending.pop()
        if isinstance(current, tuple) and id(current) not in seen:
            seen.add(id(current))
            pending.extend(current)
    mark({"kind":"consumer", "objects":len(seen), "shared":inputs["data"].value[0] is inputs["data"].value[1]})
    return RuleResult(findings=(HealthFinding(rule_id="CASE.RECORD",severity="warning",object_type="node",object_id="case.step",
        message="Bounded record summary",source_location={"path":__file__,"line":1}),))

checks = ruleset(id="case.records", calls=[{"id":"provider","rule_id":"case.provider"},{"id":"consumer","rule_id":"case.consumer"}],
    relations=[{"source":"consumer","target":"provider","kind":"requires","bindings":{"data":"data"}}], entrypoints={"static":["consumer"]})
'''


def _record_cli_cases(work, kernel):
    rows = []
    for variant in ('shared','cycle','provider_error'):
        root = work / ('record-cli-'+variant)
        body = RECORD_RULES.replace('    CYCLE','    value = []; value.append(value)' if variant=='cycle' else '')
        if variant == 'provider_error':
            body = body.replace('return RuleResult({"data":RuleRecord("case.data",value)})',
                'return RuleResult({"data":RuleRecord("case.data",value)}, (HealthFinding(rule_id="CASE.PROVIDER",severity="error",object_type="node",object_id="case.step",message="Records remain valid",source_location={"path":__file__,"line":1}),))')
        node = '@node(type_key="case.step",contract={},rulesets=["case.records"])\nclass Step:\n    def run_pure(self,inputs,params):\n        return {}\n'
        write_project(root,body=body,resources=['provide','consume','checks'],node_source=node,calls=2)
        workflow = json.loads((root/'workflow.jsonc').read_text())
        workflow['pipeline'].pop('outputs')
        (root/'workflow.jsonc').write_text(json.dumps(workflow,indent=2)+'\n')
        result = run_probe(root,CLI_PROJECTION_PROBE,kernel,name='formal_validate')
        payload = result['payload'] or {}
        findings = payload.get('findings',[])
        observations = payload.get('observations',[])
        consumer = [item for item in observations if item['kind']=='consumer']
        actual = {'probe_exit':result['exit_code'],'cli_exit_code':payload.get('cli_exit_code'),
                  'provider_calls':sum(item['kind']=='provider' for item in observations), 'consumer_calls':len(consumer),
                  'consumer_objects':[item['objects'] for item in consumer], 'consumer_shared':[item['shared'] for item in consumer],
                  'codes':[item['code'] for item in findings], 'projections':payload.get('projections',{}),
                  'findings':findings}
        expected = {'probe_exit':0,'cli_exit_code':0 if variant=='shared' else 1,'provider_calls':2,
                    'consumer_calls':0 if variant=='cycle' else 1,'consumer_objects':[] if variant=='cycle' else [8],
                    'consumer_shared':[] if variant=='cycle' else [True]}
        failures = []
        for key,value in expected.items():
            if actual.get(key)!=value:
                failures.append(f'{key}: expected {value!r}, got {actual.get(key)!r}')
        expected_codes = {'RULE.EXECUTION','RULE.INPUT.UNAVAILABLE'} if variant=='cycle' else {'CASE.PROVIDER','CASE.RECORD'} if variant=='provider_error' else {'CASE.RECORD'}
        if set(actual['codes']) != expected_codes:
            failures.append(f'target codes expected {expected_codes}, got {actual["codes"]}')
        if variant!='cycle':
            for category in ('cache','diagnostic'):
                if actual['projections'].get(category)!=0:
                    failures.append(f'internal {category} projection still expands records: {actual["projections"].get(category)}')
            expected['projections'] = {'cache':0,'diagnostic':0}
            warning = next((item for item in findings if item['code']=='CASE.RECORD'),{})
            associations = {(item.get('owner'),item.get('node')) for item in warning.get('calls',[])}
            if len(associations)!=2:
                failures.append('source finding lost one of the two real Node call associations')
        rows.append(row('A08.formal.'+variant,'A08','Formal provider/consumer and finding dedup: '+variant,expected,actual,failures,root))
    return rows


def _contribution_cases(work, kernel):
    root = work / 'fixed-contributions'
    result = run_probe(root,CONTRIBUTIONS_PROBE,kernel,name='fixed_contributions')
    payload = result['payload'] or {}
    expected = {'internal_projections':0,'facts_projections':1,'facts_resources':1,'fixed_resources_same':True,
                'descriptor_shared':True,'catalogs_distinct':True,'immutable':True,'config_values':[1,2]}
    rows = [row('S01.fixed_contribution','S01','One immutable definition; only report boundary serializes',expected,payload,project=root)]
    for variant in ('raw_entry','wrong_origin','wrong_descriptor','duplicate'):
        expected = {'rejected':True}
        if variant == 'wrong_descriptor':
            expected['code'] = 'DESCRIPTOR.TYPE'
        if variant == 'duplicate':
            expected.update(code='RULE.RESOURCE.DUPLICATE',origins={'current':{'path':'second.py','plugin_id':'case.plugin'},
                                                                'previous':{'path':'first.py','plugin_id':'case.plugin'}})
        rows.append(row('S01.public_validation.'+variant,'S01','Direct public contributions stay validated: '+variant,
                        expected,payload.get('invalid',{}).get(variant,{}),project=root))
    root = work / 'workflow-isolation'
    body = '''
from pathlib import Path
import json
@rule(id="case.config")
def inspect_config(context, inputs, params):
    with Path(__file__).with_name("config.marker").open("a") as stream:
        stream.write(json.dumps({"mode":context.facts["plugins"]["case.resources"]["mode"]})+"\\n")
    return RuleResult()
checks = ruleset(id="case.configs",calls=[{"id":"check","rule_id":"case.config"}],entrypoints={"static":["check"]})
'''
    write_project(root,body=body,resources=['inspect_config','checks'],selections=['case.configs'],config={'mode':1})
    write_workflow(root,name='second.jsonc',config={'mode':2})
    statuses = []
    for index,config in enumerate(('workflow.jsonc','second.jsonc','workflow.jsonc')):
        actual, _ = _cli(root,kernel,name='isolation_'+str(index),config=config)
        statuses.append(actual['exit_code'])
    values = [json.loads(line)['mode'] for line in (root/'config.marker').read_text().splitlines()] if (root/'config.marker').exists() else []
    rows.append(row('S01.workflow_isolation','S01','Workflow config does not rewrite the fixed plugin definition',
                    {'exit_codes':[0,0,0],'observed_modes':[1,2,1]}, {'exit_codes':statuses,'observed_modes':values},project=root))
    return rows


def observe(work: Path, kernel: Path, toolchain: Path | None = None, renderer: Path | None = None) -> list[dict]:
    work.mkdir(parents=True, exist_ok=True)
    return [*_node_identity_cases(work,kernel), *_rule_identity_cases(work,kernel),
            *_record_cases(work,kernel), *_record_cli_cases(work,kernel), *_contribution_cases(work,kernel)]
