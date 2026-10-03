"""Graph failures retain resource identity without introducing Core file I/O."""

import pytest

from vibeflow.core.descriptors.catalogs import RulesetCatalog
from vibeflow.core.rules import RuleCall, RuleDescriptor, RuleGraphError, RulesetDescriptor, compile_ruleset, rule_graph_error_finding


def test_graph_error_maps_loaded_catalog_origin_to_formal_finding(tmp_path):
    resource = tmp_path / "not-opened.jsonc"
    descriptor = RulesetDescriptor("recursive", (RuleCall("child", ruleset_id="recursive"),))
    catalog = RulesetCatalog()
    catalog.register(descriptor, source=str(resource))
    with pytest.raises(RuleGraphError) as raised:
        compile_ruleset("recursive", rules={"leaf": RuleDescriptor("leaf")}, rulesets=catalog)
    error = raised.value
    assert error.details == {"ruleset_id": "recursive", "entrypoint": "static"}
    finding = rule_graph_error_finding(error, rulesets=catalog, object_type="node", object_id="calculate")
    assert finding.code == "RULE.INCLUDES.CYCLE"
    assert finding.source_location == {"path": str(resource)}
    assert finding.rule_source == "ruleset:recursive"
    assert not resource.exists()
