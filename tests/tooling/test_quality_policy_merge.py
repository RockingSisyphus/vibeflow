"""The two targets consume one policy merge and schema contract."""

from __future__ import annotations

from pathlib import Path

from vibeflow.tooling.project.quality_policy import resolve_shared_quality_policy


def test_shared_policy_precedence_and_nullable_complexity_defaults(tmp_path: Path) -> None:
    config = tmp_path / "workflow.jsonc"
    config.write_text("{}", encoding="utf-8")
    (tmp_path / "kernel_policy.jsonc").write_text(
        '{"node_source":{"max_lines":400},"complexity":{"max_params":2}}',
        encoding="utf-8",
    )
    explicit = tmp_path / "explicit.jsonc"
    explicit.write_text(
        '{"node_source":{"max_lines":350},"complexity":{"max_params":3}}',
        encoding="utf-8",
    )
    data, sources, findings = resolve_shared_quality_policy(
        {"policy": {"node_source": {"max_lines":300}}},
        config_path=config,
        explicit_policy_path=explicit,
    )
    assert not findings
    assert data["node_source"]["max_lines"] == 300
    assert data["complexity"]["max_params"] == 3
    assert data["complexity"]["max_functions"] is None
    assert sources == (
        "kernel.default_policy",
        f"project.policy:{tmp_path / 'kernel_policy.jsonc'}",
        f"project.policy:{explicit}",
        "config.inline_policy",
    )


def test_invalid_policy_field_is_reported_without_overriding_valid_layer(tmp_path: Path) -> None:
    config = tmp_path / "workflow.jsonc"
    config.write_text("{}", encoding="utf-8")
    explicit = tmp_path / "invalid.jsonc"
    explicit.write_text('{"complexity":{"max_params":0}}', encoding="utf-8")
    data, sources, findings = resolve_shared_quality_policy(
        {}, config_path=config, explicit_policy_path=explicit,
    )
    assert data["complexity"]["max_params"] is None
    assert sources == ("kernel.default_policy",)
    assert [item.rule_id for item in findings] == ["CONFIG.SCHEMA.POLICY_POSITIVE_INT"]
