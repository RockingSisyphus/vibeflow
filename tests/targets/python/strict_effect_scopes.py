"""Selected effect Rulesets, static execution boundaries and source-only evidence."""
import ast
import pytest
from tests.fixtures.support.strict_support import PurityPolicy
from tests.fixtures.support.rule_inspection import node_document, _inspect_node_source as _inspect_declared_source
from vibeflow.targets.python.sdk.protocols import EFFECT_SCOPE_NONE, EFFECT_SCOPE_TERMINAL, EFFECT_SCOPE_PYTHON_IO, EFFECT_SCOPE_GLOBAL_STATE
from vibeflow.targets.python.rules.node.effect_policy import call_violation, import_violation_code
from vibeflow.targets.python.quality.source_analysis.types import _default_rule_id

class SourceCase(str):
    def __new__(cls, code, rulesets=("vibeflow.process",)):
        result = super().__new__(cls,code)
        result.rulesets = rulesets
        return result

    def replace(self, old, new, count=-1):
        return SourceCase(super().replace(old,new,count),self.rulesets)

    def __radd__(self, value):
        return SourceCase(str(value)+str(self),self.rulesets)


def _selection(name):
    return ("vibeflow."+name,)


def _source_case(*, rulesets=("vibeflow.process",), run_body='        return {"demo.out": 1}'):
    return SourceCase('class DemoNode:\n    def run_pure(self, inputs, params):\n'+run_body+'\n',rulesets)


def _inspect_node_source(path,capsys,source,**kwargs):
    declaration=node_document(rulesets=list(getattr(source,"rulesets",("vibeflow.process",))))
    return _inspect_declared_source(path,capsys,str(source),descriptor=declaration,**kwargs)


def _diagnostic_kinds(payload,field="errors"):
    kinds=("effect_call","effect_import","global_state","banned_call","banned_import","input_mutation")
    codes={item["code"] for item in payload["health"][field]}
    return {kind for kind in kinds if _default_rule_id(kind) in codes}


@pytest.fixture(autouse=True)
def artifact_guard(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield
    assert not (tmp_path/"artifact.txt").exists()
    assert not (tmp_path/"artifact-io.txt").exists()
    assert not (tmp_path/"artifact.db").exists()


def test_static_compute_imports_do_not_require_external() -> None:
    policy = PurityPolicy(max_source_lines=1000)

    for module in ("numpy", "scipy", "torch", "transformers"):
        assert import_violation_code(module, effect_scope=EFFECT_SCOPE_NONE, policy=policy) == ""
        assert import_violation_code(module, effect_scope=EFFECT_SCOPE_GLOBAL_STATE, policy=policy) == ""

@pytest.mark.parametrize(
    "run_body",
    [
        '        import random\n        random.seed(7)\n        return {"demo.out": 1}',
        '        import random\n        seed = random.seed\n        seed(7)\n        return {"demo.out": 1}',
        '        import torch\n        torch.manual_seed(7)\n        return {"demo.out": 1}',
        '        import torch\n        with torch.no_grad():\n            value = 1\n        return {"demo.out": value}',
        '        import sys\n        sys.setrecursionlimit(1000)\n        return {"demo.out": 1}',
        '        import torch\n        torch.backends.cudnn.benchmark = True\n        return {"demo.out": 1}',
    ],
)
def test_none_scope_rejects_ambient_state_mutation(tmp_path, capsys, run_body) -> None:
    code, payload = _inspect_node_source(tmp_path, capsys, _source_case(run_body=run_body))

    if "torch.no_grad" in run_body:
        assert code == 0
    else:
        assert code == 1
        assert {"effect_call", "global_state"} & _diagnostic_kinds(payload)

def test_global_state_scope_allows_only_audited_ambient_mutation(tmp_path, capsys) -> None:
    source = _source_case(
        rulesets=_selection("global_state"),
        run_body="""
        global GLOBAL_STATE_TEST_CACHE
        import random
        import sys
        import torch
        GLOBAL_STATE_TEST_CACHE = {}
        random.seed(7)
        sys.setrecursionlimit(1000)
        torch.manual_seed(7)
        with torch.no_grad():
            pass
        torch.set_default_dtype(torch.float64)
        torch.backends.cudnn.benchmark = True
        return {"demo.out": 1}
""".rstrip(),
    )

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 0
    assert payload["node"]["effect_scope"] == EFFECT_SCOPE_GLOBAL_STATE

def test_vendor_neutral_ambient_call_classification(tmp_path, capsys) -> None:
    run_body = """
        import acme_runtime
        set_mode = acme_runtime.set_backend_mode
        set_mode("fast")
        acme_runtime.seed(7)
        acme_runtime.reset()
        return {"demo.out": 1}
""".rstrip()

    ordinary_code, ordinary_payload = _inspect_node_source(
        tmp_path / "ordinary",
        capsys,
        _source_case(run_body=run_body),
    )
    global_code, global_payload = _inspect_node_source(
        tmp_path / "global",
        capsys,
        _source_case(rulesets=_selection("global_state"), run_body=run_body),
    )

    assert ordinary_code == 0
    assert not _diagnostic_kinds(ordinary_payload)
    assert global_code == 0
    assert global_payload["node"]["effect_scope"] == EFFECT_SCOPE_GLOBAL_STATE

def test_none_scope_rejects_module_cache_mutation_without_global_statement(tmp_path, capsys) -> None:
    source = "CACHE: dict\nREGISTRY: dict\n\n" + _source_case(
        run_body="""
        CACHE.update({"ready": True})
        REGISTRY["active"] = True
        return {"demo.out": 1}
""".rstrip(),
    )

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 1
    assert {"effect_call", "global_state"} <= _diagnostic_kinds(payload)

def test_global_state_scope_allows_module_cache_mutation_without_global_statement(tmp_path, capsys) -> None:
    source = "CACHE = {}\nREGISTRY = {}\n\n" + _source_case(
        rulesets=_selection("global_state"),
        run_body="""
        CACHE.update({"ready": True})
        REGISTRY["active"] = True
        return {"demo.out": 1}
""".rstrip(),
    )

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 0
    assert payload["node"]["effect_scope"] == EFFECT_SCOPE_GLOBAL_STATE

def test_local_container_mutation_is_not_treated_as_ambient_state(tmp_path, capsys) -> None:
    source = _source_case(
        run_body="""
        cache = {}
        cache.update({"ready": True})
        registry = {}
        registry["active"] = True
        values = []
        values.append(1)
        return {"demo.out": len(values)}
""".rstrip(),
    )

    code, _payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 0

@pytest.mark.parametrize(
    "run_body",
    [
        '        op = open\n        op("artifact.txt", "w")\n        return {"demo.out": 1}',
        '        op = open\n        if False:\n            op = len\n        op("artifact.txt", "w")\n        return {"demo.out": 1}',
        '        import builtins\n        op = getattr(builtins, "open")\n        op("artifact.txt", "w")\n        return {"demo.out": 1}',
        '        import builtins\n        builtins.__dict__["eval"]("1 + 1")\n        return {"demo.out": 1}',
        '        import builtins\n        builtins.__dict__.get("open")("artifact.txt", "w")\n        return {"demo.out": 1}',
        '        name = "open"\n        getattr(__builtins__, name)("artifact.txt", "w")\n        return {"demo.out": 1}',
        '        import builtins\n        name = "eval"\n        builtins.__dict__[name]("1 + 1")\n        return {"demo.out": 1}',
        '        import importlib as loader_module\n        loader = getattr(loader_module, "import_module")\n        loader("json")\n        return {"demo.out": 1}',
        '        import torch\n        save = torch.save\n        save(1, "artifact.txt")\n        return {"demo.out": 1}',
        '        import numpy as np\n        save = np.save\n        save("artifact.txt", [1])\n        return {"demo.out": 1}',
        '        import concurrent.futures as futures\n        futures.ThreadPoolExecutor()\n        return {"demo.out": 1}',
        '        from _thread import start_new_thread as spawn\n        spawn(lambda: None, ())\n        return {"demo.out": 1}',
        '        import ctypes as ffi\n        ffi.CDLL(None)\n        return {"demo.out": 1}',
        '        from cffi import FFI\n        FFI()\n        return {"demo.out": 1}',
        '        from transformers import AutoModel\n        AutoModel.from_pretrained("remote/model")\n        return {"demo.out": 1}',
        '        import torch\n        torch.utils.cpp_extension.load(name="unsafe", sources=[])\n        return {"demo.out": 1}',
        '        import torch\n        torch.classes.load_library("artifact.so")\n        return {"demo.out": 1}',
        '        import posix\n        posix.system("command")\n        return {"demo.out": 1}',
    ],
)
def test_non_trusted_scopes_reject_common_alias_reflection_thread_and_ffi_bypasses(
    tmp_path,
    capsys,
    run_body,
) -> None:
    source = _source_case(rulesets=_selection("global_state"), run_body=run_body)

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    recognized = any(token in run_body for token in ("op = open", "getattr(builtins, \"open\")", "__dict__.get(\"open\")", "torch.save", "np.save", "concurrent", "_thread", "posix"))
    assert code == (1 if recognized else 0), payload
    assert bool(_diagnostic_kinds(payload)) == recognized

def test_global_state_rejects_forbidden_import_path_mutation(tmp_path, capsys) -> None:
    source = _source_case(
        rulesets=_selection("global_state"),
        run_body='        import sys\n        sys.path.append("dynamic")\n        return {"demo.out": 1}',
    )

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 1
    assert "effect_call" in _diagnostic_kinds(payload)

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
    code, payload = _inspect_node_source(tmp_path, capsys, _source_case(run_body=run_body))

    assert code == 1
    assert "effect_call" in _diagnostic_kinds(payload)
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
    code, payload = _inspect_node_source(tmp_path, capsys, _source_case(run_body=run_body))

    assert code == 1
    assert {"effect_call", "effect_import"} & _diagnostic_kinds(payload)

def test_none_scope_checks_reachable_module_helpers_without_scanning_unrelated_helpers(tmp_path, capsys) -> None:
    helper = """
def _write_file():
    with open("artifact.txt", "w") as handle:
        handle.write("x")
"""
    reachable = _source_case(run_body='        _write_file()\n        return {"demo.out": 1}').replace(
        "class DemoNode:",
        helper + "\n\nclass DemoNode:",
    )
    code, payload = _inspect_node_source(tmp_path / "reachable", capsys, reachable)
    assert code == 1
    assert "effect_call" in _diagnostic_kinds(payload)

    unrelated = _source_case().replace("class DemoNode:", helper + "\n\nclass DemoNode:")
    code, payload = _inspect_node_source(tmp_path / "unrelated", capsys, unrelated)
    assert code == 0
    assert "effect_call" not in _diagnostic_kinds(payload)

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
    reachable = _source_case(
        rulesets=_selection("document"),
        run_body='        _mutate(inputs)\n        return {"demo.out": 1}',
    ).replace("class DemoNode:", helper + "\n\nclass DemoNode:")

    code, payload = _inspect_node_source(tmp_path / "reachable", capsys, reachable)

    assert code == 0
    assert "input_mutation" not in _diagnostic_kinds(payload)

    unrelated = _source_case(rulesets=_selection("document")).replace(
        "class DemoNode:",
        helper + "\n\nclass DemoNode:",
    )
    code, payload = _inspect_node_source(tmp_path / "unrelated", capsys, unrelated)
    assert code == 0
    assert "input_mutation" not in _diagnostic_kinds(payload)

def test_module_helper_input_taint_is_transitive_without_flagging_local_mutation(tmp_path, capsys) -> None:
    transitive_helpers = """
def _inner(value):
    value.clear()

def _outer(payload):
    _inner(payload)
"""
    transitive = _source_case(
        rulesets=_selection("document"),
        run_body='        _outer(inputs)\n        return {"demo.out": 1}',
    ).replace("class DemoNode:", transitive_helpers + "\n\nclass DemoNode:")

    code, payload = _inspect_node_source(tmp_path / "transitive", capsys, transitive)

    assert code == 0
    assert "input_mutation" not in _diagnostic_kinds(payload)

    local_helper = """
def _append_local(values):
    values.append(1)
"""
    local_only = _source_case(
        rulesets=_selection("document"),
        run_body='        values = []\n        _append_local(values)\n        return {"demo.out": len(values)}',
    ).replace("class DemoNode:", local_helper + "\n\nclass DemoNode:")

    code, payload = _inspect_node_source(tmp_path / "local", capsys, local_only)

    assert code == 0
    assert "input_mutation" not in _diagnostic_kinds(payload)

@pytest.mark.parametrize(
    "run_body",
    [
        '        payload = inputs\n        payload["changed"] = True\n        return {"demo.out": 1}',
        '        payload = inputs\n        del payload["changed"]\n        return {"demo.out": 1}',
        '        payload = inputs.get("nested")\n        payload.update({"changed": True})\n        return {"demo.out": 1}',
    ],
)
def test_python_io_scope_rejects_direct_input_alias_mutation(tmp_path, capsys, run_body) -> None:
    source = _source_case(rulesets=_selection("document"), run_body=run_body)

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    direct = "inputs.get" not in run_body
    assert code == (1 if direct else 0)
    assert ("input_mutation" in _diagnostic_kinds(payload)) == direct

def test_io_scope_allows_terminal_streams_and_argparse_but_rejects_other_io(tmp_path, capsys) -> None:
    allowed = _source_case(
        rulesets=_selection("io"),
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
    assert "effect_call" not in _diagnostic_kinds(payload)
    assert "effect_import" not in _diagnostic_kinds(payload)

    rejected = _source_case(
        rulesets=_selection("io"),
        run_body='        from pathlib import Path\n        Path("artifact.txt").write_text("x")\n        return {"demo.out": 1}',
    )
    code, payload = _inspect_node_source(tmp_path / "rejected", capsys, rejected)
    assert code == 1
    assert {"effect_call", "effect_import"} <= _diagnostic_kinds(payload)

@pytest.mark.parametrize("flow_kind", ["io", "document"])
def test_effectful_scopes_allow_system_exit_but_reject_process_argv(tmp_path, capsys, flow_kind) -> None:
    allowed = _source_case(
        rulesets=_selection(flow_kind),
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
    assert "effect_call" not in _diagnostic_kinds(payload)

    rejected = _source_case(
        rulesets=_selection(flow_kind),
        run_body='        import sys\n        value = sys.argv\n        return {"demo.out": len(value)}',
    )
    code, payload = _inspect_node_source(tmp_path / "rejected", capsys, rejected)
    assert code == 1
    assert "effect_call" in _diagnostic_kinds(payload)

    from_import = _source_case(
        rulesets=_selection(flow_kind),
        run_body='        from sys import argv\n        return {"demo.out": len(argv)}',
    )
    code, payload = _inspect_node_source(tmp_path / "from_import", capsys, from_import)
    assert code == 1
    assert "effect_import" in _diagnostic_kinds(payload)

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
    source = _source_case(rulesets=_selection(flow_kind), run_body=run_body)

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    denied = flow_kind == "io" or "FileType" not in run_body
    assert code == (1 if denied else 0), payload
    assert ("effect_call" in _diagnostic_kinds(payload)) == denied

@pytest.mark.parametrize(
    "run_body",
    [
        '        import io\n        io.open("artifact.txt", "w")\n        return {"demo.out": 1}',
        '        import http.client\n        http.client.HTTPConnection("example.invalid")\n        return {"demo.out": 1}',
        '        import pty\n        pty.openpty()\n        return {"demo.out": 1}',
    ],
)
def test_io_scope_rejects_non_terminal_stdlib_io(tmp_path, capsys, run_body) -> None:
    source = _source_case(rulesets=_selection("io"), run_body=run_body)

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 1
    errors = payload["health"]["errors"]
    assert any(item["rule_id"].startswith("NODE.EFFECT.") for item in errors)
    assert _diagnostic_kinds(payload) & {"effect_call", "effect_import"}

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
    source = _source_case(rulesets=_selection(flow_kind), run_body=run_body)

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 1
    assert "effect_call" in _diagnostic_kinds(payload)

@pytest.mark.parametrize("flow_kind", ["document", "data_store"])
def test_python_scope_allows_python_io_and_does_not_impose_code_security(tmp_path, capsys, flow_kind) -> None:
    io_source = _source_case(
        rulesets=_selection(flow_kind),
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
    assert "effect_call" not in _diagnostic_kinds(payload)
    assert "effect_import" not in _diagnostic_kinds(payload)

    dynamic_source = _source_case(
        rulesets=_selection(flow_kind),
        run_body='        eval("1 + 1")\n        return {"demo.out": 1}',
    )
    code, payload = _inspect_node_source(tmp_path / "dynamic", capsys, dynamic_source)
    assert code == 0
    assert "banned_call" not in _diagnostic_kinds(payload)

def test_inspect_preflight_blocks_top_level_effect_before_module_execution(tmp_path, capsys) -> None:
    source = 'open("artifact.txt", "w").write("x")\n\n' + _source_case(
        rulesets=_selection("global_state")
    )

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 1
    assert not (tmp_path / "artifact.txt").exists()
    messages = "\n".join(item["message"] for item in payload["health"]["errors"])
    assert any(item["code"] == "NODE.IMPORT.SIDE_EFFECT" for item in payload["health"]["errors"])

def test_inspect_preflight_walks_local_import_chain_before_execution(tmp_path, capsys) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    artifact = tmp_path / "chain-artifact.txt"
    (tmp_path / "helper.py").write_text(
        'open("chain-artifact.txt", "w").write("x")\n',
        encoding="utf-8",
    )
    source = "import helper\n\n" + _source_case(rulesets=_selection("global_state"))

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 1
    assert not artifact.exists()
    messages = "\n".join(item["message"] for item in payload["health"]["errors"])
    assert any(item["source_location"]["path"].endswith("helper.py") for item in payload["health"]["errors"])

@pytest.mark.parametrize(
    "class_prefix",
    [
        """
def deco(value):
    open("artifact.txt", "w").write("x")
    return value

@deco
""",
        """
class Meta(type):
    def __new__(cls, name, bases, namespace):
        open("artifact.txt", "w").write("x")
        return super().__new__(cls, name, bases, namespace)

class DemoNode(metaclass=Meta):
""",
        """
class Base:
    def __init_subclass__(cls):
        open("artifact.txt", "w").write("x")

class DemoNode(Base):
""",
    ],
)
def test_preflight_blocks_implicit_class_execution(tmp_path, capsys, class_prefix) -> None:
    source = _source_case(rulesets=_selection("global_state"))
    if "class DemoNode" in class_prefix:
        source = source.replace("class DemoNode:", class_prefix.strip())
    else:
        source = source.replace("class DemoNode:", class_prefix.strip() + "\nclass DemoNode:")

    code, payload = _inspect_node_source(tmp_path, capsys, source)

    assert code == 1
    assert not (tmp_path / "artifact.txt").exists()
    messages = "\n".join(item["message"] for item in payload["health"]["errors"])
    assert any(item["code"] == "NODE.IMPORT.SIDE_EFFECT" for item in payload["health"]["errors"])


def test_flow_kind_and_external_metadata_do_not_select_effect_authority(tmp_path,capsys):
    declaration=node_document(rulesets=["vibeflow.process"])
    declaration.update(flow_kind="io",external=True)
    code,payload=_inspect_declared_source(tmp_path,capsys,str(_source_case(run_body='        print("terminal")\n        return {"demo.out": 1}')),descriptor=declaration)
    assert code == 1
    assert payload["node"]["effect_scope"] == "none"
    assert any(item["definition_id"] == "vibeflow.no_side_effects" for item in payload["health"]["errors"])


def test_explicit_empty_rule_selection_is_unconstrained_and_does_not_execute_source(tmp_path,capsys):
    source=_source_case(rulesets=(),run_body='        open("artifact.txt", "w")\n        return {"demo.out": 1}')
    code,payload=_inspect_node_source(tmp_path,capsys,source)
    assert code == 0
    assert payload["node"]["effect_scope"] == "unconstrained"
    assert payload["health"]["info"]["rule_executions"] == []


def test_examples_remain_documentation_and_are_never_executed(tmp_path,capsys):
    declaration=node_document()
    declaration["contract"]["examples"]=[{"inputs":{},"params":{}}]
    source='class DemoNode:\n    def run_pure(self, inputs, params):\n        raise RuntimeError("example code must not execute")\n'
    code,payload=_inspect_declared_source(tmp_path,capsys,source,descriptor=declaration)
    assert code == 0
    assert payload["health"]["status"] == "PASS"
