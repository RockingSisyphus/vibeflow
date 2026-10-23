"""Rule capability specifications; expectations describe desired parity."""

from textwrap import indent


def _case(name, title, family, body='return {"demo.out": 1}', code=None, severity="error", **options):
    expected = {"should_accept": code is None or severity != "error", "codes": [] if code is None else [{"code": code, "severity": severity}]}
    expected.update(options.pop("expect", {}))
    source = options.pop("source", "class DemoNode:\n    def run_pure(self, inputs, params):\n" + indent(body, "        ") + "\n")
    return {"id": "python." + name, "title": title, "family": family, "source": source, "expected": expected, **options}


def _contract_cases():
    requirement = {"type": "demo.out", "cardinality": "exactly_one", "display_name": "Input"}
    provider = {"key": "demo.out", "type": "demo.out", "display_name": "Result"}
    route = {"key": "flow.route", "type": "flow.route", "display_name": "Route"}
    return [
        _case("contract.valid", "Complete ordinary contract", "contract"),
        _case("contract.decision_missing_route", "Decision lacks a route output", "contract", code="NODE.DECISION.MISSING_ROUTE_OUTPUT", flow_kind="decision"),
        _case("contract.decision_route", "Decision explicitly provides a route", "contract", body='return {"flow.route": True}', flow_kind="decision", contract={"provides": [route], "output_semantics": {"flow.route": ["selected branch"]}}),
        _case("contract.overlap", "Required type overlaps a provided key", "contract", code="NODE.CONTRACT.CONTRACT_OVERLAP", contract={"requires": [requirement], "input_semantics": {"demo.out": ["input"]}}),
        _case("contract.example_missing_params", "Example omits params", "contract", code="NODE.MAINTAINABILITY.EXAMPLE_SHAPE", severity="warning", contract={"examples": [{"inputs": {}}]}),
        _case("contract.example_missing_inputs", "Example omits inputs", "contract", code="NODE.MAINTAINABILITY.EXAMPLE_SHAPE", severity="warning", contract={"examples": [{"params": {}}]}),
        _case("contract.example_bad_params", "Example params has non-mapping shape", "contract", code="NODE.MAINTAINABILITY.EXAMPLE_SHAPE", severity="warning", contract={"examples": [{"inputs": {}, "params": 1}]}),
        _case("contract.example_outputs_removed", "Removed example outputs is rejected", "contract", code="NODE.PURITY.EXAMPLE_OUTPUTS_REMOVED", contract={"examples": [{"inputs": {}, "params": {}, "outputs": {}}]}),
        _case("contract.duplicate_provider", "Duplicate provider key is rejected", "contract", code="NODE.CONTRACT.CONTRACT_DUPLICATE_KEY", contract={"provides": [provider, provider]}, expect={"variants": {"current": {"codes": [{"code": "NODE.INSPECT.LOAD_ERROR", "severity": "error"}]}}}),
        _case("contract.semantics_missing", "Declared output lacks semantics", "contract", code="NODE.CONTRACT.CONTRACT_SEMANTICS_MISSING", contract={"output_semantics": {}}, expect={"variants": {"current": {"codes": [{"code": "NODE.INSPECT.LOAD_ERROR", "severity": "error"}]}}}),
        _case("contract.semantics_extra", "Semantics contains an undeclared key", "contract", code="NODE.CONTRACT.CONTRACT_SEMANTICS_EXTRA", contract={"output_semantics": {"demo.out": ["result"], "extra": ["not provided"]}}, expect={"variants": {"current": {"codes": [{"code": "NODE.INSPECT.LOAD_ERROR", "severity": "error"}]}}}),
        _case("contract.temporary_key", "Unstable temporary key warning", "contract", body='return {"tmp.out": 1}', code="NODE.MAINTAINABILITY.TEMPORARY_KEY", severity="warning", contract={"provides": [{"key": "tmp.out", "type": "tmp.out", "display_name": "Temporary"}], "output_semantics": {"tmp.out": ["temporary"]}}),
        _case("contract.confusing_key", "Nonstandard key spelling warning", "contract", body='return {"Tmp Key": 1}', code="NODE.MAINTAINABILITY.CONFUSING_KEY_NAME", severity="warning", contract={"provides": [{"key": "Tmp Key", "type": "Tmp Key", "display_name": "Temporary"}], "output_semantics": {"Tmp Key": ["temporary"]}}),
    ]


def _interface_cases():
    prefixes = {
        "missing_run_pure": "class DemoNode:\n    def _helper(self):\n        return 1\n",
        "run_pure_signature": "class DemoNode:\n    def run_pure(self, inputs):\n        return {\"demo.out\": 1}\n",
        "async_run_pure": "class DemoNode:\n    async def run_pure(self, inputs, params):\n        return {\"demo.out\": 1}\n",
        "init_signature": "class DemoNode:\n    def __init__(self, value):\n        self.value=value\n    def run_pure(self, inputs, params):\n        return {\"demo.out\": 1}\n",
        "context_run_forbidden": "class DemoNode:\n    def run(self, context):\n        return {}\n    def run_pure(self, inputs, params):\n        return {\"demo.out\": 1}\n",
        "public_callable": "class DemoNode:\n    def public_helper(self):\n        return 1\n    def run_pure(self, inputs, params):\n        return {\"demo.out\": 1}\n",
    }
    cases = [_case("interface." + name, name.replace("_", " "), "node-interface", source=source,
                   code="NODE.CONTRACT." + name.upper(),
                   **({"classification":"approved_change", "expect":{"variants":{"current":{"codes":[{"code":"NODE.CONTRACT.COMPLETION","severity":"error"}]}}},
                       "notes":"An async implementation is supported; this fixture still declares immediate completion."}
                      if name == "async_run_pure" else {})) for name, source in prefixes.items()]
    cases.append(_case("interface.private_helper", "Private local helper is allowed", "node-interface", source='class DemoNode:\n    def _helper(self):\n        return 1\n    def run_pure(self, inputs, params):\n        return {"demo.out": self._helper()}\n'))
    cases.append(_case("authority.class_metadata_removed", "Canonical declaration replaces implementation class metadata", "declaration-authority", baseline_metadata=False, code="NODE.CONTRACT.MISSING_NODE_INFO", classification="approved_change", expect={"variants": {"current": {"should_accept": True, "codes": []}}}, notes="The current project still declares the complete Node resource; only the execution class has no legacy attributes."))
    return cases


def _metric_cases():
    long_body = "\n".join(["value=1", *("value=value+1" for _ in range(65)), 'return {"demo.out": value}'])
    branches = 'value=1\nif params.get("a"):\n    value+=1\nif params.get("b"):\n    value+=1\nif params.get("c"):\n    value+=1\nreturn {"demo.out": value}'
    nested = 'value=1\nif params.get("a"):\n    if params.get("b"):\n        value+=1\nreturn {"demo.out": value}'
    helper_source = 'class DemoNode:\n    def _a(self):\n        return 1\n    def _b(self):\n        return 2\n    def run_pure(self, inputs, params):\n        return {"demo.out": self._a()+self._b()}\n'
    cases = [
        _case("metrics.source_lines", "Source line limit", "node-metrics", body=long_body, code="NODE.PURITY.SOURCE_TOO_LARGE", policy={"node_source": {"max_lines": 40}}),
        _case("metrics.source_bytes", "UTF-8 source byte limit", "node-metrics", body='text="' + "界" * 400 + '"\nreturn {"demo.out": text}', code="NODE.PURITY.SOURCE_BYTES_TOO_LARGE", policy={"node_source": {"max_bytes": 900}}),
        _case("metrics.source_warning", "Source warning threshold", "node-metrics", body=long_body, code="NODE.PURITY.SOURCE_NEAR_LIMIT", severity="warning", policy={"node_source": {"max_lines": 500, "warn_lines": 40}}),
        _case("metrics.functions", "Function count limit", "node-metrics", source=helper_source, code="NODE.MAINTAINABILITY.COMPLEXITY_MAX_FUNCTIONS", policy={"complexity": {"max_functions": 2}}, expect={"metrics": {"function_count": 3}}),
        _case("metrics.functions_allowed", "Function count within configured limit", "node-metrics", source=helper_source, policy={"complexity": {"max_functions": 4}}, expect={"metrics": {"function_count": 3}}),
        _case("metrics.branches", "Branch count limit", "node-metrics", body=branches, code="NODE.MAINTAINABILITY.COMPLEXITY_MAX_BRANCHES", policy={"complexity": {"max_branches": 2}}),
        _case("metrics.nesting", "Nesting depth limit", "node-metrics", body=nested, code="NODE.MAINTAINABILITY.COMPLEXITY_MAX_NESTING_DEPTH", policy={"complexity": {"max_nesting_depth": 1}}),
    ]
    for length, severity in ((3, "warning"), (5, "error")):
        methods = "".join(f"    def _m{i}(self):\n        return " + (f"self._m{i+1}()\n" if i+1 < length else "1\n") for i in range(1, length))
        source = 'class DemoNode:\n    def run_pure(self, inputs, params):\n        return {"demo.out": self._m1()}\n' + methods
        cases.append(_case("metrics.call_chain_" + severity, "Internal call chain " + severity, "node-metrics", source=source, code="NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP", severity=severity, policy={"maintainability": {"warn_call_chain_length": 3, "max_call_chain_length": 4}}))
    cases.append(_case("metrics.recursive_helper", "Recursive internal helper", "node-metrics", source='class DemoNode:\n    def _loop(self):\n        return self._loop()\n    def run_pure(self, inputs, params):\n        return {"demo.out": self._loop()}\n', code="NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN"))
    schema = {name: {"type": "integer"} for name in ("a", "b", "c")}
    for limit in (2, 4):
        cases.append(_case("metrics.configured_params_" + str(limit), "Configured parameter count " + str(limit), "node-metrics", entrypoint="target.validate_graph_health", contract={"params_schema": schema, "params_defaults": {name: 1 for name in schema}}, purity_kwargs={"max_params": limit}, code="NODE.MAINTAINABILITY.COMPLEXITY_MAX_PARAMS" if limit == 2 else None))
    return cases


def _purity_cases():
    bodies = {
        "print": ('print("forbidden")', "NODE.EFFECT.CALL_FORBIDDEN"),
        "dynamic_eval": ('eval("1+1")', "NODE.PURITY.BANNED_CALL"),
        "open": ('open("missing.txt")', "NODE.EFFECT.CALL_FORBIDDEN"),
        "setattr": ('setattr(self,"value",1)', "NODE.PURITY.MONKEY_PATCH"),
        "resource_field": ('self.session=None', "NODE.PURITY.RESOURCE_FIELD"),
        "input_assign": ('inputs["demo.in"]=1', "NODE.PURITY.INPUT_MUTATION"),
        "input_alias_mutation": ('value=inputs["demo.in"]\nvalue.append(1)', "NODE.PURITY.INPUT_MUTATION"),
        "input_delete": ('del inputs["demo.in"]', "NODE.PURITY.INPUT_MUTATION"),
        "internal_while": ('while False:\n    pass', "NODE.PURITY.INTERNAL_LOOP"),
        "generator": ('yield {"demo.out": 1}', "NODE.PURITY.GENERATOR_RUN_PURE"),
        "system_exit": ('raise SystemExit(1)', "NODE.EFFECT.CALL_FORBIDDEN"),
        "ambient_module_mutation": ('import math\nmath.pi=0', "NODE.PURITY.GLOBAL_STATE"),
    }
    cases = []
    for name, (body, code) in bodies.items():
        cases.append(_case("purity." + name, name.replace("_", " "), "purity", body=body + '\nreturn {"demo.out": 1}', code=code))
    cases.extend([
        _case("purity.local_mutation", "Mutation of a locally owned list", "purity", body='value=[]\nvalue.append(1)\nreturn {"demo.out": value}'),
        _case("purity.dynamic_output", "Dynamic output key", "contract-output", body='key="demo.out"\nreturn {key: 1}', code="NODE.PURITY.DYNAMIC_OUTPUT_KEY"),
        _case("purity.undeclared_output", "Undeclared returned output", "contract-output", body='return {"extra.out": 1}', code="NODE.PURITY.UNDECLARED_OUTPUT"),
        _case("purity.missing_output", "Missing declared returned output", "contract-output", body='return {}', code="NODE.PURITY.MISSING_OUTPUT"),
        _case("purity.runtime_dispatch", "Input-supplied callable warning", "purity", body='callback=inputs["demo.in"]["value"]\nreturn {"demo.out": callback()}', code="NODE.EFFECT.RUNTIME_DISPATCH.UNDECLARED", severity="warning", contract={"requires": [{"type": "demo.in", "cardinality": "exactly_one", "display_name": "Input"}], "input_semantics": {"demo.in": ["callable"]}}),
        _case("selection.empty", "Explicit empty selection is unconstrained", "ruleset-selection", body='print("unconstrained")\nreturn {"demo.out": 1}', code="NODE.EFFECT.CALL_FORBIDDEN", rulesets=[], classification="approved_change", expect={"variants": {"current": {"should_accept": True, "codes": [], "metrics": {"effect_scope": "unconstrained"}}}}),
        _case("selection.process_terminal", "Process explicitly selects terminal effect policy", "ruleset-selection", body='print("terminal")\nreturn {"demo.out": 1}', code="NODE.EFFECT.CALL_FORBIDDEN", rulesets=["vibeflow.io"], classification="approved_change", expect={"variants": {"current": {"should_accept": True, "codes": [], "metrics": {"effect_scope": "terminal"}}}}),
        _case("selection.external_no_grant", "External metadata no longer grants implicit trust", "ruleset-selection", body='print("external")\nreturn {"demo.out": 1}', node_fields={"external": True}, code="NODE.EFFECT.CALL_FORBIDDEN", classification="approved_change", expect={"variants": {"baseline": {"should_accept": True, "codes": []}}}),
    ])
    return cases


def _import_cases():
    cases = [
        _case("imports.allowed_math", "Pure mathematical import", "imports", body='import math\nreturn {"demo.out": math.sqrt(4)}'),
        _case("imports.allowed_urllib_parse", "Allowed urllib.parse module", "imports", body='from urllib.parse import urlparse\nreturn {"demo.out": urlparse("https://example.com").scheme}'),
        _case("imports.os", "OS import in execution method", "imports", body='import os\nreturn {"demo.out": os.getenv("PATH")}', code="NODE.EFFECT.IMPORT_FORBIDDEN"),
        _case("imports.urllib_request", "Forbidden urllib.request module", "imports", body='from urllib.request import urlopen\nreturn {"demo.out": 1}', code="NODE.EFFECT.IMPORT_FORBIDDEN"),
        _case("imports.alias_eval", "Dynamic code through an import alias", "imports", body='from builtins import eval as execute\nexecute("1")\nreturn {"demo.out": 1}', code="NODE.PURITY.BANNED_CALL"),
        _case("imports.ffi_policy_allow", "Import allowlist does not legalize FFI under NoEffect", "imports", body='import ctypes\nreturn {"demo.out": 1}', code="NODE.EFFECT.IMPORT_FORBIDDEN", policy={"imports": {"allowed_roots": ["ctypes"], "banned_roots": []}}),
        _case("imports.top_level_call", "Import-time call is rejected before its marker", "import-execution", source='open(__MARKER__, "w").write("module executed")\nclass DemoNode:\n    def run_pure(self, inputs, params):\n        return {"demo.out": 1}\n', code="NODE.IMPORT.SIDE_EFFECT", expect={"metrics": {"marker": ""}, "variants": {"baseline": {"codes": [{"code": "NODE.INSPECT.LOAD_ERROR", "severity": "error"}]}}}, notes="Baseline pre-import source guard transports this rejection through the inspection load-error code."),
        _case("imports.mutable_module", "Import-time mutable module state", "import-execution", source='CACHE={}\nclass DemoNode:\n    def run_pure(self, inputs, params):\n        return {"demo.out": 1}\n', code="NODE.IMPORT.SIDE_EFFECT", expect={"variants": {"baseline": {"codes": [{"code": "NODE.PURITY.MODULE_GLOBAL_STATE", "severity": "error"}]}}}),
        _case("imports.function_default_call", "Function default is rejected before its marker", "import-execution", source='class DemoNode:\n    def _helper(self, value=open(__MARKER__, "w").write("default executed")):\n        return value\n    def run_pure(self, inputs, params):\n        return {"demo.out": self._helper()}\n', code="NODE.IMPORT.SIDE_EFFECT", expect={"metrics": {"marker": ""}, "variants": {"baseline": {"codes": [{"code": "NODE.INSPECT.LOAD_ERROR", "severity": "error"}]}}}),
        _case("imports.class_decorator", "Class decorator is rejected before its marker", "import-execution", source='def decorate(value):\n    open(__MARKER__, "w").write("decorator executed")\n    return value\n@decorate\nclass DemoNode:\n    def run_pure(self, inputs, params):\n        return {"demo.out": 1}\n', code="NODE.IMPORT.SIDE_EFFECT", expect={"metrics": {"marker": ""}, "variants": {"baseline": {"codes": [{"code": "NODE.INSPECT.LOAD_ERROR", "severity": "error"}]}}}),
    ]
    helper = 'def change(value):\n    value["demo.in"]=1\n    return 1\n'
    cases.append(_case("helpers.same_file_input_mutation", "Reachable same-file helper mutates input", "helper-ownership", source=helper+'class DemoNode:\n    def run_pure(self, inputs, params):\n        return {"demo.out": change(inputs)}\n', code="NODE.PURITY.INPUT_MUTATION"))
    cases.append(_case("helpers.cross_file_input_mutation", "Reachable cross-file helper mutates input", "helper-ownership", source='from helpers import change\nclass DemoNode:\n    def run_pure(self, inputs, params):\n        return {"demo.out": change(inputs)}\n', files={"helpers.py": helper}, code="NODE.PURITY.INPUT_MUTATION", classification="new_feature", expect={"variants": {"baseline": {"should_accept": True, "codes": []}}}, notes="Legacy static inspection only followed module-local helper bodies; current SourceContext resolves cross-file symbol ownership."))
    return cases


def case_specs():
    return [*_contract_cases(), *_interface_cases(), *_metric_cases(), *_purity_cases(), *_import_cases()]
