# Explicit Flow Edges Plan

This document records the next kernel tightening step: config edges are the only
program flow edges. The kernel must not infer control flow from
`requires`/`provides`.

## Goal

AI and humans must explicitly register the program flow in `pipeline.edges` and
nodeset-local `pipeline.edges`. The kernel should validate that registered flow
as a strict flowchart contract.

`requires` and `provides` remain data contracts. They can produce warnings when
data looks disconnected, but they must not create flow edges.

## Rules

### Flow Edges

- Only edges written in config are flow edges.
- Root `pipeline.edges` defines root flow.
- Each nodeset's own `pipeline.edges` defines that nodeset's internal flow.
- The compiler must not infer flow edges from `requires`/`provides`.
- Mermaid must default to rendering only explicit flow edges.
- Runtime must schedule by explicit flow edges, not by data availability alone.

### Data Contract Warnings

The kernel should keep `providers` and `consumers` maps for diagnostics.

Warn, but do not fail, when:

- a node `requires` a key that is not provided by an upstream flow predecessor or
  declared pipeline input;
- a node `provides` a key that is not required by a downstream flow successor or
  exported/finalized by the graph.

Suggested warning codes:

- `GRAPH.DATA.MISSING_UPSTREAM_PROVIDER`
- `GRAPH.DATA.UNCONSUMED_PROVIDER`

These are warnings because external inputs, terminal nodes, IO nodes, or future
config may intentionally supply/consume data outside local node-to-node flow.

### Strict Flowchart Health

For implemented executable graph content, strict flow shape is mandatory.

- Planned nodes may be disconnected because they are architecture placeholders.
- Non-planned nodes must not be orphaned.
- Every executable graph must have at least one start node.
- Every executable graph must have at least one end node.
- Every non-planned node must be reachable from a start node.
- Every non-planned node must be able to reach an end node.

Start/end nodes are standard terminal flowchart nodes:

- start: `terminal` node with no incoming flow edges;
- end: `terminal` node with no outgoing flow edges.

Suggested hard error codes:

- `GRAPH.FLOW.MISSING_START`
- `GRAPH.FLOW.MISSING_END`
- `GRAPH.FLOW.ORPHAN_NODE`
- `GRAPH.FLOW.UNREACHABLE_FROM_START`
- `GRAPH.FLOW.CANNOT_REACH_END`

### Cycles

Cycle checks operate only on explicit flow edges.

Every explicit flow cycle must contain at least one `decision` node.

Cycles without such a node fail with `GRAPH.CYCLE.MISSING_ROUTER`.

### Runtime

Runtime must execute the registered flow, not a guessed data graph.

- Initial ready nodes are start nodes.
- After a node runs, only its active outgoing flow edges enqueue next nodes.
- `when` is evaluated only on explicit flow edges.
- Before executing a node, runtime still checks that all `requires` keys are
  present.
- Missing required runtime data is a runtime error; health should usually warn
  about the same issue earlier.

### Mermaid

- Default Mermaid output renders explicit flow edges only.
- Data dependencies may be added later as an opt-in dashed overlay, but not in
  the default flowchart.
- Planned nodes should be visually obvious: colored fill, thick dashed border,
  and `PLANNED` in the label.
- Expanded nodeset rendering must not create misleading orphan wrapper nodes.

### Sandbox Updates

Valid sandbox configs must explicitly declare full flow edges and start/end
nodes.

Examples:

- linear: `start -> seed -> add -> multiply -> end`
- decision cycle:
  - `start -> increment -> done`
  - `done -- loop.done == false --> copy -> increment`
  - `done -- loop.done == true --> end`
- nodeset internals must include their own start/end and explicit edges.
- IO/data-store examples must connect data-store and IO nodes into one explicit
  flow, not leave them isolated.

Invalid sandbox configs should cover:

- orphan implemented node;
- missing start;
- missing end;
- unreachable node from start;
- node that cannot reach end;
- explicit cycle without a decision/external dependency;
- planned graph refused at runtime.

## Minimal Implementation Order

1. Change the compiler so explicit config edges are the only flow edges.
2. Keep data provider/consumer diagnostics as warnings.
3. Add strict flow health checks for start/end/reachability/orphans/cycles.
4. Change runtime scheduling to follow explicit flow edges.
5. Change Mermaid to render explicit flow edges by default and strengthen planned
   styling.
6. Update sandbox configs/nodes/tests.
7. Run full verification: compileall, unit tests, integration sandbox.
