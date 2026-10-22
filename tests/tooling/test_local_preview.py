"""Snapshot history, target adapters and real offline browser interactions."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from vibeflow.tooling.presentation.preview.catalog import new_record, reindex
from vibeflow.tooling.presentation.viewer import install_page
from vibeflow.tooling.project.preview_options import validate_preview_options
from vibeflow.tooling.project.architecture_types import WorkspaceConfigError


def test_installer_discovers_entry_asset_references_and_preserves_configuration(tmp_path,monkeypatch):
    from vibeflow.tooling.presentation import viewer
    assets=tmp_path/"tool";assets.mkdir()
    (assets/"index.html").write_text('<link href="new-style.css"><script src="new-module.js"></script>'
        '<script src="preview.config.js"></script><a href="#flow">Flow</a><a href="https://example.org">Help</a>')
    (assets/"new-style.css").write_text("body{}")
    (assets/"new-module.js").write_text("window.newModule=true;")
    root=tmp_path/"workspace";root.mkdir()
    config=root/"vibeflow-preview.config.js";config.write_text('window.VibeFlowViewerConfig={dataRoot:"custom/"};')
    monkeypatch.setattr(viewer,"viewer_assets",lambda:assets)
    install_page(root)
    html=(root/"vibeflow-preview.html").read_text()
    assert 'href="vibeflow-preview/assets/new-style.css"' in html
    assert 'src="vibeflow-preview/assets/new-module.js"' in html
    assert 'src="vibeflow-preview.config.js"' in html
    assert 'href="#flow"' in html and 'href="https://example.org"' in html
    assert (root/"vibeflow-preview/assets/new-module.js").read_text()=="window.newModule=true;"
    assert config.read_text()=='window.VibeFlowViewerConfig={dataRoot:"custom/"};'


def test_project_directory_projects_architecture_for_registered_roots(tmp_path):
    from vibeflow.tooling.presentation.preview.exporter import publish_project
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    roots = []
    for name in ("app", "peer", "empty"):
        root = tmp_path / name
        (root / "configs").mkdir(parents=True)
        (root / "vibeflow_project.jsonc").write_text(json.dumps({"project_target":"python",
            "architecture":{"documents":[{"workflow":"configs/deleted.jsonc", "document":"ARCHITECTURE.jsonc"}]}}))
        (root / "configs/deleted.jsonc").write_text('{"pipeline":{"nodes":[]}}')
        roots.append({"id":name,"path":name})
        if name != "empty":
            (root / "configs/main.jsonc").write_text('{"pipeline":{"nodes":[]}}')
            (root / "outside.jsonc").write_text('{"pipeline":{"nodes":[]}}')
    (tmp_path / "app/configs/broken.jsonc").write_text('{"pipeline":')
    workspace_file = tmp_path / "vibeflow_config.jsonc"
    workspace_file.write_text(json.dumps({"roots":roots}))
    workspace = load_workspace_config(workspace_file)
    for name in ("app", "peer", "empty"):
        (tmp_path / name / "configs/deleted.jsonc").unlink()
    from vibeflow.tooling.project.preparation import ProjectPreparation
    ProjectPreparation(workspace).review(write_architecture=True)
    publish_project(tmp_path, workspace)
    script = (tmp_path / "vibeflow-preview/project.js").read_text()
    catalog = json.loads(script[len("VibeFlowPreview.project("):-3])
    assert {root["id"]:[w["path"] for w in root["workflows"]] for root in catalog["roots"]} == {
        "app":["configs/broken.jsonc", "configs/deleted.jsonc", "configs/main.jsonc", "outside.jsonc"], "peer":["configs/deleted.jsonc", "configs/main.jsonc", "outside.jsonc"], "empty":["configs/deleted.jsonc"]}
    assert not catalog["inventory_complete"]
    (tmp_path / "app/configs/main.jsonc").unlink()
    (tmp_path / "app/vibeflow_project.jsonc").write_text('{"project_target":"python"}')
    workspace_file.write_text(json.dumps({"roots":roots[:1]}))
    ProjectPreparation(load_workspace_config(workspace_file)).review(write_architecture=True)
    publish_project(tmp_path, load_workspace_config(workspace_file))
    script = (tmp_path / "vibeflow-preview/project.js").read_text()
    catalog = json.loads(script[len("VibeFlowPreview.project("):-3])
    assert [root["id"] for root in catalog["roots"]] == ["app"]
    assert [w["path"] for w in catalog["roots"][0]["workflows"]] == ["configs/broken.jsonc", "outside.jsonc"]


def test_concurrent_catalog_updates_and_reindex(tmp_path):
    install_page(tmp_path)
    def publish(index):
        record = new_record(tmp_path, {"id":"root:main", "root_id":"root", "path":"main", "target":"python"}, "run", "running")
        record.update("running")
        record.update("failed" if index % 2 else "succeeded")
        return record.metadata["id"]
    with ThreadPoolExecutor(max_workers=12) as pool:
        ids = list(pool.map(publish, range(48)))
    assert len(set(ids)) == 48
    index = tmp_path / "vibeflow-preview/index.js"
    lines = index.read_text().splitlines()
    assert len(lines) == 96
    merged = {}
    for line in lines:
        assert line.startswith("VibeFlowPreview.record(") and line.endswith(");")
        value = json.loads(line[len("VibeFlowPreview.record("):-2])
        merged[value["id"]] = value
    assert sorted(v["status"] for v in merged.values()) == ["failed"]*24+["succeeded"]*24
    index.write_text("damaged catalog")
    result = reindex(tmp_path)
    assert result["records"] == 48 and not result["errors"]
    assert len(index.read_text().splitlines()) == 48
    assert {json.loads(p.read_text())["status"] for p in (tmp_path / "vibeflow-preview/snapshots").glob("*/record.json")} == {"failed", "succeeded"}
    broken=tmp_path/"vibeflow-preview/snapshots/broken/record.json"
    broken.parent.mkdir();broken.write_text("[]")
    result=reindex(tmp_path)
    assert result["records"] == 48 and len(result["errors"]) == 1


@pytest.mark.parametrize("value", [None, [], {"unknown":True}, {"workflow_links":{}},
    {"workflow_links":[{"from_workflow":"a"}]},
    {"workflow_links":[{"from_workflow":"/a","to_root":"b","to_workflow":"b","kind":"call"}]},
    {"workflow_links":[{"from_workflow":"a","to_root":"b","to_workflow":"../b","kind":"reference"}]}])
def test_invalid_preview_options(value):
    with pytest.raises(WorkspaceConfigError):
        validate_preview_options(value, path=Path("vibeflow_project.jsonc"))


def test_cyclic_missing_workflow_links_are_display_only():
    validate_preview_options({"workflow_links":[
        {"from_workflow":"a.jsonc","from_call_path":"outer/child","to_root":"missing","to_workflow":"b.jsonc","kind":"call"},
        {"from_workflow":"b.jsonc","to_root":"project","to_workflow":"a.jsonc","kind":"reference","label":"back"},
    ]}, path=Path("vibeflow_project.jsonc"))
    validate_preview_options({"workflow_links":[
        {"from_workflow":"./configs/../main.jsonc", "to_root":"other",
         "to_workflow":"./target.jsonc", "kind":"reference"}
    ]}, path=Path("vibeflow_project.jsonc"))


def test_reindex_preserves_a_status_written_during_replay(tmp_path, monkeypatch):
    from vibeflow.tooling.presentation.preview import catalog
    install_page(tmp_path)
    record = new_record(tmp_path, {"id":"root:main"}, "run", "running")
    record.update("running")
    append = catalog.append_record
    def replay(root, metadata):
        # A producer finishes after reindex has read the old record.json.
        monkeypatch.setattr(catalog, "append_record", append)
        record.update("succeeded")
        append(root, metadata)
    monkeypatch.setattr(catalog, "append_record", replay)
    assert reindex(tmp_path)["records"] == 1
    rows = [json.loads(line[len("VibeFlowPreview.record("):-2])
            for line in (tmp_path/"vibeflow-preview/index.js").read_text().splitlines()]
    assert [row["status"] for row in rows] == ["succeeded", "running"]
    assert max(rows, key=lambda row:row["revision"])["status"] == "succeeded"


def test_preview_command_uses_registered_project_or_explicit_data_directory(tmp_path, monkeypatch, capsys):
    from tests.fixtures.support.projects import register_root
    from vibeflow.tooling.presentation.preview.cli import main
    root = tmp_path / "工作区"
    child = root / "project/configs"
    child.mkdir(parents=True)
    register_root(child.parent)
    monkeypatch.chdir(child)
    assert main([]) == 0
    assert Path(json.loads(capsys.readouterr().out)["output"]).parent == root
    assert (root / "vibeflow-preview/index.js").read_text() == ""
    (root / "vibeflow_config.jsonc").unlink()
    assert main([]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "ERROR"
    assert main(["--preview-root", str(root / "standalone viewer")]) == 0
    assert Path(json.loads(capsys.readouterr().out)["output"]).parent == root / "standalone viewer"


def test_adapter_discovers_registered_project_root(tmp_path):
    from tests.fixtures.support.projects import register_root
    from vibeflow.tooling.application.presentation_targets import preview_workspace
    from vibeflow.tooling.presentation.preview.exporter import workflow_identity
    root = tmp_path / "独立 项目"
    config = root / "configs/main.jsonc"
    config.parent.mkdir(parents=True)
    register_root(root)
    config.write_text('{}')
    workspace = preview_workspace(config)
    assert workspace.root == root.parent
    assert workflow_identity(config, workspace)["path"] == "configs/main.jsonc"


def test_node_aliases_preserve_identity():
    from vibeflow.tooling.application.python.presentation.mermaid.labels import _safe_id as python_id
    from vibeflow.tooling.application.javascript.presentation.diagrams import _safe_id as javascript_id
    names = ["a-b", "a_b", "a/b", "a.b", "中文", "中_", "end", "n_end", "1", "n_1", "vf_encoded_612d62"]
    for mapper in (python_id, javascript_id):
        assert len({mapper(value) for value in names}) == len(names)


def test_missing_graph_and_nonzero_delegate_status_are_recorded(tmp_path):
    from vibeflow.tooling.application.python.preview_run import source_run_preview, bind_run_observer
    from tests.fixtures.support.projects import register_root
    register_root(tmp_path / "app")
    config = tmp_path / "app/missing.jsonc"
    with source_run_preview(config):
        bind_run_observer(SimpleNamespace(result={"status":"failed","error":"program exited with code 4"}))
    with pytest.raises(RuntimeError):
        with source_run_preview(config):
            raise RuntimeError("refused before a valid graph existed")
    metadata = [json.loads(p.read_text()) for p in (tmp_path/"vibeflow-preview/snapshots").glob("*/record.json")]
    assert len(metadata) == 2 and all(m["status"] == "failed" for m in metadata)
    assert all(m["preview_error"] and m["views"] == [] for m in metadata)


def test_ancillary_build_failure_updates_actual_status(tmp_path):
    from vibeflow.tooling.presentation.preview.diagnostics import preview_operation
    install_page(tmp_path)
    record = new_record(tmp_path, {"id":"fixture:main"}, "build", "building")
    with pytest.raises(RuntimeError):
        with preview_operation(record):
            raise RuntimeError("target compiler failed")
    value=json.loads((record.directory/"record.json").read_text())
    assert value["status"] == "failed" and value["error"] == "target compiler failed"


def test_source_run_is_not_blocked_by_preview_status_write_failure(tmp_path, monkeypatch):
    from vibeflow.tooling.application.python import preview_run
    class Record:
        metadata = {}
        def update(self, *args, **kwargs):
            raise OSError("preview device unavailable")
    monkeypatch.setattr(preview_run, "python_preview", lambda **kwargs:Record())
    run_dir = tmp_path/"run";run_dir.mkdir()
    from tests.fixtures.support.projects import register_root
    register_root(tmp_path / "app")
    with preview_run.source_run_preview(tmp_path/"app/main.jsonc"):
        from types import SimpleNamespace
        prepared = SimpleNamespace(graph=SimpleNamespace(entries={}, default_entry=""))
        preview_run.start_run_preview(prepared, run_dir)
    assert "preview device unavailable" in (run_dir/"preview.error.txt").read_text()


def test_data_snapshot_has_no_render_dependency_and_separates_installer(tmp_path, monkeypatch):
    from vibeflow.tooling.presentation.preview.exporter import publish_preview
    from vibeflow.tooling.presentation import mermaid
    monkeypatch.setattr(mermaid,"render_mermaid_svg",lambda *a,**k:pytest.fail("data export invoked Mermaid"))
    record=publish_preview(root=tmp_path,workflow={"id":"r:main"},category="review",status="passed",
        architecture={"workflow":{"nodes":[],"edges":[]}})
    payload=json.loads((record.directory/"snapshot.js").read_text()[len("VibeFlowPreview.snapshot("):-3])
    assert payload["version"]==4 and "bodies" not in payload
    assert payload["artifacts"]=={} and not (tmp_path/"vibeflow-preview.html").exists()
    assert not list(record.directory.glob("*.svg"))
    install_page(tmp_path)
    config=tmp_path/"vibeflow-preview.config.js";config.write_text('window.VibeFlowViewerConfig={dataRoot:"other/"};')
    install_page(tmp_path)
    assert 'dataRoot:"other/"' in config.read_text()
    legacy=record.directory.parent/"legacy";legacy.mkdir();(legacy/"record.json").write_text('{"id":"legacy","workflow":{}}')
    result=reindex(tmp_path)
    assert result["obsolete"]==1 and result["records"]==1


def test_svg_attachment_is_published_to_operation_metadata(tmp_path):
    from vibeflow.tooling.presentation.preview.exporter import publish_preview, attach_svg
    record=publish_preview(root=tmp_path,workflow={"id":"r:main"},category="review",status="reviewing",
        architecture={"workflow":{"nodes":[],"edges":[]}})
    source=tmp_path/"explicit.svg";source.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    attach_svg(record,source)
    metadata=json.loads((record.directory/"record.json").read_text())
    payload=json.loads((record.directory/"snapshot.js").read_text()[len("VibeFlowPreview.snapshot("):-3])
    assert metadata["artifacts"] == payload["artifacts"] == {"svg":"review.svg"}
    assert (record.directory/"review.svg").read_text() == source.read_text()
    assert metadata["status"] == "reviewing"


def _presentations(root):
    from vibeflow.core.descriptors import DescriptorCatalogs, NodeDescriptor, NodeContractDescriptor
    from vibeflow.core.style import NODE_SHAPES
    from vibeflow.targets.python.project import NodeRegistry
    from vibeflow.tooling.project.graph_config import parse_graph_config
    from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
    from vibeflow.tooling.application.javascript.presentation.architecture import build_architecture_facts

    registry = NodeRegistry()
    descriptor = NodeDescriptor("fixture.work", "Work", "Preview node", "1", "process", contract=NodeContractDescriptor(), rulesets=(), node_type="vibeflow.node")
    registry.register(descriptor, loader=lambda: pytest.fail("preview must not execute node implementations"))
    catalogs = DescriptorCatalogs.empty(); catalogs.nodes.register(descriptor)
    external=NodeDescriptor("fixture.external","External","External dependency","1","process",contract=NodeContractDescriptor(),rulesets=(),external=True, node_type="vibeflow.node")
    registry.register(external,loader=lambda:pytest.fail("external dependency must not execute"));catalogs.nodes.register(external)
    def call(name, kind="fixture.work", **fields):
        return dict(id=name, definition_id=kind, display_name=name, description="真实预览测试 "+name, **fields)
    def body(key, nodes):
        return dict(type_key=key, display_name=key, description=key, expand=False, requires=[], provides=[],
                    pipeline={"nodes":nodes,"edges":[[a["id"],b["id"]] for a,b in zip(nodes,nodes[1:])]})
    shapes = [call("shape_"+shape.replace("-","_"),style={"shape":shape,"fill":"#d6eaff","stroke":"#425a78","text":"#172b45","icon":"M"}) for shape in sorted(NODE_SHAPES)]
    next(n for n in shapes if n["id"] == "shape_circle")["definition_id"] = "fixture.external"
    next(n for n in shapes if n["id"] == "shape_rect")["definition_id"] = "deep0"
    deep = [body("deep"+str(i), [call("next", "deep"+str(i+1))]) for i in range(5)]
    deep.append(body("deep5", [call("bottom")]))
    config = root / "main.jsonc"
    graph = parse_graph_config({"rulesets":[], "nodeset_types":[*deep,body("leaf", shapes),body("outer",[call("inner","leaf")])],
        "pipeline":{"nodes":[call("first","outer"),call("second","outer",style={"fill":"#efe0f8"}),
            call("loop","vibeflow.loop.while",requires=[],provides=[],loop={"body":"outer","max_iterations":1,"stop_after":1}),
            call("future","future.type",status="planned",flow_kind="process",requires=[],provides=[])],
            "edges":[["first","second"],["second","loop"],["loop","future"]]}},
        project_root=root,root_path=root,root_id="fixture",source_path=config)
    prepared = prepare_python_presentation(graph,registry=registry)
    compiled_nodeset_types = {key:prepared.graph_for(value.graph)[1] for key,value in graph.nodeset_types.items()}
    architecture = build_architecture_facts(graph,compiled=prepared.compiled,compiled_nodeset_types=compiled_nodeset_types,
        catalogs=catalogs,used_node_ids=frozenset({descriptor.id}),active_base_lib_ids=frozenset(),
        plugin_records=(),root_id="fixture",source_path="main.jsonc")
    root_model=SimpleNamespace(id="fixture",path=root,project_target="python",architecture_documents=(),project_config={"preview":{"workflow_links":[
        {"from_workflow":"main.jsonc","from_call_path":"first","to_root":"remote","to_workflow":"other.jsonc","kind":"call","label":"历史目标"},
        {"from_workflow":"main.jsonc","to_root":"missing","to_workflow":"absent.jsonc","kind":"reference","label":"缺失目标"}]}})
    (root/"remote").mkdir()
    remote_model=SimpleNamespace(id="remote",path=root/"remote",project_target="javascript",architecture_documents=(),project_config={"preview":{"workflow_links":[
        {"from_workflow":"other.jsonc","to_root":"fixture","to_workflow":"main.jsonc","kind":"reference"}]}})
    workspace=SimpleNamespace(root=root,roots=(root_model,remote_model),root_for_path=lambda p:root_model)
    javascript=SimpleNamespace(warnings=(),graph=graph,compiled=prepared.compiled,compiled_nodeset_types=compiled_nodeset_types,
        catalogs=catalogs,architecture=architecture,workspace=workspace,config_path=config)
    return prepared,javascript,workspace,config


def test_real_offline_shapes_nested_browser_and_history(tmp_path):
    from vibeflow.core.style import NODE_SHAPES
    from vibeflow.tooling.presentation.mermaid import is_mermaid_svg_renderer_available, _find_mmdc
    if not is_mermaid_svg_renderer_available():
        pytest.skip("locked Mermaid renderer required; supplied by the full gate")
    from vibeflow.tooling.application.python.presentation.preview import python_preview
    from vibeflow.tooling.application.javascript.presentation.preview import javascript_preview

    prepared,javascript,workspace,config = _presentations(tmp_path)
    first = python_preview(prepared,config=config,workspace=workspace,status="passed")
    second = javascript_preview(javascript,status="passed")
    assert first.metadata["workflow"]["target"] == "python"
    assert second.metadata["workflow"]["target"] == "javascript"
    # Read the actual producer protocol, not a second rendering implementation.
    payload = json.loads((first.directory/"snapshot.js").read_text()[len("VibeFlowPreview.snapshot("):-3])
    assert payload["version"] == 4 and "bodies" not in payload
    assert payload["architecture"] == prepared.architecture()
    assert not list(first.directory.glob("*.svg"))
    from vibeflow.tooling.presentation.preview.exporter import attach_svg
    svg=tmp_path/"reference.svg";svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300"><rect width="600" height="300" fill="#ece7da"/><text x="20" y="80">Optional opaque SVG reference</text></svg>')
    attach_svg(first,svg)
    destination=tmp_path/"搬移 空格";destination.mkdir()
    shutil.copy2(tmp_path/"vibeflow-preview.html",destination)
    shutil.copy2(tmp_path/"vibeflow-preview.config.js",destination)
    shutil.copytree(tmp_path/"vibeflow-preview",destination/"vibeflow-preview")
    tool=tmp_path/"独立 工具"
    shutil.copytree(Path(__file__).resolve().parents[2]/"tools/workflow-viewer",tool)
    (tool/"preview.config.js").write_text('window.VibeFlowViewerConfig={dataRoot:"../搬移 空格/vibeflow-preview/"};')
    browser = Path(__file__).resolve().parents[1]/"fixtures/preview/browser.cjs"
    renderer = _find_mmdc().resolve()
    result=subprocess.run(["node",str(browser),str(renderer),str(destination/"vibeflow-preview.html"),
            first.metadata["id"],second.metadata["id"],str(tool/"index.html"),json.dumps(sorted(NODE_SHAPES))],capture_output=True,text=True,timeout=120)
    assert result.returncode == 0, result.stdout+result.stderr
    report=json.loads(result.stdout)
    assert report["shapes"] == len(NODE_SHAPES) and report["network_requests"] == [] and not report["page_errors"]


def test_real_project_resource_views(tmp_path):
    from vibeflow.tooling.presentation.mermaid import is_mermaid_svg_renderer_available, _find_mmdc
    if not is_mermaid_svg_renderer_available():
        pytest.skip("locked Mermaid renderer required; supplied by the full gate")
    from tests.fixtures.python.review_layout.fixtures import write_project
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    from vibeflow.tooling.application.python.workspace_service import load_workspace_graph_for_export
    from vibeflow.tooling.application.python.presentation.preview import python_preview
    project = tmp_path / "project"
    write_project(project)
    workspace = load_workspace_config(project.parent / "vibeflow_config.jsonc")
    config = project / "workflow.jsonc"
    loaded = load_workspace_graph_for_export(config, workspace=workspace, validate_health=True, _include_presentation=True)
    assert loaded[4] is None
    record = python_preview(loaded[-1],config=config,workspace=workspace)
    browser = Path(__file__).resolve().parents[1]/"fixtures/preview/browser.cjs"
    result = subprocess.run(["node",str(browser),str(_find_mmdc().resolve()),str(record.root/"vibeflow-preview.html"),"--resources"],
                            capture_output=True,text=True,timeout=90)
    assert result.returncode == 0, result.stdout+result.stderr
    assert json.loads(result.stdout)["resources"] is True


def test_node_details_edge_roles_and_contracts_in_real_browser(tmp_path):
    from vibeflow.core.contracts import DataProvider, DataRequirement
    from vibeflow.core.descriptors import DescriptorCatalogs, NodeDescriptor, NodeContractDescriptor
    from vibeflow.targets.python.project import NodeRegistry
    from vibeflow.tooling.project.graph_config import parse_graph_config
    from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
    from vibeflow.tooling.application.javascript.presentation.architecture import build_architecture_facts
    from vibeflow.tooling.presentation.preview.exporter import publish_preview
    from vibeflow.tooling.presentation.mermaid import _find_mmdc, is_mermaid_svg_renderer_available
    if not is_mermaid_svg_renderer_available(): pytest.skip("full gate supplies locked browser")
    registry=NodeRegistry();catalogs=DescriptorCatalogs.empty()
    contracts={"emit":NodeContractDescriptor(provides=(DataProvider("payload","fixture.payload","计算结果"),),
        output_semantics={"payload":("结果携带本次计算的完整数值。",)},
        params_schema={"factor":{"type":"number","description":"计算倍率"}},params_defaults={"factor":2}),
        "take":NodeContractDescriptor(requires=(DataRequirement("fixture.payload","exactly_one","待处理结果"),),
            input_semantics={"fixture.payload":("消费上游结果，不重新计算。",)})}
    for key,kind in (("boundary","terminal"),("emit","process"),("take","process"),("choice","decision")):
        descriptor=NodeDescriptor("detail."+key,"详情测试 "+key,"类型定义："+key+" 的完整职责说明。","2.1",kind,
            contract=contracts.get(key,NodeContractDescriptor()),rulesets=(), node_type="vibeflow.node")
        registry.register(descriptor,loader=lambda:pytest.fail("viewer executed business code"));catalogs.nodes.register(descriptor)
    calls=[{"id":name,"definition_id":"detail."+kind,"display_name":name,"description":"调用职责："+name,
            **({"join_policy":"all"} if name=="join" else {}),**({"config":{"factor":3}} if name=="emit" else {})}
           for name,kind in (("start","boundary"),("emit","emit"),("left","take"),("right","take"),("join","take"),
                             ("choice","choice"),("yes","boundary"),("no","boundary"),("end","boundary"))]
    graph=parse_graph_config({"rulesets":[],"pipeline":{"nodes":calls,"edges":[
        {"from":"start","to":"emit","transfer":False},
        {"from":"start","to":"emit","schedule":False,"when":"route == 'data_only'"},
        ["emit","left"],["emit","right"],
        ["left","join"],["right","join"],{"from":"emit","to":"join","schedule":False,"transfer":True},
        ["join","choice"],{"from":"choice","to":"yes","when":"route == 'yes'"},
        {"from":"choice","to":"no","when":"route == 'no'"},["yes","end"],["no","end"]]}},
        project_root=tmp_path,root_path=tmp_path,root_id="details",source_path=tmp_path/"main.jsonc")
    prepared=prepare_python_presentation(graph,registry=registry)
    javascript=build_architecture_facts(prepared.graph,compiled=prepared.compiled,compiled_nodeset_types={},catalogs=catalogs,
        used_node_ids=frozenset(catalogs.nodes.to_dict()),active_base_lib_ids=frozenset(),plugin_records=(),
        root_id="details",source_path="main.jsonc")
    records=[]
    for target,architecture in (("python",prepared.architecture()),("javascript",javascript)):
        records.append(publish_preview(root=tmp_path,workflow={"id":target+":main.jsonc","root_id":target,"path":"main.jsonc","name":target,"target":target},
            category="review",status="passed",architecture=architecture))
    install_page(tmp_path)
    browser=Path(__file__).resolve().parents[1]/"fixtures/preview/details.cjs"
    result=subprocess.run(["node",str(browser),str(_find_mmdc().resolve()),str(tmp_path/"vibeflow-preview.html"),
                           *(r.metadata["id"] for r in records)],capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)["targets"]==["python","javascript"]


def test_default_python_commands_and_explicit_svg_failure(tmp_path, monkeypatch, capsys):
    import builtins
    from tests.fixtures.python.review_layout.fixtures import write_project
    from vibeflow.tooling.application.cli import main
    from vibeflow.tooling.presentation import mermaid
    project=tmp_path/"python";write_project(project)
    def no_renderer(*args,**kwargs):
        raise RuntimeError("Mermaid deliberately unavailable")
    monkeypatch.setattr(mermaid,"_find_mmdc",no_renderer)
    common=["--workspace",str(project.parent/"vibeflow_config.jsonc"),"--config",str(project/"workflow.jsonc")]
    original_import=builtins.__import__
    def no_graphics_import(name,globals=None,locals=None,fromlist=(),level=0):
        if ".presentation.mermaid" in name or name=="vibeflow.tooling.presentation" and "mermaid" in fromlist:
            pytest.fail("default command imported Mermaid: "+name)
        return original_import(name,globals,locals,fromlist,level)
    with monkeypatch.context() as scope:
        scope.setattr(builtins,"__import__",no_graphics_import)
        review_status=main(["review",*common]);review_output=capsys.readouterr().out
        assert review_status==0,review_output
        assert main(["build",*common,"--out-dir",str(tmp_path/"bundle")])==0;capsys.readouterr()
        assert main(["run",*common,"--run-root",str(tmp_path/"runs"),"--run-id","actual"] )==0;capsys.readouterr()
    records=[json.loads(f.read_text()) for f in (project.parent/"vibeflow-preview/snapshots").glob("*/record.json")]
    assert {(r["category"],r["status"]) for r in records}=={("review","passed"),("build","succeeded"),("run","succeeded")}
    assert all(r["version"]==4 for r in records)
    assert not list((project.parent/"vibeflow-preview/snapshots").rglob("*.svg"))
    assert main(["review",*common,"--with-svg"])==1;capsys.readouterr()
    failed=[json.loads(f.read_text()) for f in (project.parent/"vibeflow-preview/snapshots").glob("*/record.json") if json.loads(f.read_text())["status"]=="failed"]
    assert len(failed)==1
    data=json.loads((project.parent/"vibeflow-preview/snapshots"/failed[0]["id"]/"snapshot.js").read_text()[len("VibeFlowPreview.snapshot("):-3])
    assert data["architecture"]["workflow"]["nodes"] and not data["artifacts"]


def test_default_javascript_commands_and_explicit_svg_failure(tmp_path, monkeypatch, capsys):
    from tests.targets.javascript.test_code_plugins import project as javascript_project
    from vibeflow.tooling.application.cli import main
    from vibeflow.tooling.presentation import mermaid
    project=tmp_path/"javascript"
    javascript_project(project)
    (project / "vibeflow_project.jsonc").write_text(json.dumps({"project_target":"javascript", "architecture":{"documents":[
        {"workflow":"workflow.jsonc","document":"ARCHITECTURE.jsonc"}]}}))
    monkeypatch.setattr(mermaid,"_find_mmdc",lambda:(_ for _ in ()).throw(RuntimeError("Mermaid deliberately unavailable")))
    common=["--workspace",str(project.parent/"vibeflow_config.jsonc"),"--config",str(project/"workflow.jsonc")]
    review_status=main(["review",*common]);review_output=capsys.readouterr().out
    assert review_status==0,review_output
    assert main(["build",*common,"--target","node","--profile","single-esm","--out-dir",str(tmp_path/"bundle")])==0;capsys.readouterr()
    records=[json.loads(f.read_text()) for f in (project.parent/"vibeflow-preview/snapshots").glob("*/record.json")]
    assert {(r["category"],r["status"]) for r in records}=={("review","passed"),("build","succeeded")}
    for record in records:
        script=(project.parent/"vibeflow-preview/snapshots"/record["id"]/"snapshot.js").read_text()
        architecture=json.loads(script[len("VibeFlowPreview.snapshot("):-3])["architecture"]
        assert {"rule_selections","rule_checks","implementation_graph"} <= architecture.keys()
        assert architecture["implementation_graph"] and architecture["workflow"]["nodes"]
    assert main(["review",*common,"--with-svg"])==1;capsys.readouterr()
    records=[json.loads(f.read_text()) for f in (project.parent/"vibeflow-preview/snapshots").glob("*/record.json")]
    failed=next(r for r in records if r["status"]=="failed")
    assert (project.parent/"vibeflow-preview/snapshots"/failed["id"]/"snapshot.js").is_file()


def test_cancelled_run_uses_observer_terminal_result(tmp_path):
    from vibeflow.targets.python.runtime.observation import RunObservation
    from vibeflow.tooling.application.python.preview_run import source_run_preview,bind_run_observer
    from tests.fixtures.support.projects import register_root
    register_root(tmp_path / "app")
    observer=RunObservation(tmp_path/"run")
    with pytest.raises(KeyboardInterrupt):
        with source_run_preview(tmp_path/"app/absent.jsonc"):
            with observer.scope():
                bind_run_observer(observer)
                with pytest.raises(TypeError):observer.result["status"]="succeeded"
                raise KeyboardInterrupt("cancelled")
    records=[json.loads(f.read_text()) for f in (tmp_path/"vibeflow-preview/snapshots").glob("*/record.json")]
    assert records[0]["status"]==observer.result["status"]=="failed"
    assert records[0]["error"]==observer.result["error"]=="cancelled"


def test_real_resource_cards_express_all_declared_shapes(tmp_path):
    from vibeflow.core.style import NODE_SHAPES
    from vibeflow.tooling.presentation.mermaid import is_mermaid_svg_renderer_available, _find_mmdc
    from tests.fixtures.support.projects import register_root
    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    from vibeflow.tooling.application.python.workspace_service import load_workspace_graph_for_export
    from vibeflow.tooling.application.python.presentation.preview import python_preview
    if not is_mermaid_svg_renderer_available():
        pytest.skip("full gate supplies the locked browser")
    root = tmp_path / "project"
    register_root(root)
    (root / "base_lib").mkdir()
    (root / "nodes").mkdir()
    selections, libraries = [], []
    for index, shape in enumerate(sorted(NODE_SHAPES)):
        style = {"shape":shape,"fill":"#c8e4ff","stroke":"#1a5276","text":"#123456","icon":"M"}
        library = "shapes.lib" + str(index)
        libraries.append(library)
        (root / "base_lib" / f"lib{index}.py").write_text(
            'from vibeflow.targets.python.sdk import base_lib\n'
            f'@base_lib(id={library!r},rulesets=[],presentation={style!r})\n'
            'def identity(value):\n    return value\n')
        package = root / "plugins" / f"shape{index}"
        package.mkdir(parents=True)
        (package / "plugin.py").write_text('from vibeflow.targets.python.sdk import Plugin\n'
            f'plugin=Plugin(id="shapes.plugin{index}",resources=[],presentation={style!r})\n')
        selections.append({"source":{"kind":"file","ref":f"plugins/shape{index}/plugin.py"}})
    (root / "nodes/main.py").write_text('from vibeflow.targets.python.sdk import node\n'
        f'@node(id="shapes.main",node_type="vibeflow.node",flow_kind="terminal",contract={{}},rulesets=[],base_libs={libraries!r})\n'
        'class Main:\n    def run_pure(self,inputs,params):\n        return {}\n')
    config = root / "workflow.jsonc"
    config.write_text(json.dumps({"plugins":selections,"base_lib":{"modules":libraries},"rulesets":[],"pipeline":{"nodes":[{
        "id":"main","definition_id":"shapes.main","display_name":"Resource shapes","description":"One real workflow using all shape resources"}]}}))
    workspace = load_project_workspace(config)
    loaded = load_workspace_graph_for_export(config,workspace=workspace,validate_health=False,_include_presentation=True)
    assert loaded[4] is None
    record = python_preview(loaded[-1],config=config,workspace=workspace)
    snapshot = json.loads((record.directory / "snapshot.js").read_text()[len("VibeFlowPreview.snapshot("):-3])
    for library in libraries:
        assert snapshot["architecture"]["implementation_graph"]["resources"]["base_lib:" + library]["owner"]["kind"] == "root"
    browser = Path(__file__).resolve().parents[1] / "fixtures/preview/resource-shapes.cjs"
    result = subprocess.run(["node",str(browser),str(_find_mmdc().resolve()),str(record.root/"vibeflow-preview.html"),json.dumps(sorted(NODE_SHAPES))],
        capture_output=True,text=True,timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["cards"] == len(NODE_SHAPES) * 2
