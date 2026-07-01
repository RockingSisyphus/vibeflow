# VibeFlow Strict Flowchart Redesign

This document records the target redesign for VibeFlow (`vibeflow`) as a strict
standard-flowchart runtime for human-AI collaborative development.

## Goal

VibeFlow must enforce an explicit architecture contract, not merely suggest
good structure. Every node must declare its standard flowchart role, every path
must be explainable by the registered flow, and any drift must fail strict
checks.

The redesign removes bespoke `boundary` and loop-registration concepts. Their
responsibilities are represented by standard flowchart node kinds and conditional
routing.

## Required Node Identity

Each node must declare `NodeInfo.flow_kind`. This field is mandatory and has no
default. Missing, empty, or unknown values are hard errors.

`NodeInfo.category` remains a domain/business category. It is not flowchart
semantics.

Allowed `flow_kind` values:

| flow_kind | Flowchart role | Kernel meaning |
| --- | --- | --- |
| `terminal` | Start / End | Flow entry, flow exit, initial input, final output |
| `process` | Process | Normal self-maintained computation node |
| `decision` | Decision | A process node that may route outputs conditionally |
| `io` | Input / Output | Program input/output adaptation |
| `predefined` | Predefined process / Subroutine | Declared subflow or nodeset wrapper |
| `data_store` | Database / Data store | File, database, cache, or state-store interaction |
| `document` | Document | Document read, generation, or transformation |
| `preparation` | Preparation / Initialization | Defaults, parameters, and setup |

Suggested `NodeInfo` shape:

```python
@dataclass(frozen=True)
class NodeInfo:
    type_key: str
    display_name: str
    category: str
    description: str
    version: str
    flow_kind: str
    purity: str = "pure"
    author: str | None = None
    tags: tuple[str, ...] = ()
    external: bool = False
```

## Strict Node Rules

All nodes must pass identity, contract, interface, topology, and traceability
checks.

Additional rules by kind:

| flow_kind | Required behavior |
| --- | --- |
| `terminal` | Must model start/end responsibility and stay thin. |
| `process` | Must pass normal self-maintained source quality checks. |
| `decision` | Must output a routing field and may conditionally activate outgoing edges. |
| `io` | Must model input/output adaptation instead of hidden business logic. |
| `predefined` | Must represent a declared subflow/nodeset-style unit. |
| `data_store` | Must model storage interaction responsibility. |
| `document` | Must model document interaction responsibility. |
| `preparation` | Must model setup/default/initialization responsibility. |

`NodeInfo.external=True` marks third-party or externally maintained code. It is
not a flowchart kind and does not change graph shape. The kernel still validates
`NODE_INFO`, `NODE_CONTRACT`, `requires`, `provides`, routing, graph placement,
and runtime trace. It only skips source-quality checks for code not owned by the
project.

## Conditional Routing

`decision` is a normal process node with route outputs. It is not a special loop
construct.

Outgoing edges may declare `when`:

```jsonc
{
  "source": "classify",
  "target": "retry",
  "when": "route == 'retry'"
}
```

First-pass `when` expressions should stay deliberately small:

- `name == 'value'`
- `name != 'value'`
- `flag == true`
- `flag == false`

No Python `eval`, general expression language, or plugin DSL is required for the
first implementation.

## Loop Rule

The kernel must remove explicit loop registration:

- remove `pipeline.loops`
- remove `LoopSpec`
- remove `max_iterations`
- remove edge `max_executions`
- remove loop-specific runtime trace fields

Cycles are legal only when each cycle contains a `decision` node. External code
does not legalize a cycle by itself; an externally implemented router must still
declare `flow_kind="decision"` and `external=True`. Runtime still needs
`max_steps` as a safety guard, but `max_steps` is execution protection, not
architecture meaning.

## Boundary Removal

`boundary` is removed from the public model. Its historical responsibilities are
covered by standard flowchart nodes:

| Old boundary responsibility | New flow_kind |
| --- | --- |
| External input | `terminal` start plus `io` input node |
| Final output | `io` output node plus `terminal` end |
| Files, databases, caches | `data_store` |
| Document reads/writes | `document` |
| API or third-party calls | `io`, `data_store`, `document`, or `external=True` implementation flag |
| Environment/setup | `preparation` |

Configs containing `boundary` must fail. Runtime must not have boundary lifecycle
hooks or boundary trace events.

## Architecture Contract

The existing `pipeline` and `nodesets` config is the architecture contract. Do
not add a parallel `architecture_flow`; that would duplicate the graph and create
drift between two sources of truth.

Before implementation, AI-authored design can register planned nodes and
nodesets directly in config:

```jsonc
{
  "nodesets": {
    "classify_flow": {
      "status": "planned",
      "flow_kind": "predefined"
    }
  },
  "pipeline": {
    "nodes": [
      {"name": "start", "status": "planned", "flow_kind": "terminal"},
      {"name": "classify", "status": "planned", "flow_kind": "decision"}
    ],
    "edges": [
      {"from": "start", "to": "classify"}
    ]
  }
}
```

Rules:

- `status` is `planned` or `implemented`; default is `implemented`.
- Planned pipeline nodes must declare config `flow_kind`.
- Implemented pipeline nodes must not declare config `flow_kind`; their kind comes
  from registered `NodeInfo.flow_kind`.
- Planned nodes and nodesets are valid for design/health visualization but cannot
  run.
- An implemented nodeset cannot contain planned children.
- Mermaid must render planned nodes/nodesets with flowchart shapes and a distinct
  planned marker.
- Conditional routes and cycles still follow the same `when` and routing-node
  rules.

## Mermaid Output

Mermaid rendering should use `flow_kind` as the shape source:

| flow_kind | Mermaid shape |
| --- | --- |
| `terminal` | `([label])` |
| `process` | `[label]` |
| `decision` | `{label}` |
| `io` | `[/label/]` |
| `predefined` | `[[label]]` |
| `data_store` | `[(label)]` |
| `document` | document-style shape or class |
| `preparation` | hexagon-style shape or class |

Edges should display `when`. Loop and boundary labels should disappear.

## Runtime Shape

Runtime should move from DAG plus declared loops to a step-based flow executor:

1. Find runnable nodes.
2. Execute one node.
3. Store outputs.
4. Activate outgoing edges whose `when` is absent or true.
5. Allow repeated node execution.
6. Stop on end terminal, no runnable nodes, failure, or `max_steps`.

Trace should record:

- `exec_order`
- `edge_executions`
- `step_count`
- `node_runs`
- `stop_reason`
- `events`

Trace should remove:

- `loop_iterations`
- `loop_stop_reasons`
- `loop_orders`
- `boundary_events`

## Strict Error Codes

The following conditions must fail strict runs:

| Code | Meaning |
| --- | --- |
| `NODE.FLOW_KIND.MISSING` | Node does not declare `flow_kind` |
| `NODE.FLOW_KIND.INVALID` | Node declares an unknown kind |
| `NODE.DECISION.MISSING_ROUTE_OUTPUT` | Decision node has no route output |
| `GRAPH.DECISION.MISSING_EDGE_CONDITION` | Decision branch edge lacks `when` |
| `GRAPH.CYCLE.MISSING_ROUTER` | Cycle lacks `decision` |
| `NODE.EXTERNAL.INVALID` | `NodeInfo.external` is not boolean |
| `CONFIG.BOUNDARY.REMOVED` | Config still uses `boundary` |
| `CONFIG.LOOPS.REMOVED` | Config still uses `pipeline.loops` |
| `CONFIG.LOOP_LIMITS.REMOVED` | Config still uses loop count fields |
| `GRAPH.PLANNED.MISSING_FLOW_KIND` | Planned config node lacks `flow_kind` |
| `GRAPH.PLANNED.IMPLEMENTED_HAS_CONFIG_FLOW_KIND` | Implemented config node declares duplicate `flow_kind` |
| `GRAPH.PLANNED.NODE` | Planned node exists in design graph |
| `GRAPH.PLANNED.NODESET` | Planned nodeset exists in design graph |
| `GRAPH.PLANNED.PARENT_HAS_PLANNED_CHILD` | Implemented nodeset contains planned descendants |
| `GRAPH.PLANNED.NODE_IN_RUN` | Runtime was asked to execute planned graph content |

## Implementation Phases

### Phase 1: Mandatory Node Identity

- make `NodeInfo.flow_kind` mandatory
- add allowed kind constants
- add `external: bool`
- validate flow kind strictly
- validate `decision` route output
- validate `NodeInfo.external` is boolean
- skip source-quality checks only for `external=True`

### Phase 2: Remove Boundary and Declared Loops

- reject `boundary`
- reject `pipeline.loops`
- reject `max_iterations` and `max_executions`
- remove `LoopSpec`
- allow cycles only when routed by `decision`
- replace loop runtime with `max_steps`

### Phase 3: Architecture Contract

- treat existing `pipeline` and `nodesets` as the contract
- add `status: planned | implemented`
- allow planned nodes/nodesets to declare design-time `flow_kind`
- reject config `flow_kind` on implemented nodes
- warn on planned design content during health checks
- refuse planned content at runtime
- render planned content in Mermaid

The shortest correct path is to land Phase 1 first, then remove old semantics,
then let the existing topology config act as the architecture contract.
