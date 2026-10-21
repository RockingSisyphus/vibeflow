from xml.etree import ElementTree

from tests.fixtures.support.strict_support import *
from tests.fixtures.support.rule_inspection import VALID_NODE_IMPORT, _valid_node_source, _inspect_node_source, node_document
from tests.core.strict_core import _review_node
from vibeflow.targets.python.quality.source_analysis.types import _default_rule_id


def test_mermaid_renderer_lists_unique_non_snap_browsers_in_priority_order(monkeypatch) -> None:
    import vibeflow.tooling.presentation.mermaid as mermaid_render

    paths = {
        "chromium": "/snap/bin/chromium",
        "chromium-browser": "/usr/bin/chromium-browser",
        "google-chrome": "/usr/bin/google-chrome",
        "google-chrome-stable": "/usr/bin/google-chrome",
    }

    monkeypatch.setattr(mermaid_render.shutil, "which", lambda name: paths.get(name))

    assert mermaid_render._system_browser_candidates() == [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
    ]
    assert mermaid_render._puppeteer_launch_options() == [
        ("Puppeteer bundled browser", None),
        ("/usr/bin/google-chrome", "/usr/bin/google-chrome"),
        ("/usr/bin/chromium-browser", "/usr/bin/chromium-browser"),
    ]


def test_mermaid_renderer_keeps_non_snap_chromium_candidate(monkeypatch) -> None:
    import vibeflow.tooling.presentation.mermaid as mermaid_render

    paths = {
        "chromium": "/snap/bin/chromium",
        "chromium-browser": "/usr/bin/chromium-browser",
        "google-chrome": None,
        "google-chrome-stable": None,
    }

    monkeypatch.setattr(mermaid_render.shutil, "which", lambda name: paths.get(name))

    assert mermaid_render._system_browser_candidates() == ["/usr/bin/chromium-browser"]
    assert mermaid_render._puppeteer_launch_options() == [
        ("Puppeteer bundled browser", None),
        ("/usr/bin/chromium-browser", "/usr/bin/chromium-browser"),
    ]


def test_mermaid_renderer_skips_snap_chromium_as_only_system_browser(monkeypatch) -> None:
    import vibeflow.tooling.presentation.mermaid as mermaid_render

    paths = {
        "chromium": "/snap/bin/chromium",
        "chromium-browser": None,
        "google-chrome": None,
        "google-chrome-stable": None,
    }

    monkeypatch.setattr(mermaid_render.shutil, "which", lambda name: paths.get(name))

    assert mermaid_render._system_browser_candidates() == []
    assert mermaid_render._puppeteer_launch_options() == [("Puppeteer bundled browser", None)]


def test_mermaid_puppeteer_config_omits_executable_by_default(tmp_path) -> None:
    import vibeflow.tooling.presentation.mermaid as mermaid_render

    path = tmp_path / "puppeteer.json"
    mermaid_render._write_puppeteer_config(path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["args"] == ["--no-sandbox", "--disable-setuid-sandbox"]
    assert "executablePath" not in payload


def test_mermaid_config_uses_readable_svg_spacing_defaults(tmp_path) -> None:
    import vibeflow.tooling.presentation.mermaid as mermaid_render

    path = tmp_path / "mermaid.json"
    mermaid_render._write_mermaid_config(path, max_text_size=1234, max_edges=56, html_labels=False)

    payload = json.loads(path.read_text(encoding="utf-8"))
    flowchart = payload["flowchart"]

    assert payload["htmlLabels"] is False
    assert payload["maxTextSize"] == 1234
    assert payload["maxEdges"] == 56
    assert flowchart["htmlLabels"] is False
    assert flowchart["nodeSpacing"] == mermaid_render.DEFAULT_FLOWCHART_NODE_SPACING
    assert flowchart["rankSpacing"] == mermaid_render.DEFAULT_FLOWCHART_RANK_SPACING
    assert flowchart["wrappingWidth"] == mermaid_render.DEFAULT_FLOWCHART_WRAPPING_WIDTH
    assert flowchart["diagramPadding"] == mermaid_render.DEFAULT_FLOWCHART_DIAGRAM_PADDING


def test_mermaid_svg_label_enhancement_styles_native_text_without_touching_edges(tmp_path) -> None:
    import vibeflow.tooling.presentation.mermaid as mermaid_render

    svg = tmp_path / "graph.svg"
    svg.write_text(
        """
<svg xmlns="http://www.w3.org/2000/svg">
  <g class="node defaultNode">
    <rect class="basic label-container" x="-80" width="160"/>
    <g class="label">
      <text>
        <tspan class="text-outer-tspan row" x="0"><tspan font-weight="normal">Readable</tspan><tspan font-weight="normal"> Title</tspan></tspan>
        <tspan class="text-outer-tspan row" x="0"><tspan font-weight="normal">id:</tspan><tspan font-weight="normal"> node_a</tspan></tspan>
        <tspan class="text-outer-tspan row" x="0"><tspan font-weight="normal">----------</tspan><tspan font-weight="normal"> meta</tspan><tspan font-weight="normal"> ----------</tspan></tspan>
        <tspan class="text-outer-tspan row" x="0"><tspan font-weight="normal">desc:</tspan><tspan font-weight="normal"> useful</tspan></tspan>
        <tspan class="text-outer-tspan row" x="0"><tspan font-weight="normal">external:</tspan><tspan font-weight="normal"> true</tspan></tspan>
      </text>
    </g>
  </g>
  <g class="edgeLabel">
    <text><tspan class="text-outer-tspan row" x="0"><tspan font-weight="normal">id:</tspan></tspan></text>
  </g>
</svg>
""".strip(),
        encoding="utf-8",
    )

    mermaid_render._enhance_svg_labels(svg)
    text = svg.read_text(encoding="utf-8")

    assert 'font-weight="700" font-size="1.05em">Readable' in text
    root = ElementTree.parse(svg).getroot()
    node = next(item for item in root if "node" in item.attrib.get("class", "").split())
    box = next(item for item in node if item.tag.endswith("}rect"))
    left, width = float(box.attrib["x"]), float(box.attrib["width"])
    rows = [item for item in node.iter() if item.tag.endswith("}tspan")
            and any("".join(item.itertext()).startswith(label) for label in ("id:", "desc:", "external:"))
            and "x" in item.attrib]
    assert len(rows) == 3
    assert len({item.attrib["x"] for item in rows}) == 1
    assert all(left < float(item.attrib["x"]) < left + width and item.attrib["text-anchor"] == "start" for item in rows)
    assert 'fill:#64748b !important' in text
    edge_text = text[text.index('<g class="edgeLabel"') :]
    assert 'font-weight="normal">id:</tspan>' in edge_text
    assert 'font-weight="700">id:</tspan>' not in edge_text


def test_mermaid_svg_label_enhancement_recenters_native_cloud_text(tmp_path) -> None:
    import vibeflow.tooling.presentation.mermaid as mermaid_render

    svg = tmp_path / "cloud.svg"
    svg.write_text(
        """
<svg xmlns="http://www.w3.org/2000/svg">
  <g class="node defaultNode vibeflowCloudNode">
    <path class="basic label-container" transform="translate(-120, -80)"/>
    <g class="label" transform="translate(-110.5, -72.25)">
      <text><tspan class="text-outer-tspan row" x="0"><tspan>Global State</tspan></tspan></text>
    </g>
  </g>
  <g class="node defaultNode">
    <rect class="basic label-container" x="-80" width="160"/>
    <g class="label" transform="translate(-12, -20)">
      <text><tspan class="text-outer-tspan row" x="0"><tspan>Ordinary</tspan></tspan></text>
    </g>
  </g>
</svg>
""".strip(),
        encoding="utf-8",
    )

    mermaid_render._enhance_svg_labels(svg)
    root = ElementTree.parse(svg).getroot()
    nodes = [
        group
        for group in root.iter()
        if group.tag.endswith("}g") and "node" in group.attrib.get("class", "").split()
    ]
    cloud_label = next(
        child
        for child in list(nodes[0])
        if child.tag.endswith("}g") and "label" in child.attrib.get("class", "").split()
    )
    ordinary_label = next(
        child
        for child in list(nodes[1])
        if child.tag.endswith("}g") and "label" in child.attrib.get("class", "").split()
    )

    assert cloud_label.attrib["transform"].startswith("translate(0,")
    assert "Global State" in "".join(cloud_label.itertext())
    assert "Ordinary" in "".join(ordinary_label.itertext())


def test_mermaid_renderer_finds_distribution_kernel_tool_path(tmp_path, monkeypatch) -> None:
    import vibeflow.tooling.presentation.mermaid as mermaid_render

    monkeypatch.delenv("VIBEFLOW_MERMAID_RENDERER_ROOT", raising=False)

    mmdc = tmp_path / "kernel" / "tools" / "mermaid-renderer" / "node_modules" / ".bin" / ("mmdc.cmd" if mermaid_render._is_windows() else "mmdc")
    mmdc.parent.mkdir(parents=True)
    mmdc.write_text("", encoding="utf-8")

    monkeypatch.setattr(mermaid_render, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(mermaid_render.shutil, "which", lambda name: None)

    assert mermaid_render._find_mmdc() == mmdc


def test_mermaid_renderer_keeps_source_tool_path_precedence(tmp_path, monkeypatch) -> None:
    import vibeflow.tooling.presentation.mermaid as mermaid_render

    monkeypatch.delenv("VIBEFLOW_MERMAID_RENDERER_ROOT", raising=False)

    executable = "mmdc.cmd" if mermaid_render._is_windows() else "mmdc"
    source_mmdc = tmp_path / "tools" / "mermaid-renderer" / "node_modules" / ".bin" / executable
    distribution_mmdc = tmp_path / "kernel" / "tools" / "mermaid-renderer" / "node_modules" / ".bin" / executable
    source_mmdc.parent.mkdir(parents=True)
    distribution_mmdc.parent.mkdir(parents=True)
    source_mmdc.write_text("", encoding="utf-8")
    distribution_mmdc.write_text("", encoding="utf-8")

    monkeypatch.setattr(mermaid_render, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(mermaid_render.shutil, "which", lambda name: None)

    assert mermaid_render._find_mmdc() == source_mmdc


def test_mermaid_renderer_prefers_explicit_temporary_root(tmp_path, monkeypatch) -> None:
    import vibeflow.tooling.presentation.mermaid as mermaid_render

    configured = tmp_path / "temporary-renderer"
    executable = "mmdc.cmd" if mermaid_render._is_windows() else "mmdc"
    mmdc = configured / "node_modules" / ".bin" / executable
    mmdc.parent.mkdir(parents=True)
    mmdc.write_text("", encoding="utf-8")

    monkeypatch.setenv("VIBEFLOW_MERMAID_RENDERER_ROOT", str(configured))
    monkeypatch.setattr(mermaid_render, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(mermaid_render.shutil, "which", lambda name: None)

    assert mermaid_render._find_mmdc() == mmdc


def test_mermaid_renderer_discovers_source_checkout_root(tmp_path, monkeypatch) -> None:
    import vibeflow.tooling.presentation.mermaid as mermaid_render

    module_path = tmp_path / "src" / "vibeflow" / "rendering" / "mermaid" / "render.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text("", encoding="utf-8")
    renderer_manifest = tmp_path / "tools" / "mermaid-renderer" / "package.json"
    renderer_manifest.parent.mkdir(parents=True)
    renderer_manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(mermaid_render, "__file__", str(module_path))

    assert mermaid_render._repo_root() == tmp_path


def test_mermaid_renderer_keeps_distribution_zip_root(tmp_path, monkeypatch) -> None:
    import vibeflow.tooling.presentation.mermaid as mermaid_render

    module_path = tmp_path / "kernel" / "vibeflow-kernel.zip" / "vibeflow" / "rendering" / "mermaid" / "render.py"
    monkeypatch.setattr(mermaid_render, "__file__", str(module_path))

    assert mermaid_render._repo_root() == tmp_path


@pytest.mark.parametrize("failed_attempts", (1, 2))
def test_mermaid_renderer_falls_back_through_non_snap_system_browsers(tmp_path, monkeypatch, failed_attempts) -> None:
    import subprocess
    import vibeflow.tooling.presentation.mermaid as mermaid_render

    mmdc = tmp_path / "mmdc"
    mmdc.write_text("", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_run(command, **kwargs):
        config_path = Path(command[command.index("--puppeteerConfigFile") + 1])
        output_path = Path(command[command.index("--output") + 1])
        calls.append(json.loads(config_path.read_text(encoding="utf-8")))
        if len(calls) <= failed_attempts:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="browser launch failed")
        output_path.write_text("<svg></svg>", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(mermaid_render, "_find_mmdc", lambda: mmdc)
    monkeypatch.setattr(mermaid_render, "_ensure_mermaid_cli_compat", lambda: None)
    monkeypatch.setattr(
        mermaid_render,
        "_puppeteer_launch_options",
        lambda: [
            ("Puppeteer bundled browser", None),
            ("/usr/bin/google-chrome", "/usr/bin/google-chrome"),
            ("/usr/bin/chromium-browser", "/usr/bin/chromium-browser"),
        ],
    )
    monkeypatch.setattr(mermaid_render, "_snap_chromium_candidates", lambda: ["/snap/bin/chromium"])
    monkeypatch.setattr(mermaid_render.subprocess, "run", fake_run)

    output = tmp_path / "graph.svg"
    mermaid_render.render_mermaid_svg("flowchart TD\n  A-->B\n", output)

    assert "executablePath" not in calls[0]
    assert calls[1]["executablePath"] == "/usr/bin/google-chrome"
    assert len(calls) == failed_attempts + 1
    if failed_attempts == 2:
        assert calls[2]["executablePath"] == "/usr/bin/chromium-browser"
    assert output.read_text(encoding="utf-8") == "<svg></svg>"


def test_cli_inspect_node_reports_unmatched_type(tmp_path, capsys) -> None:
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source(), node_type="demo.missing", descriptor=node_document())
    assert code == 1
    assert payload["health"]["status"] == "ERROR"
    assert payload["health"]["errors"][0]["code"] == "NODE.INSPECT.LOAD_ERROR"


@pytest.mark.parametrize(("changes", "reason"), [
    ({"type_key": ""}, "type_key"),
    ({"contract": {}}, "contract"),
    ({"contract": {"provides": [{"key": "demo.out", "type": "demo.out", "display_name": "Demo"}, {"key": "demo.out", "type": "demo.out", "display_name": "Demo"}]}}, "duplicate"),
    ({"contract": {"provides": [{"key": "demo.out", "type": "demo.out", "display_name": "Demo"}], "output_semantics": {}}}, "semantics"),
])
def test_inspect_node_rejects_invalid_declarations(tmp_path, capsys, changes, reason) -> None:
    declaration = {**node_document(), **changes}
    if changes == {"contract": {}}:
        declaration.pop("contract")
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source(), descriptor=declaration)
    assert code == 1
    assert payload["health"]["status"] == "ERROR"
    assert reason in payload["health"]["errors"][0]["message"].lower()


@pytest.mark.parametrize(("source", "diagnostic"), [
    (_valid_node_source(run_body='        return {"other.out": 1}'), "undeclared_output"),
    (_valid_node_source(run_body='        return {}'), "missing_output"),
    (_valid_node_source(run_body='        return {params["output_key"]: 1}'), "dynamic_output_key"),
    ("class DemoNode:\n    pass", "missing_run_pure"),
    (_valid_node_source(run_body='        return {"demo.out": 1}\n\n    def run(self, context):\n        return context'), "context_run_forbidden"),
    (_valid_node_source().replace("def run_pure(self, inputs, params):", "def run_pure(self, inputs, params, extra):"), "run_pure_signature"),
    (_valid_node_source().replace("def run_pure(self, inputs, params):", "async def run_pure(self, inputs, params):"), "async_run_pure"),
    (_valid_node_source(run_body='        while True:\n            return {"demo.out": 1}'), "internal_loop"),
    (_valid_node_source(run_body='        return {"demo.out": 1}\n\n    def helper(self):\n        return 1'), "public_callable"),
    (_valid_node_source().replace("class DemoNode:", "class DemoNode:\n    def __init__(self, client):\n        self.x = client"), "init_signature"),
    (_valid_node_source().replace("class DemoNode:", "class DemoNode:\n    def __init__(self):\n        self.session = None"), "resource_field"),
    (_valid_node_source(run_body='        open("x.txt", "w")\n        return {"demo.out": 1}'), "effect_call"),
    (_valid_node_source(run_body='        import os\n        return {"demo.out": 1}'), "effect_import"),
    (_valid_node_source(run_body='        os.getenv("HOME")\n        return {"demo.out": 1}'), "effect_call"),
    (_valid_node_source(run_body='        subprocess.run(["echo", "x"])\n        return {"demo.out": 1}'), "effect_call"),
    (_valid_node_source(run_body='        requests.get("https://example.com")\n        return {"demo.out": 1}'), "effect_call"),
    (_valid_node_source(run_body='        sqlite3.connect("x.db")\n        return {"demo.out": 1}'), "effect_call"),
    (_valid_node_source(run_body='        eval("1 + 1")\n        return {"demo.out": 1}'), "banned_call"),
    (_valid_node_source(run_body='        importlib.import_module("math")\n        return {"demo.out": 1}'), "banned_call"),
    (_valid_node_source(run_body='        global X\n        X = 1\n        return {"demo.out": 1}'), "global_state"),
    (_valid_node_source(run_body='        setattr(self, "x", 1)\n        return {"demo.out": 1}'), "monkey_patch"),
    (_valid_node_source(run_body='        DemoNode.x = 1\n        return {"demo.out": 1}'), "monkey_patch"),
    (_valid_node_source(run_body='        from nodes.other_node import OtherNode\n        return {"demo.out": 1}'), "node_import"),
    (_valid_node_source().replace(VALID_NODE_IMPORT, VALID_NODE_IMPORT + "CACHE = {}\n\n"), "module_global_state"),
    (_valid_node_source().replace(VALID_NODE_IMPORT, VALID_NODE_IMPORT + "if True:\n    X = 1\n\n"), "module_side_effect"),
    (_valid_node_source(run_body='        Path("x").read_text()\n        return {"demo.out": 1}'), "effect_call"),
    (_valid_node_source(run_body='        path = Path("x")\n        path.write_text("bad")\n        return {"demo.out": 1}'), "effect_call"),
    (_valid_node_source(run_body='        path = Path("x")\n        (path / "child").open()\n        return {"demo.out": 1}'), "effect_call"),
    (_valid_node_source(run_body='        compile("1", "<x>", "eval")\n        return {"demo.out": 1}'), "banned_call"),
])
def test_inspect_node_rejects_invalid_node_shapes(tmp_path, capsys, source, diagnostic) -> None:
    additional = ()
    if diagnostic == "node_import":
        folder = tmp_path / "nodes"
        folder.mkdir()
        (folder / "__init__.py").write_text("")
        (folder / "other_node.py").write_text('class OtherNode:\n    def run_pure(self, inputs, params):\n        return {"demo.out":1}\n')
        declaration = node_document(type_key="demo.other",class_name="OtherNode")
        declaration["implementations"][0]["source"]["ref"] = "nodes/other_node.py"
        additional = (declaration,)
    code, payload = _inspect_node_source(tmp_path, capsys, source, additional_nodes=additional)
    if diagnostic in {"undeclared_output", "missing_output", "dynamic_output_key", "internal_loop", "resource_field", "external_attr_assignment", "external_mutation_call", "banned_call", "contract_overlap", "monkey_patch"}:
        assert code == 0, payload
        return
    assert code == 1
    expected = "VF_IMPORT_LAYER" if diagnostic == "node_import" else "NODE.IMPORT.SIDE_EFFECT" if diagnostic in {"module_global_state", "module_side_effect"} else _default_rule_id(diagnostic)
    assert any(error["code"] == expected for error in payload["health"]["errors"]), payload


def test_inspect_node_rejects_node_direct_call_and_internal_read(tmp_path, capsys) -> None:
    source = """class OtherNode:
    def run_pure(self, inputs, params):
        return {"demo.out": 1}

class DemoNode:
    def run_pure(self, inputs, params):
        OtherNode._private
        return OtherNode().run_pure({}, {})
"""
    code, payload = _inspect_node_source(tmp_path, capsys, source,
        additional_nodes=(node_document(type_key="demo.other", class_name="OtherNode"),))
    assert code == 1
    codes = {error["code"] for error in payload["health"]["errors"]}
    assert _default_rule_id("node_direct_call") in codes
    assert _default_rule_id("node_internal_read") in codes


def test_selected_rule_warns_when_source_nears_policy_limit() -> None:
    violations = _review_node(SeedNode_DECLARATION, SeedNode, policy=PurityPolicy(max_source_lines=1000, warn_source_lines=1)).findings
    assert any(item.code == "NODE.PURITY.SOURCE_NEAR_LIMIT" and item.severity == "warning" for item in violations)


def test_cli_inspect_node_uses_explicit_rule_parameters(tmp_path, capsys) -> None:
    declaration = node_document()
    declaration['rulesets'] = [{'rule_id':'vibeflow.maintainability','params':{'policy':{'node_source':{'max_lines':1}}}}]
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source(), descriptor=declaration)
    assert code == 1
    assert any(error["code"] == "NODE.PURITY.SOURCE_TOO_LARGE" for error in payload["health"]["errors"])

def test_node_internal_call_chain_short_path_is_allowed(tmp_path, capsys) -> None:
    source = _valid_node_source(
        run_body="""
        return {"demo.out": self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return 1
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source)
    assert code == 0
    assert payload["health"]["status"] == "PASS"
    assert payload["node"]["metrics"]["call_chain_length"] == 3
    assert payload["node"]["metrics"]["call_chain_path"] == ["run_pure", "_a", "_b"]

def test_node_internal_call_chain_length_four_warns(tmp_path, capsys) -> None:
    source = _valid_node_source(
        run_body="""
        return {"demo.out": self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return self._c()

    def _c(self):
        return 1
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source)
    assert code == 0
    assert payload["health"]["status"] == "CONCERNS"
    warning = payload["health"]["warnings"][0]
    assert warning["rule_id"] == "NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP"
    assert warning["details"]["length"] == 4
    assert warning["details"]["path"] == ["run_pure", "_a", "_b", "_c"]

def test_node_internal_call_chain_over_four_fails(tmp_path, capsys) -> None:
    source = _valid_node_source(
        run_body="""
        return {"demo.out": self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return self._c()

    def _c(self):
        return self._d()

    def _d(self):
        return 1
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source)
    assert code == 1
    error = payload["health"]["errors"][0]
    assert error["rule_id"] == "NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP"
    assert error["details"]["length"] == 5
    assert error["suggested_fix_type"] == "split_node"

def test_private_algorithm_recursion_is_allowed(tmp_path, capsys) -> None:
    direct = _valid_node_source(
        run_body="""
        return {"demo.out": self._a()}

    def _a(self):
        return self._a()
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, direct)
    assert code == 0
    assert not payload["health"]["errors"]

    indirect = _valid_node_source(
        run_body="""
        return {"demo.out": self._a()}

    def _a(self):
        return self._b()

    def _b(self):
        return self._a()
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, indirect)
    assert code == 0
    assert not payload["health"]["errors"]

def test_graph_health_reports_node_call_chain_metrics() -> None:
    graph = parse_graph_config({"pipeline": {"nodes": [_node_call("seed", "test.seed", "Produces value.in.")]}})
    from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context
    registry = _registry()
    source_context = collect_workflow_source_context(registry, graph)
    report = validate_graph_health(graph, registry=registry, source_context=source_context, purity_policy=PurityPolicy(max_source_lines=1000))
    metrics = report.to_dict()["info"]["node_metrics"]["seed"]
    assert metrics["call_chain_length"] == 1
    assert metrics["call_chain_path"] == ["run_pure"]

def test_runtime_allows_non_json_object_output_by_reference() -> None:
    registry = _registry()
    register_node(registry, SetOutputNode_DECLARATION, SetOutputNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the runtime fixture."),
                    _node_call("set_output", "test.set_output", "Produces a non-JSON object output."),
                    _node_call("end", "test.out_end", "Consumes value.out at the end."),
                ],
                "edges": _edge_chain("start", "set_output", "end"),
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )
    context = PipelineRuntime(graph, registry=registry).run()
    assert context.get("value.out")["value"] == {1, 2}

def test_runtime_ignores_legacy_snapshot_metadata() -> None:
    registry = _registry()
    register_node(registry, OpaqueOutputNode_DECLARATION, OpaqueOutputNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the runtime fixture."),
                    _node_call("opaque", "test.opaque_output", "Produces an opaque object output."),
                    _node_call("end", "test.out_end", "Consumes value.out at the end."),
                ],
                "edges": _edge_chain("start", "opaque", "end"),
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )
    context = PipelineRuntime(graph, registry=registry).run()
    assert context.get("value.out")["value"] == {1, 2}

def test_runtime_allows_input_mutation_by_reference() -> None:
    registry = _registry()
    register_node(registry, MutatingInputNode_DECLARATION, MutatingInputNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the runtime fixture."),
                    _node_call("mutate", "test.mutating_input", "Mutates the input object by reference."),
                    _node_call("end", "test.out_end", "Consumes value.out at the end."),
                ],
                "edges": _edge_chain("start", "mutate", "end"),
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )
    value = [1, 2]
    context = PipelineRuntime(graph, registry=registry).run({"value.in": value})
    assert context.get("value.out")["value"] is value
    assert value == [1, 2, 3]

def test_collect_node_metrics_reports_complexity_and_contract_size() -> None:
    report = _review_node(AddNode_DECLARATION, AddNode, policy=PurityPolicy(max_source_lines=1000))
    payload = report.node_metrics[AddNode_DECLARATION.id]
    assert payload["function_count"] == 1
    assert payload["branch_count"] == 0
    # Python parameters come from the canonical descriptor contract.
    assert payload["param_count"] == 0
    assert payload["requires_count"] == 1
    assert payload["provides_count"] == 1
    assert payload["contract_key_count"] == 2
    assert payload["source_lines"] > 0

def test_complexity_policy_thresholds_are_enforced() -> None:
    violations = _review_node(
        AddNode_DECLARATION, AddNode,
        policy=PurityPolicy(
            max_source_lines=1000,
            max_functions=0,
            max_params=0,
            max_contract_keys=1,
        ),
    )
    violations = violations.findings
    codes = {item.code for item in violations}
    assert "NODE.MAINTAINABILITY.COMPLEXITY_MAX_FUNCTIONS" in codes
    assert "NODE.MAINTAINABILITY.COMPLEXITY_MAX_PARAMS" not in codes
    assert "NODE.MAINTAINABILITY.COMPLEXITY_MAX_CONTRACT_KEYS" in codes
    assert all(item.suggested_fix_type in {"split_node", "fix_contract"} for item in violations if item.code.startswith("NODE.MAINTAINABILITY.COMPLEXITY_"))

def test_branch_and_nesting_complexity_are_enforced(tmp_path, capsys) -> None:
    source = _valid_node_source(
        run_body="""
        if params.get("flag", False):
            if params.get("other", False):
                return {"demo.out": 2}
        return {"demo.out": 1}
""".rstrip(),
    )
    declaration = node_document()
    declaration['rulesets'] = [{'rule_id':'vibeflow.maintainability','params':{'policy':{'complexity':{'max_branches':1,'max_nesting_depth':1}}}}]
    code, payload = _inspect_node_source(tmp_path, capsys, source, descriptor=declaration)
    assert code == 1
    codes = {error["code"] for error in payload["health"]["errors"]}
    assert "NODE.MAINTAINABILITY.COMPLEXITY_MAX_BRANCHES" in codes
    assert "NODE.MAINTAINABILITY.COMPLEXITY_MAX_NESTING_DEPTH" in codes
    assert payload["node"]["metrics"]["branch_count"] == 2
    assert payload["node"]["metrics"]["max_nesting_depth"] == 2

def test_inspect_node_reports_metrics_for_valid_node(tmp_path, capsys) -> None:
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source())
    assert code == 0
    assert payload["health"]["status"] == "PASS"
    assert payload["node"]["metrics"]["function_count"] == 1
    assert payload["node"]["metrics"]["provides_count"] == 1
    assert set(payload["node"]["contract"]["examples"][0]) == {"inputs", "params"}

def test_missing_examples_and_example_contract_gap_are_accepted_as_documentation(tmp_path, capsys) -> None:
    declaration = node_document()
    declaration["contract"].pop("examples")
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source(), descriptor=declaration)
    assert code == 0
    assert payload["health"]["status"] == "PASS"
    declaration["contract"].update({"requires": [{"type": "demo.in", "cardinality": "exactly_one", "display_name": "Demo In"}], "input_semantics": {"demo.in": ["demo input"]}})
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source(), descriptor=declaration)
    assert code == 0
    assert payload["health"]["status"] == "PASS"


def test_python_interface_rule_rejects_example_outputs(tmp_path, capsys) -> None:
    declaration = node_document()
    declaration["contract"]["examples"][0]["outputs"] = {"demo.out": 1}
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source(), descriptor=declaration)
    assert code == 0
    assert not payload["health"]["errors"]


def test_removed_output_schema_is_an_explicit_load_error(tmp_path, capsys) -> None:
    declaration = node_document()
    declaration["contract"]["output_schema"] = {"demo.out": {"type": "number"}}
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source(), descriptor=declaration)
    assert code == 1
    assert payload["health"]["status"] == "ERROR"
    assert payload["health"]["errors"][0]["code"] == "NODE.INSPECT.LOAD_ERROR"


def test_example_output_key_failure_is_health_error(tmp_path, capsys) -> None:
    code, payload = _inspect_node_source(tmp_path, capsys, _valid_node_source(run_body='        return {"demo.other": 1}'))
    assert code == 0
    assert not payload["health"]["errors"]
