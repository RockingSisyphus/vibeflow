import ast

from tests.unit.strict_support import *

from vibeflow.node import (
    EFFECT_SCOPE_NONE,
    EFFECT_SCOPE_PYTHON_IO,
    EFFECT_SCOPE_TERMINAL,
    EFFECT_SCOPE_TRUSTED,
    effective_effect_scope,
)
from vibeflow.rendering.architecture_document import build_architecture_document
from vibeflow.policy import EffectivePolicy, apply_policy_to_findings
from vibeflow.purity.effects import call_violation
from vibeflow.purity.types import _SourceInfo
from vibeflow.purity.validators import _validate_examples


@pytest.fixture(autouse=True)
def _effect_example_artifact_guard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield
    assert not (tmp_path / "artifact.txt").exists()
    assert not (tmp_path / "artifact-io.txt").exists()
    assert not (tmp_path / "artifact.db").exists()


class IoExampleRaisesNode:
    NODE_INFO = NodeInfo("test.io_raises", "IO Raises", "test", "Exercises terminal IO.", "0.1.0", "io")
    CONTRACT = NodeContract(
        provides=(DataProvider("effect.out", "effect.out"),),
        output_semantics={"effect.out": ("effect output",)},
        output_schema={"effect.out": {"type": "number"}},
        examples=({"inputs": {}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        raise RuntimeError("effectful examples must not execute")


class IoExampleParamsGapNode(IoExampleRaisesNode):
    NODE_INFO = NodeInfo("test.io_params_gap", "IO Params Gap", "test", "Exercises terminal IO params.", "0.1.0", "io")
    CONTRACT = NodeContract(
        provides=(DataProvider("effect.out", "effect.out"),),
        output_semantics={"effect.out": ("effect output",)},
        output_schema={"effect.out": {"type": "number"}},
        examples=({"inputs": {}, "params": {"undeclared": True}},),
    )

    def run_pure(self, inputs, params):
        raise RuntimeError("effectful examples must not execute")


class ExternalExampleRaisesNode:
    NODE_INFO = NodeInfo(
        "test.external_raises",
        "External Raises",
        "test",
        "Exercises a trusted external implementation.",
        "0.1.0",
        "process",
        external=True,
    )
    CONTRACT = NodeContract(
        provides=(DataProvider("effect.out", "effect.out"),),
        output_semantics={"effect.out": ("effect output",)},
        output_schema={"effect.out": {"type": "number"}},
        examples=({"inputs": {}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        raise RuntimeError("trusted examples must not execute")


class PureExampleRaisesNode:
    NODE_INFO = NodeInfo("test.pure_raises", "Pure Raises", "test", "Exercises pure examples.", "0.1.0", "process")
    CONTRACT = NodeContract(
        provides=(DataProvider("effect.out", "effect.out"),),
        output_semantics={"effect.out": ("effect output",)},
        output_schema={"effect.out": {"type": "number"}},
        examples=({"inputs": {}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        raise RuntimeError("pure examples still execute")


class PureExampleSystemExitNode:
    def run_pure(self, inputs, params):
        raise SystemExit(0)


class ExternalCoverageGapNode(ExternalExampleRaisesNode):
    NODE_INFO = NodeInfo(
        "test.external_gap",
        "External Gap",
        "test",
        "Exercises trusted example coverage.",
        "0.1.0",
        "process",
        external=True,
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("effect.in", "exactly_one"),),
        provides=(DataProvider("effect.out", "effect.out"),),
        input_semantics={"effect.in": ("effect input",)},
        output_semantics={"effect.out": ("effect output",)},
        output_schema={"effect.out": {"type": "number"}},
        examples=({"inputs": {}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        raise RuntimeError("trusted examples must not execute")


class DocumentGlobalMutationNode:
    NODE_INFO = NodeInfo("test.document_global", "Document Global", "test", "Writes a document.", "0.1.0", "document")
    CONTRACT = NodeContract(examples=({"inputs": {}, "params": {}},))

    def run_pure(self, inputs, params):
        global DOCUMENT_STATE
        DOCUMENT_STATE = 1
        return {}


class PolicyCannotElevateNode:
    NODE_INFO = NodeInfo("test.policy_escape", "Policy Escape", "test", "Attempts policy elevation.", "0.1.0", "process")
    CONTRACT = NodeContract(examples=({"inputs": {}, "params": {}},))

    def run_pure(self, inputs, params):
        import os

        os.getenv("HOME")
        return {}


def _info_source(flow_kind: str, *, external: bool = False) -> str:
    external_line = "\n        external=True," if external else ""
    return VALID_NODE_INFO.replace('flow_kind="process",', f'flow_kind="{flow_kind}",{external_line}')


def _legacy_codes(payload: dict[str, object], field: str = "errors") -> set[object]:
    return {
        item["details"].get("legacy_code")
        for item in payload["health"][field]
    }


def test_effect_scope_mapping_preserves_pure_node_abi() -> None:
    positional = NodeInfo("demo.io", "IO", "demo", "Terminal IO.", "1.0.0", "io")

    assert positional.purity == "pure"
    assert effective_effect_scope(positional) == EFFECT_SCOPE_TERMINAL
    assert effective_effect_scope(NodeInfo("demo.document", "Document", "demo", "Document IO.", "1.0.0", "document")) == EFFECT_SCOPE_PYTHON_IO
    assert effective_effect_scope(NodeInfo("demo.process", "Process", "demo", "Trusted process.", "1.0.0", "process", external=True)) == EFFECT_SCOPE_TRUSTED
    assert effective_effect_scope(NodeInfo("demo.external_io", "IO", "demo", "Trusted IO.", "1.0.0", "io", external=True)) == EFFECT_SCOPE_TRUSTED
    assert effective_effect_scope(NodeInfo("demo.external_document", "Document", "demo", "Trusted document.", "1.0.0", "document", external=True)) == EFFECT_SCOPE_TRUSTED
    assert effective_effect_scope(object()) == EFFECT_SCOPE_NONE


@pytest.mark.parametrize(
    "run_body",
    [
        '        import argparse\n        argparse.ArgumentParser().parse_args([])\n        return {"demo.out": 1}',
        '        print("terminal")\n        return {"demo.out": 1}',
        '        open("artifact.txt", "w")\n        return {"demo.out": 1}',
        '        requests.get("https://example.invalid")\n        return {"demo.out": 1}',
        '        sqlite3.connect("artifact.db")\n        return {"demo.out": 1}',
        '        subprocess.run(["echo", "x"])\n        return {"demo.out": 1}',
    ],
)
def test_none_scope_rejects_terminal_file_network_database_and_process(tmp_path, capsys, run_body) -> None:
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source(run_body=run_body))

    assert code == 1
    assert "effect_call" in _legacy_codes(payload)
    assert all(item["rule_id"].startswith("NODE.EFFECT.") for item in payload["health"]["errors"])


@pytest.mark.parametrize(
    "run_body",
    [
        '        import builtins\n        builtins.open("artifact.txt", "w")\n        return {"demo.out": 1}',
        '        import sys\n        value = sys.argv\n        return {"demo.out": len(value)}',
        '        from sys import argv\n        return {"demo.out": len(argv)}',
        '        raise SystemExit(0)',
        '        raise SystemExit',
        '        exit(0)',
        '        quit(0)',
        '        import sys\n        sys.exit(0)',
    ],
)
def test_none_scope_rejects_builtins_open_process_argv_and_system_exit(tmp_path, capsys, run_body) -> None:
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source(run_body=run_body))

    assert code == 1
    assert {"effect_call", "effect_import"} & _legacy_codes(payload)


def test_none_scope_checks_reachable_module_helpers_without_scanning_unrelated_helpers(tmp_path, capsys) -> None:
    helper = """
def _write_file():
    with open("artifact.txt", "w") as handle:
        handle.write("x")
"""
    reachable = _valid_node_source(run_body='        _write_file()\n        return {"demo.out": 1}').replace(
        "class DemoNode:",
        helper + "\n\nclass DemoNode:",
    )
    code, payload = _inspect_node_source(tmp_path / "reachable", capsys, reachable)
    assert code == 1
    assert "effect_call" in _legacy_codes(payload)

    unrelated = _valid_node_source().replace("class DemoNode:", helper + "\n\nclass DemoNode:")
    code, payload = _inspect_node_source(tmp_path / "unrelated", capsys, unrelated)
    assert code == 0
    assert "effect_call" not in _legacy_codes(payload)


@pytest.mark.parametrize(
    "helper_body",
    [
        '    payload["changed"] = True',
        '    del payload["changed"]',
        '    nested = payload["nested"]\n    nested.update({"changed": True})',
    ],
)
def test_python_io_scope_rejects_input_mutation_in_reachable_module_helpers(
    tmp_path,
    capsys,
    helper_body,
) -> None:
    helper = f"""
def _mutate(payload):
{helper_body}
"""
    reachable = _valid_node_source(
        info=_info_source("document"),
        run_body='        _mutate(inputs)\n        return {"demo.out": 1}',
    ).replace("class DemoNode:", helper + "\n\nclass DemoNode:")

    code, payload = _inspect_node_source(tmp_path / "reachable", capsys, reachable)

    assert code == 1
    assert "input_mutation" in _legacy_codes(payload)

    unrelated = _valid_node_source(info=_info_source("document")).replace(
        "class DemoNode:",
        helper + "\n\nclass DemoNode:",
    )
    code, payload = _inspect_node_source(tmp_path / "unrelated", capsys, unrelated)
    assert code == 0
    assert "input_mutation" not in _legacy_codes(payload)


def test_module_helper_input_taint_is_transitive_without_flagging_local_mutation(tmp_path, capsys) -> None:
    transitive_helpers = """
def _inner(value):
    value.clear()

def _outer(payload):
    _inner(payload)
"""
    transitive = _valid_node_source(
        info=_info_source("document"),
        run_body='        _outer(inputs)\n        return {"demo.out": 1}',
    ).replace("class DemoNode:", transitive_helpers + "\n\nclass DemoNode:")

    code, payload = _inspect_node_source(tmp_path / "transitive", capsys, transitive)

    assert code == 1
    assert "input_mutation" in _legacy_codes(payload)

    local_helper = """
def _append_local(values):
    values.append(1)
"""
    local_only = _valid_node_source(
        info=_info_source("document"),
        run_body='        values = []\n        _append_local(values)\n        return {"demo.out": len(values)}',
    ).replace("class DemoNode:", local_helper + "\n\nclass DemoNode:")

    code, payload = _inspect_node_source(tmp_path / "local", capsys, local_only)

    assert code == 0
    assert "input_mutation" not in _legacy_codes(payload)


@pytest.mark.parametrize(
    "run_body",
    [
        '        payload = inputs\n        payload["changed"] = True\n        return {"demo.out": 1}',
        '        payload = inputs\n        del payload["changed"]\n        return {"demo.out": 1}',
        '        payload = inputs.get("nested")\n        payload.update({"changed": True})\n        return {"demo.out": 1}',
    ],
)
def test_python_io_scope_rejects_direct_input_alias_mutation(tmp_path, capsys, run_body) -> None:
    source = _valid_node_source(info=_info_source("document"), run_body=run_body)

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 1
    assert "input_mutation" in _legacy_codes(payload)


def test_io_scope_allows_terminal_streams_and_argparse_but_rejects_other_io(tmp_path, capsys) -> None:
    allowed = _valid_node_source(
        info=_info_source("io"),
        run_body="""
        import argparse
        import json
        import sys
        parser = argparse.ArgumentParser()
        parser.parse_args([])
        parser.parse_intermixed_args([])
        parser.parse_known_intermixed_args([])
        print("terminal")
        sys.stdout.write("terminal")
        return {"demo.out": len(json.dumps({"ok": True}))}
""".rstrip(),
    )
    code, payload = _inspect_node_source(tmp_path / "allowed", capsys, allowed)
    assert code == 0
    assert "effect_call" not in _legacy_codes(payload)
    assert "effect_import" not in _legacy_codes(payload)

    rejected = _valid_node_source(
        info=_info_source("io"),
        run_body='        from pathlib import Path\n        Path("artifact.txt").write_text("x")\n        return {"demo.out": 1}',
    )
    code, payload = _inspect_node_source(tmp_path / "rejected", capsys, rejected)
    assert code == 1
    assert {"effect_call", "effect_import"} <= _legacy_codes(payload)


@pytest.mark.parametrize("flow_kind", ["io", "document"])
def test_effectful_scopes_allow_system_exit_but_reject_process_argv(tmp_path, capsys, flow_kind) -> None:
    allowed = _valid_node_source(
        info=_info_source(flow_kind),
        run_body="""
        import sys
        if False:
            sys.exit(7)
        if False:
            raise SystemExit(8)
        if False:
            exit(9)
        if False:
            quit(10)
        return {"demo.out": 1}
""".rstrip(),
    )
    code, payload = _inspect_node_source(tmp_path / "allowed", capsys, allowed)
    assert code == 0
    assert "effect_call" not in _legacy_codes(payload)

    rejected = _valid_node_source(
        info=_info_source(flow_kind),
        run_body='        import sys\n        value = sys.argv\n        return {"demo.out": len(value)}',
    )
    code, payload = _inspect_node_source(tmp_path / "rejected", capsys, rejected)
    assert code == 1
    assert "effect_call" in _legacy_codes(payload)

    from_import = _valid_node_source(
        info=_info_source(flow_kind),
        run_body='        from sys import argv\n        return {"demo.out": len(argv)}',
    )
    code, payload = _inspect_node_source(tmp_path / "from_import", capsys, from_import)
    assert code == 1
    assert "effect_import" in _legacy_codes(payload)


def test_builtins_open_matches_effect_scope() -> None:
    aliases = {"builtins": "builtins"}
    call = ast.parse('builtins.open("artifact.txt", "w")').body[0].value
    assert isinstance(call, ast.Call)

    assert call_violation(call, aliases=aliases, effect_scope=EFFECT_SCOPE_NONE)[0] == "effect_call"
    assert call_violation(call, aliases=aliases, effect_scope=EFFECT_SCOPE_TERMINAL)[0] == "effect_call"
    assert call_violation(call, aliases=aliases, effect_scope=EFFECT_SCOPE_PYTHON_IO) == ("", "")


@pytest.mark.parametrize("flow_kind", ["io", "document"])
@pytest.mark.parametrize(
    "run_body",
    [
        '        import argparse\n        argparse.FileType("w")("artifact.txt")\n        return {"demo.out": 1}',
        '        import argparse\n        argparse.ArgumentParser().parse_args()\n        return {"demo.out": 1}',
        '        import argparse\n        argparse.ArgumentParser().parse_known_args(args=None)\n        return {"demo.out": 1}',
        '        import argparse\n        argparse.ArgumentParser().parse_intermixed_args()\n        return {"demo.out": 1}',
        '        import argparse\n        argparse.ArgumentParser().parse_known_intermixed_args(args=None)\n        return {"demo.out": 1}',
    ],
)
def test_effectful_scopes_reject_argparse_hidden_file_io_and_global_argv(
    tmp_path,
    capsys,
    flow_kind,
    run_body,
) -> None:
    source = _valid_node_source(info=_info_source(flow_kind), run_body=run_body)

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 1
    assert "effect_call" in _legacy_codes(payload)


@pytest.mark.parametrize(
    "run_body",
    [
        '        import io\n        io.open("artifact.txt", "w")\n        return {"demo.out": 1}',
        '        import http.client\n        http.client.HTTPConnection("example.invalid")\n        return {"demo.out": 1}',
        '        import pty\n        pty.openpty()\n        return {"demo.out": 1}',
    ],
)
def test_io_scope_rejects_non_terminal_stdlib_io(tmp_path, capsys, run_body) -> None:
    source = _valid_node_source(info=_info_source("io"), run_body=run_body)

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 1
    errors = payload["health"]["errors"]
    assert any(item["rule_id"].startswith("NODE.EFFECT.") for item in errors)
    assert {item["details"].get("legacy_code") for item in errors} & {"effect_call", "effect_import"}


@pytest.mark.parametrize("flow_kind", ["io", "document"])
@pytest.mark.parametrize(
    "run_body",
    [
        '        import os\n        os._exit(1)',
        '        import os\n        os.abort()',
        '        import os\n        os.kill(1, 9)',
        '        import os\n        os.killpg(1, 9)',
        '        import signal\n        signal.raise_signal(2)',
    ],
)
def test_non_trusted_scopes_reject_uncatchable_process_termination(tmp_path, capsys, flow_kind, run_body) -> None:
    source = _valid_node_source(info=_info_source(flow_kind), run_body=run_body)

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 1
    assert "effect_call" in _legacy_codes(payload)


@pytest.mark.parametrize("flow_kind", ["document", "data_store"])
def test_python_scope_allows_python_io_but_keeps_dynamic_code_gate(tmp_path, capsys, flow_kind) -> None:
    io_source = _valid_node_source(
        info=_info_source(flow_kind),
        run_body="""
        import argparse
        import pathlib
        import io
        import http.client
        import json
        import pty
        import requests
        import sqlite3
        import subprocess
        import sys
        argparse.ArgumentParser().parse_known_args([])
        argparse.ArgumentParser().parse_known_intermixed_args([])
        pathlib.Path("artifact.txt").write_text(json.dumps({"ok": True}))
        io.open("artifact-io.txt", "w")
        http.client.HTTPConnection("example.invalid")
        pty.openpty()
        requests.get("https://example.invalid")
        sqlite3.connect("artifact.db")
        subprocess.run(["echo", "x"])
        sys.stderr.write("document")
        return {"demo.out": 1}
""".rstrip(),
    )
    code, payload = _inspect_node_source(tmp_path / "io", capsys, io_source)
    assert code == 0
    assert "effect_call" not in _legacy_codes(payload)
    assert "effect_import" not in _legacy_codes(payload)

    dynamic_source = _valid_node_source(
        info=_info_source(flow_kind),
        run_body='        eval("1 + 1")\n        return {"demo.out": 1}',
    )
    code, payload = _inspect_node_source(tmp_path / "dynamic", capsys, dynamic_source)
    assert code == 1
    assert "banned_call" in _legacy_codes(payload)


def test_effectful_and_trusted_examples_validate_without_execution() -> None:
    assert validate_node_class(IoExampleRaisesNode, policy=PurityPolicy(max_source_lines=1000)) == []
    assert validate_node_class(ExternalExampleRaisesNode, policy=PurityPolicy(max_source_lines=1, max_functions=0)) == []

    pure = validate_node_class(PureExampleRaisesNode, policy=PurityPolicy(max_source_lines=1000))
    assert any(item.code == "example_failed" for item in pure)

    gap = validate_node_class(ExternalCoverageGapNode, policy=PurityPolicy(max_source_lines=1000))
    assert any(item.code == "example_contract_gap" for item in gap)
    assert not any(item.code == "example_failed" for item in gap)

    params_gap = validate_node_class(IoExampleParamsGapNode, policy=PurityPolicy(max_source_lines=1000))
    assert any(item.details.get("undeclared_params") == ["undeclared"] for item in params_gap)
    assert not any(item.code == "example_failed" for item in params_gap)


def test_pure_example_system_exit_becomes_example_failed() -> None:
    contract = NodeContract(
        provides=(DataProvider("effect.out", "effect.out"),),
        examples=({"inputs": {}, "params": {}},),
    )

    findings = _validate_examples(
        PureExampleSystemExitNode,
        contract,
        source=_SourceInfo(path="<example>", class_text="", class_start_line=1, module_text=""),
    )

    assert len(findings) == 1
    assert findings[0].code == "example_failed"
    assert "SystemExit" in findings[0].message


def test_base_lib_none_scope_rejects_builtins_open_process_argv_and_system_exit(tmp_path) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "unsafe.py").write_text(
        """
import builtins
import sys

def unsafe():
    builtins.open("artifact.txt", "w")
    value = sys.argv
    raise SystemExit(len(value))
""".strip(),
        encoding="utf-8",
    )

    report = scan_base_lib(tmp_path, policy=PurityPolicy(max_source_lines=1000))
    messages = "\n".join(finding.message for finding in report.findings)

    assert "builtins.open" in messages
    assert "sys.argv" in messages
    assert "SystemExit" in messages
    assert {finding.rule_id for finding in report.findings} == {"BASE_LIB.SIDE_EFFECT_CALL"}


def test_python_scope_keeps_structural_rules_and_policy_cannot_elevate_none() -> None:
    document = validate_node_class(DocumentGlobalMutationNode, policy=PurityPolicy(max_source_lines=1000))
    assert any(item.code == "global_state" for item in document)

    escaped = validate_node_class(
        PolicyCannotElevateNode,
        policy=PurityPolicy(max_source_lines=1000, allowed_import_roots=("os",)),
    )
    assert {item.code for item in escaped} >= {"effect_import", "effect_call"}


def test_effect_findings_cannot_be_exempted_or_downgraded() -> None:
    finding = HealthFinding(
        rule_id="NODE.EFFECT.CALL_FORBIDDEN",
        severity="error",
        object_type="node",
        object_id="unsafe",
        failure_layer="implementation",
        message="effect scope violation",
        suggested_fix_type="fix_node",
    )
    policy = EffectivePolicy(
        {
            "rules": {
                "exemptions": [{"rule_id": finding.rule_id, "scope": {}, "reason": "attempted exemption"}],
                "downgrades": [{"rule_id": finding.rule_id, "scope": {}, "to": "warning", "reason": "attempted downgrade"}],
            }
        },
        ("test",),
    )

    errors, warnings, skipped = apply_policy_to_findings((finding,), (), policy)

    assert errors == (finding,)
    assert warnings == ()
    assert skipped == ()


@pytest.mark.parametrize(
    "rule_id",
    [
        "BASE_LIB.BANNED_IMPORT",
        "BASE_LIB.FORBIDDEN_PROJECT_IMPORT",
        "BASE_LIB.GLOBAL_STATE",
        "BASE_LIB.SIDE_EFFECT_CALL",
        "BASE_LIB.TOP_LEVEL_SIDE_EFFECT",
        "NODE.BASE_LIB.INDIRECT_VIOLATION",
    ],
)
def test_base_lib_effect_and_indirect_findings_cannot_be_exempted_or_downgraded(rule_id) -> None:
    finding = HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type="base_lib" if rule_id.startswith("BASE_LIB.") else "node",
        object_id="base_lib.unsafe",
        failure_layer="base_lib",
        message="base_lib must not hide effects",
        suggested_fix_type="fix_base_lib",
    )
    override_sets = (
        {
            "exemptions": [{"rule_id": rule_id, "scope": {}, "reason": "attempted exemption"}],
            "downgrades": [],
        },
        {
            "exemptions": [],
            "downgrades": [{"rule_id": rule_id, "scope": {}, "to": "warning", "reason": "attempted downgrade"}],
        },
    )

    for rules in override_sets:
        policy = EffectivePolicy({"rules": rules}, ("test",))
        errors, warnings, skipped = apply_policy_to_findings((finding,), (), policy)

        assert errors == (finding,)
        assert warnings == ()
        assert skipped == ()


def test_health_inspect_and_architecture_show_derived_effect_scope(tmp_path, capsys) -> None:
    class TrustedRuntimePlugin:
        pass

    registry = _registry()
    plugins = PluginRegistry()
    plugins.register(TrustedRuntimePlugin(), plugin_type="runtime", name="trusted-runtime")
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the IO fixture."),
                    _node_call("read", "test.value_input", "Reads terminal input.", requires=[REQ_SPEC("value.in")]),
                    _node_call("end", "test.in_end", "Ends the IO fixture.", requires=[REQ_SPEC("value.in")]),
                ],
                "edges": _edge_chain("start", "read", "end"),
            }
        }
    )

    health = validate_graph_health(
        graph,
        registry=registry,
        plugin_registry=plugins,
        purity_policy=PurityPolicy(max_source_lines=1000),
    )
    assert health.info["node_effect_scopes"] == {
        "start": EFFECT_SCOPE_NONE,
        "read": EFFECT_SCOPE_TERMINAL,
        "end": EFFECT_SCOPE_NONE,
    }
    assert health.info["plugins"]["plugins"][0]["effect_scope"] == EFFECT_SCOPE_TRUSTED

    architecture = build_architecture_document(
        graph,
        registry=registry,
        resources={
            "plugins": [
                {
                    "id": "trusted-runtime",
                    "name": "trusted-runtime",
                    "type": "runtime",
                    "status": "implemented",
                }
            ]
        },
    )
    nodes = {node["id"]: node for node in architecture["workflow"]["nodes"]}
    assert nodes["read"]["effect_scope"] == EFFECT_SCOPE_TERMINAL
    assert architecture["node_types"]["test.value_input"]["info"]["effect_scope"] == EFFECT_SCOPE_TERMINAL
    assert architecture["resources"]["plugins"][0]["effect_scope"] == EFFECT_SCOPE_TRUSTED

    code, payload = _inspect_node_source(
        tmp_path,
        capsys,
        _valid_node_source(info=_info_source("io")),
    )
    assert code == 0
    assert payload["node"]["metadata"]["effect_scope"] == EFFECT_SCOPE_TERMINAL
    assert payload["node"]["metadata"]["purity"] == "pure"


def test_planned_flow_kind_never_elevates_architecture_scope() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call(
                        "future_document",
                        "test.effect_request",
                        "Represents future document IO.",
                        status="planned",
                        flow_kind="document",
                    )
                ]
            }
        }
    )

    architecture = build_architecture_document(graph, registry=_registry())
    assert architecture["workflow"]["nodes"][0]["effect_scope"] == EFFECT_SCOPE_NONE
    assert architecture["node_types"]["test.effect_request"]["info"]["effect_scope"] == EFFECT_SCOPE_NONE
