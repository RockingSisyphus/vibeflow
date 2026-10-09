"""Target extraction and formal project-quality checks use real Python source."""


def _case(name, title, source, code=None, severity="warning", **options):
    expected = {"should_accept": code is None or severity != "error", "codes": [] if code is None else [{"code": code, "severity": severity}]}
    expected.update(options.pop("expect", {}))
    return {"id": "python.source." + name, "title": title, "family": "source-to-facts",
        "entrypoint": "target.analyze_python_source", "general_source": source, "expected": expected, **options}


def case_specs():
    duplicated = 'def first(a):\n    value=a+1\n    return value\ndef second(b):\n    result=b+2\n    return result\n'
    return [
        _case("syntax", "Python parser finding preserves actual source location", 'def broken(:\n', "QUALITY.SYNTAX.PYTHON", "error", expect={"located_codes": ["QUALITY.SYNTAX.PYTHON"]}),
        _case("optional_effects_off", "General source effects are optional by default", 'import subprocess\nsubprocess.run(["ignored"])\n', expect={"forbidden_codes": ["QUALITY.SIDE_EFFECT.IMPORT", "QUALITY.SIDE_EFFECT.CALL"], "metrics": {"marker": ""}}),
        _case("effect_import", "Selected general source effect import retains location", 'import subprocess\n', "QUALITY.SIDE_EFFECT.IMPORT", source_options={"check_side_effects": True}, expect={"located_codes": ["QUALITY.SIDE_EFFECT.IMPORT"]}),
        _case("effect_alias_call", "Selected general source resolves imported call alias", 'from subprocess import run as execute\nexecute(["ignored"])\n', "QUALITY.SIDE_EFFECT.CALL", source_options={"check_side_effects": True}, expect={"located_codes": ["QUALITY.SIDE_EFFECT.CALL"], "metrics": {"marker": ""}}),
        _case("required_params", "Required parameters exclude defaults and method self", 'def calculate(a,b=1,*,c,d=2):\n    return a+b+c+d\n', expect={"metrics": {"required_params_first": 2, "file.function_count": 1}}),
        _case("method_params", "Method self is excluded from required parameters", 'class Calculator:\n    def calculate(self,a,b=1):\n        return a+b\n', expect={"metrics": {"required_params_first": 1, "file.function_count": 1, "file.class_count": 1}}),
        _case("branches", "Branch and nesting facts come from real syntax", 'def calculate(a):\n    if a:\n        if a>1:\n            return 1\n    return 0\n', expect={"metrics": {"file.branch_count": 2, "file.max_nesting_depth": 2}}),
        _case("relative_import", "Relative import facts preserve resolved module and source line", '\nfrom .helper import step as compute\n', source_options={"module": "pkg.source"}, expect={"metrics": {"relative_import_resolved": True, "first_import_line": 2}}),
        _case("normalized_duplicates", "AST fingerprints normalize names and literals", duplicated, expect={"metrics": {"fingerprints_equal": True, "file.function_count": 2}}),
        _case("formal_syntax", "Formal quality CLI rejects actual invalid Python", 'def broken(:\n', "QUALITY.SYNTAX.PYTHON", "error", entrypoint="cli.quality-check", expect={"located_codes": ["QUALITY.SYNTAX.PYTHON"], "metrics": {"exit_code": 1}}),
        _case("formal_effects", "Formal quality CLI carries opt-in import and alias-call findings", 'from subprocess import run as execute\nexecute(["ignored"])\n', "QUALITY.SIDE_EFFECT.IMPORT", entrypoint="cli.quality-check", cli_args=["--check-side-effects"], expect={"codes": [{"code": "QUALITY.SIDE_EFFECT.IMPORT", "severity": "warning"}, {"code": "QUALITY.SIDE_EFFECT.CALL", "severity": "warning"}], "located_codes": ["QUALITY.SIDE_EFFECT.IMPORT", "QUALITY.SIDE_EFFECT.CALL"], "metrics": {"exit_code": 0}}),
        _case("formal_functions", "Formal quality CLI applies function parameter threshold to source facts", 'def calculate(a,b):\n    return a+b\n', "QUALITY.FUNCTION.TOO_MANY_PARAMS", entrypoint="cli.quality-check", cli_args=["--max-function-params", "1"]),
        _case("formal_duplicates", "Formal quality CLI discovers repeated function AST", duplicated, "QUALITY.DUPLICATE.AST_FINGERPRINT", entrypoint="cli.quality-check"),
    ]
