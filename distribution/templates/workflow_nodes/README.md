<!-- vibeflow-directory-purpose -->
# Workflow and port nodes

Python: copy `nodes.py` into a project module and explicitly include `resources`
in your Plugin. JavaScript: copy `nodes.mjs` and the release-generated
`interfaces.mjs`, import `resources`, and explicitly contribute them. The SDK
import is the normal project `@vibeflow/plugin` alias.

These are fixed ordinary SDK declarations, with example data types and selected
Rules. Change the contracts to your business types. Call uses target alias
`worker`; update both the implementation and its Rule action if that changes.
`Call` returns immediately after registration; `CallAndWait` additionally waits
for real completion. Add `allow_background: true` to a Call's config only when
accepting responsibility for that background instance. Port nodes require a
host-provided `vibeflow.port`; coordination nodes require a connected host.

Add explicit start/end terminals around these nodes and select
`vibeflow.capability.restrict` at graph scope. Shapes/colors can be changed
without granting or removing an operation.
