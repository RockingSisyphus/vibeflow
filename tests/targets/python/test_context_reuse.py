"""Formal CLI identity checks across different registered Node types."""

from sandbox.python.context_reuse.cli_probe import observe


def test_formal_cli_reuses_source_facts_across_node_and_rule_subjects(tmp_path):
    result = observe(tmp_path)
    assert result["matched"], result
