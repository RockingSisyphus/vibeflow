# ASCII Flowchart Renderer Plan

## Problem

The kernel currently emits Mermaid flowcharts. Recent Mermaid shape syntax fixed
the source model, but the user's available renderer does not support Mermaid
v11.3 shape syntax and renders every node as a rectangle.

Using Mermaid as an intermediate format also weakens the kernel's own contract:
the kernel already has a typed compiled graph with explicit flow edges and
`flow_kind`, so it should not depend on external Mermaid parser compatibility to
show a program flowchart.

## Research Summary

The local reference directory
`/home/rockingsisyphus/projects/opencodeMisc/plugins-mermaid-research` contains
three Mermaid-related plugins/packages:

- `opencode-mermaid-formatter`: thin OpenCode plugin around `mermaid2term`.
- `opencode-mermaid-renderer`: thin OpenCode plugin around `beautiful-mermaid`.
- `chat-mermaid`: SVG/chat rendering direction, not useful for kernel ASCII.

Both useful plugins are wrappers. Their real rendering code lives in dependencies:

- `mermaid2term`: smaller MIT package, parses Mermaid and renders terminal ASCII
  / Unicode flowcharts. It supports box drawing, edge labels, simple layout, and
  back edges, but its parser targets older Mermaid shape syntax.
- `beautiful-mermaid`: MIT package with broader diagram support and Dagre-based
  layout. It is much larger and pulls JS layout dependencies.

Conclusion: do not copy the OpenCode plugin wholesale. The shortest robust path
is to port the small useful ideas from `mermaid2term` into a native Python ASCII
renderer that consumes the kernel's `GraphConfig` and `CompiledGraph` directly.

## Target Behavior

Add a first-class ASCII flowchart export:

- Render from kernel topology objects, not from Mermaid source.
- Use explicit flow edges only (`compiled.effective_edges`).
- Preserve `when` labels on conditional edges.
- Preserve loops/back edges visually.
- Render standard flowchart roles with distinguishable ASCII/Unicode shapes.
- Mark planned nodes and health warnings/errors in text, not color.
- Support collapsed and expanded nodesets.
- Keep Mermaid export as compatibility/debug output for now.

## Shape Mapping

The ASCII renderer should map `flow_kind` directly:

| flow_kind | ASCII shape intent |
| --- | --- |
| `terminal` | rounded terminal / start-end capsule |
| `process` | rectangle |
| `decision` | diamond-like decision marker |
| `io` | parallelogram-like input/output box |
| `predefined` | subroutine box with double side bars |
| `data_store` | cylinder-like data store |
| `document` | document box with wavy bottom marker |
| `preparation` | hexagon-like preparation marker |

`NodeInfo.external=True` must not change the flowchart shape. It may add an
`external` text marker in the node label.

## Minimal Renderer Design

Add `src/topology_kernel/ascii_flowchart.py`.

Public function:

```python
def export_ascii_flowchart(
    graph: GraphConfig,
    *,
    expand_nodesets: bool = False,
    compiled: CompiledGraph | None = None,
    registry: NodeRegistry | None = None,
    health_report: object | None = None,
    show_contract: bool = True,
    show_semantics: bool = True,
    show_findings: bool = True,
) -> str: ...
```

Implementation outline:

1. Build render nodes from `graph.nodes` with `compiled.flow_kinds`.
2. Build render edges from `compiled.effective_edges`.
3. Assign simple top-down layers from terminal starts over explicit flow edges.
4. Detect back edges as edges whose target layer is less than or equal to source
   layer.
5. Draw nodes on a text canvas with fixed gaps.
6. Draw normal edges vertically or with simple elbow connectors.
7. Draw back edges around the side.
8. Append a compact findings section under the diagram.

This is intentionally smaller than Dagre. The kernel needs readable program
flowcharts, not a general-purpose graph layout engine.

## Output Artifacts and CLI

Runtime artifacts should include both formats for now:

- `graph.txt`: ASCII flowchart, primary human-readable artifact.
- `graph.mmd`: Mermaid compatibility artifact, retained for now.

CLI additions:

- Add `export-ascii` command with the same config/expand/contract/semantics flags
  as `export-mermaid`.
- Keep `export-mermaid` unchanged except tests may stop relying on it as the main
  visual output.

Integration sandbox:

- Generate `reports/ascii/*.txt` alongside `reports/mermaid/*.mmd`.
- Include `graph.txt` in run artifact checks.
- Show the comprehensive flowchart from ASCII output.

## Tests

Add or update tests to cover:

- `export_ascii_flowchart()` exists in public/devtools exports.
- Every standard `flow_kind` has a distinguishable ASCII marker.
- Decision edges show `when` labels.
- Back edges/loops are visible.
- Planned nodes show a planned marker.
- Health findings appear without creating fake graph nodes.
- `run_checked()` writes `graph.txt`.
- Sandbox comprehensive case generates ASCII output and still passes.

## Non-Goals

- Do not add a Node/JS runtime dependency.
- Do not copy the OpenCode plugin as-is; it is a chat text transformer, not a
  kernel renderer.
- Do not implement every Mermaid diagram type.
- Do not remove Mermaid export in this pass.

## Verification

Run:

```bash
python -m compileall src/topology_kernel tests/unit examples/integration_sandbox/project examples/integration_sandbox/run_all.py
pytest -q
python examples/integration_sandbox/run_all.py
```

Then inspect `examples/integration_sandbox/reports/ascii/comprehensive_flowchart.txt`.
