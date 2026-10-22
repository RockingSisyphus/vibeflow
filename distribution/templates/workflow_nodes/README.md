<!-- vibeflow-directory-purpose -->
# Workflow and port nodes

Python: copy `nodes.py` into `nodes/nodes.py`, and `protocol.py` into
`plugins/workflow_protocol/protocol.py`. Select that Plugin in the workflow's
`plugins` list. JavaScript: copy `nodes.mjs` into `nodes/nodes.mjs`; copy
`protocol.mjs` and the release-generated `interfaces.mjs` together into
`plugins/workflow_protocol/`, and select `protocol.mjs` as the Plugin entry.
The SDK import is the normal project `@vibeflow/plugin` alias. Keep protocol
initialization separate from business Node source so import rules inspect each
responsibility correctly.
The JavaScript implementation references are relative to the project root and
use `nodes/nodes.mjs`; update those references if you rename or move the file.

These are fixed ordinary SDK declarations, with example data types and selected
Rules. Change the contracts to your business types. Call requires `config.workflow` (`root`, `path`, optional `entry`) and `config.launch` (`command`, optional `cwd` and `env`). Kill requires `config.workflow` and an input instance ID. These values are supplied at each call; Rule actions do not repeat target declarations. Send/Receive accept optional `config.expected_workflows` for preview navigation.
`Call` returns immediately after registration; `CallAndWait` additionally waits
for real completion. Add `allow_background: true` to a Call's config only when
accepting responsibility for that background instance. Port nodes require a
host-provided `vibeflow.port`; coordination nodes require a connected host.

Add explicit start/end terminals around these nodes and select
`vibeflow.capability.restrict` at graph scope. Workflow operations use `flow_kind: "workflow-io"`. Call, Kill, Receive and Send share the notched-card shape (`notch-rect`), with gold, red, dark blue and light blue defaults respectively. `wait` awaits an instance's terminal state without replacing the main operation's color. Every Node can read its current instance ID with `context.workflow.self()` without a Capability declaration or Rule grant; there is no separate Self Node. Planned calls retain these colors and add a dashed outline at 60% opacity. Shapes/colors can be changed
without granting or removing an operation.
