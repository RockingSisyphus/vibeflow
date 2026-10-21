"""The public quality command owns source selection and Rule configuration."""
import json

import pytest

from tests.fixtures.support.projects import register_root
from vibeflow.tooling.application.cli import main


@pytest.mark.parametrize("rules,expected", [
    (None, True),
    ({"rulesets":[]}, False),
    ({"rulesets":[{"rule_id":"vibeflow.root.files", "params":{"max_function_params":10}}]}, False),
    ({"rulesets":[{"rule_id":"vibeflow.root.files", "params":{"max_function_params":2}}]}, True),
])
def test_quality_command_uses_default_replacement_and_empty_root_rules(tmp_path, capsys, rules, expected):
    root = tmp_path / "app"
    register_root(root)
    (root / "root_rules.jsonc").unlink()
    (root / "ordinary.py").write_text("def wide(a,b,c,d,e,f,g):\n    return a\n")
    if rules is not None:
        (root / "root_rules.jsonc").write_text(json.dumps(rules))
    assert main(["quality-check", "--path", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(row["rule_id"] == "QUALITY.FUNCTION.TOO_MANY_PARAMS" for row in payload["warnings"]) == expected


@pytest.mark.parametrize("flag", ["--check-side-effects", "--max-function-params"])
def test_removed_quality_flags_are_rejected_without_test_translation(tmp_path, capsys, flag):
    with pytest.raises(SystemExit) as error:
        main(["quality-check", "--path", str(tmp_path), flag, *(["2"] if flag.endswith("params") else [])])
    assert error.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err
