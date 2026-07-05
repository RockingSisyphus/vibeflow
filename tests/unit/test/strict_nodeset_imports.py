from tests.unit.strict_support import *


def test_nodeset_imports_expand_for_validate_inspect_mermaid_and_run(tmp_path, capsys) -> None:
    imports_path = tmp_path / "nodesets.jsonc"
    imports_path.write_text(
        json.dumps(
            {
                "nodesets": [
                    _nodeset_config(
                        "math.add_one",
                        requires=["value.in"],
                        provides=["value.out"],
                        exports=["value.out"],
                        pipeline=_input_add_pipeline(),
                    ),
                    _nodeset_config(
                        "math.seed",
                        provides=["value.in"],
                        exports=["value.in"],
                        pipeline=_seed_only_pipeline(seed={"value": 4}),
                    ),
                ]
            }
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        json.dumps(
            {
                "nodeset_imports": [{"path": "nodesets.jsonc", "names": ["math.add_one"]}],
                "pipeline": {
                    "nodes": [
                        _node_call("start", "test.start", "Starts the imported nodeset fixture."),
                        _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")], value=4),
                        _node_call("flow", "nodeset.math.add_one", "Calls imported add-one nodeset.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                        _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                    ],
                    "edges": _edge_chain("start", "seed", "flow", "end"),
                    "outputs": [REQ_SPEC("value.out")],
                },
            }
        ),
        encoding="utf-8",
    )

    assert cli_main(["validate", "--config", str(config_path), "--json"]) == 0
    validate_payload = json.loads(capsys.readouterr().out)
    assert validate_payload["info"]["nodesets"] == ["math.add_one"]
    assert validate_payload["info"]["nodeset_imports"][0]["names"] == ["math.add_one"]

    assert cli_main(["inspect-config", "--config", str(config_path)]) == 0
    inspect_payload = json.loads(capsys.readouterr().out)
    assert inspect_payload["config"]["nodeset_imports"][0]["requested_names"] == ["math.add_one"]

    assert cli_main(["export-mermaid", "--config", str(config_path), "--expand-nodesets"]) == 0
    assert "flow__add" in capsys.readouterr().out

    result = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="nodeset-import")
    assert result.context.get("value.out")["value"] == 5
    health = json.loads((result.run_dir / "health_report.json").read_text(encoding="utf-8"))
    assert health["info"]["nodeset_imports"][0]["path"] == str(imports_path.resolve())


def test_nodeset_imports_reject_missing_duplicate_and_empty_sources(tmp_path) -> None:
    empty_path = tmp_path / "empty.jsonc"
    empty_path.write_text('{"nodesets": []}', encoding="utf-8")
    with pytest.raises(ConfigLoadError) as empty_error:
        load_config_document(tmp_path / "missing-parent.jsonc")
    assert empty_error.value.rule_id == "CONFIG.READ"

    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text('{"nodeset_imports": ["empty.jsonc"], "pipeline": {"nodes": [{"name": "seed", "type": "test.seed"}]}}', encoding="utf-8")
    with pytest.raises(ConfigLoadError) as empty_import:
        load_config_document(config_path)
    assert empty_import.value.rule_id == "CONFIG.NODESET_IMPORT.EMPTY"

    imports_path = tmp_path / "nodesets.jsonc"
    imports_path.write_text(json.dumps({"nodesets": [_nodeset_config("dup.flow", pipeline={"nodes": [{"name": "seed", "type": "test.seed"}]})]}), encoding="utf-8")
    config_path.write_text(
        json.dumps(
            {
                "nodeset_imports": ["nodesets.jsonc"],
                "nodesets": [_nodeset_config("dup.flow", pipeline={"nodes": [{"name": "seed", "type": "test.seed"}]})],
                "pipeline": {"nodes": [{"name": "flow", "type": "nodeset.dup.flow"}]},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigLoadError) as duplicate:
        load_config_document(config_path)
    assert duplicate.value.rule_id == "CONFIG.NODESET_IMPORT.DUPLICATE"


def test_nodeset_imports_cache_reused_documents_within_one_load(tmp_path, monkeypatch) -> None:
    imports_path = tmp_path / "nodesets.jsonc"
    imports_path.write_text(
        json.dumps(
            {
                "nodesets": [
                    _nodeset_config("math.add_one", pipeline=_input_add_pipeline(), requires=["value.in"], provides=["value.out"], exports=["value.out"]),
                    _nodeset_config("math.seed", pipeline=_seed_only_pipeline(), provides=["value.in"], exports=["value.in"]),
                ]
            }
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        json.dumps(
            {
                "nodeset_imports": [
                    {"path": "nodesets.jsonc", "names": ["math.add_one"]},
                    {"path": "nodesets.jsonc", "names": ["math.seed"]},
                ],
                "pipeline": {"nodes": [_node_call("flow", "nodeset.math.add_one", "Calls imported flow.", provides=[PROV_SPEC("value.out")])]},
            }
        ),
        encoding="utf-8",
    )
    original_read_text = Path.read_text
    reads: list[Path] = []

    def counting_read_text(self: Path, *args, **kwargs):
        if self.resolve() == imports_path.resolve():
            reads.append(self)
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    document = load_config_document(config_path)

    assert reads == [imports_path]
    assert [item["name"] for item in document.data["nodesets"]] == ["math.add_one", "math.seed"]
