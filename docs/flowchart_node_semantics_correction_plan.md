# VibeFlow Flowchart Node Semantics Correction Plan

This document records the next correction pass for VibeFlow's strict flowchart model.
The goal is to keep standard flowchart semantics, runtime boundaries, and source
quality policy separate.

## Problems Found

### `terminal` and `io` are mixed

Current health/runtime logic accepts both `terminal` and `io` as graph start/end
nodes. This is too loose.

Standard flowcharts use:

- `terminal`: start/end of a program or subflow
- `io`: input/output action inside the flow

`io` must not replace `terminal`.

Correct shape:

```text
terminal start -> io input -> process... -> io output -> terminal end
```

### Mermaid `io` shape is unstable

Current Mermaid generation emits an `io` node as:

```mermaid
node[/"label"/]
```

Some renderers display this as a normal process rectangle and include `/"..."/`
in the visible text. The generator must emit a stable parallelogram form.

### `external_dependency` is not a flowchart kind

`external_dependency` is currently a `flow_kind`. That is wrong: it is not a
standard flowchart shape. It describes whether the code inside a node is owned by
this project and should be source-quality checked.

External dependency status should be a source-quality policy flag, not a graph
role.

### External dependency is too close to `decision`

Current design lets `external_dependency` behave like a routing node:

- it may be required to provide a route-like output
- it may make cycles legal

This is too broad. A wrapped third-party function is not automatically a
decision. If an external node routes flow, it must declare `flow_kind="decision"`.

### `document` has no dedicated rendering

`flow_kind="document"` exists but falls back to a normal process rectangle in
Mermaid. It should render as a document-like node or at least with a dedicated
document style.

### `preparation` shape should remain explicit

Preparation should use the standard preparation/initialization shape, usually a
hexagon. Mermaid support must be kept explicit and tested.

## Target Semantics

### Flow kinds

Only standard flowchart roles remain in `FLOW_KINDS`:

- `terminal`
- `process`
- `decision`
- `io`
- `predefined`
- `data_store`
- `document`
- `preparation`

`external_dependency` is removed as a flow kind.

### External source-quality policy

Use a boolean node metadata field:

```python
NodeInfo.external: bool = False
```

Meaning:

- `external=False`: this project owns the node implementation; run full source
  quality checks.
- `external=True`: the node wraps external/third-party/not-owned code; skip
  source-quality checks only.

`external=True` does not change graph shape or routing behavior.

### Checks kept for external nodes

Even when `external=True`, the kernel still validates:

- `NODE_INFO`
- `NodeContract`
- `flow_kind`
- `requires` / `provides`
- examples shape
- graph placement
- route/`when` rules if `flow_kind="decision"`
- runtime traceability

### Checks skipped for external nodes

Only source maintainability checks are skipped:

- source size
- complexity
- banned imports
- call-chain purity
- architecture smells
- module-wide source quality scans

### Start/end rule

Each executable graph and implemented nodeset must have:

- at least one `terminal` start node with no incoming flow edge
- at least one `terminal` end node with no outgoing flow edge

`io` nodes cannot satisfy start/end requirements.

### Loop rule

Cycles are legal only when the explicit flow cycle contains a
`flow_kind="decision"` node.

`external=True` does not make a cycle legal. If an external dependency routes a
cycle, declare it as both:

```python
flow_kind="decision"
external=True
```

### Decision rule

Only `flow_kind="decision"` requires a route-like output and `when` labels on
outgoing branch edges.

`external=True` alone does not require a route output.

## Mermaid Target Shapes

| flow_kind | Shape |
| --- | --- |
| `terminal` | rounded/terminal |
| `process` | rectangle |
| `decision` | diamond |
| `io` | parallelogram |
| `predefined` | predefined process/subroutine |
| `data_store` | cylinder |
| `document` | document-like node or dedicated style |
| `preparation` | hexagon/preparation |

`external=True` may be shown as label text or a style marker, but it must not
change the flowchart shape.

## Implementation Plan

1. Update `NodeInfo` and flow-kind constants.
2. Move external source-quality skipping from `flow_kind` to `NodeInfo.external`.
3. Make decision validation apply only to `flow_kind="decision"`.
4. Make cycle/routing checks accept only `decision`.
5. Make health/runtime start/end checks accept only `terminal`.
6. Fix Mermaid `io`, add `document`, and keep `preparation` explicit.
7. Update sandbox configs to use terminal start/end around `io` nodes.
8. Add/adjust tests for start/end, external policy, loops, and Mermaid shapes.
9. Run unit tests and integration sandbox verification.
