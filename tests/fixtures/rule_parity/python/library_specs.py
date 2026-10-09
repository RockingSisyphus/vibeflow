"""Node-owned library and public standalone BaseLib observations."""


def _case(name, title, code=None, **options):
    expected = {"should_accept": code is None, "codes": [] if code is None else [{"code": code, "severity": "error"}]}
    expected.update(options.pop("expect", {}))
    return {"id": "python.library." + name, "title": title, "family": "base-lib", "expected": expected, **options}


def _chain_cases():
    cases = []
    for package, relative, name in (("base_lib", False, "absolute"), ("base_lib", True, "relative"), ("support", False, "custom_path")):
        for length in (2, 4):
            policy = {"base_lib": {"allowed_paths": [package], "allowed_modules": [package]},
                "maintainability": {"warn_dependency_chain_length": 3, "max_dependency_chain_length": 3}}
            limitation = package == "support"
            code = "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP" if length == 4 and not limitation else None
            expected = {"metrics": {"dependency_chain.longest_chain_length": 0 if limitation else length + 1}}
            if limitation:
                expected["variants"] = {"current": {"should_accept": length != 4, "codes": ([{"code": "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP", "severity": "error"}] if length == 4 else []), "metrics": {"dependency_chain.longest_chain_length": length + 1, "exit_code": int(length == 4)}}}
            cases.append(_case("chain_" + name + "_" + str(length), "Library chain " + name + " " + str(length), code,
                source=f'from {package}.m0 import step\nclass DemoNode:\n    def run_pure(self, inputs, params):\n        return {{"demo.out": step(1)}}\n',
                library_chain={"package": package, "relative": relative, "length": length}, policy=policy, current_policy={"maintainability":policy["maintainability"]}, expect=expected,
                classification="baseline_limitation" if limitation else "preserved", notes="Both versions historically report zero Node dependency length for a custom non-base_lib module name." if limitation else "Relative imports must use the real resolved local dependency relation."))
    for package in ("base_lib", "support"):
        cases.append(_case("reachable_functions_" + package, "Reachable library function count: " + package, "BASE_LIB.COMPLEXITY.MAX_FUNCTIONS",
            source=f'from {package}.m0 import step\nclass DemoNode:\n    def run_pure(self, inputs, params):\n        return {{"demo.out": step(1)}}\n',
            library_chain={"package": package, "length": 1, "extra_functions": True},
            policy={"base_lib": {"allowed_paths": [package], "allowed_modules": [package]}, "complexity": {"max_functions": 2}}, current_policy={"complexity":{"max_functions":2}}))
    return cases


def _standalone_cases():
    sources = {
        "valid": ("def value():\n    return 1\n", None),
        "syntax": ("def broken(:\n", "BASE_LIB.SYNTAX"),
        "mutable_global": ("CACHE={}\n", "BASE_LIB.GLOBAL_STATE"),
        "global_statement": ("STATE=0\ndef change():\n    global STATE\n    STATE=1\n", "BASE_LIB.GLOBAL_STATE"),
        "side_effect": ("def value():\n    print('bad')\n    return 1\n", "BASE_LIB.SIDE_EFFECT_CALL"),
        "top_level_control": ("if True:\n    VALUE=1\n", "BASE_LIB.TOP_LEVEL_SIDE_EFFECT"),
        "project_import": ("from nodes import missing\n", "BASE_LIB.FORBIDDEN_PROJECT_IMPORT"),
        "banned_import": ("import os\n", "BASE_LIB.BANNED_IMPORT"),
        "dynamic_namespace": ("def value():\n    return globals()['unknown']\n", "BASE_LIB.SIDE_EFFECT_CALL"),
    }
    cases = [_case("scan_" + name, "Standalone BaseLib " + name, code, entrypoint="target.scan_base_lib", files={"base_lib/example.py": source}) for name, (source, code) in sources.items()]
    long = "\n".join(f"VALUE_{number}={number}" for number in range(12)) + "\n"
    cases.append(_case("scan_source_lines", "Standalone BaseLib line limit", "BASE_LIB.SOURCE.MAX_LINES", entrypoint="target.scan_base_lib", files={"base_lib/example.py": long}, purity_kwargs={"max_source_lines": 5}))
    cases.append(_case("scan_functions", "Standalone BaseLib function limit", "BASE_LIB.COMPLEXITY.MAX_FUNCTIONS", entrypoint="target.scan_base_lib", files={"base_lib/example.py": "def a():\n    return 1\ndef b():\n    return 2\n"}, purity_kwargs={"max_functions": 1}))
    return cases


def case_specs():
    cases = [*_chain_cases(), *_standalone_cases()]
    for spec in cases:
        name = spec["id"].rsplit(".", 1)[-1]
        if name in {"scan_syntax", "scan_project_import"}:
            current = {"should_accept":name == "scan_project_import", "codes":[] if name == "scan_project_import" else [{"code":"QUALITY.SYNTAX.PYTHON","severity":"error"}]}
            spec["expected"].setdefault("variants", {})["current"] = current
            spec["classification"] = "approved_change"
            spec["notes"] = "Selected canonical library Rules use shared syntax findings and actual ownership; directory names do not establish project roles."
    return cases
