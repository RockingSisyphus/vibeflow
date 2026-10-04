# Minimal Python Runtime project

The workflow is `input boundary -> business process -> output boundary`, with explicit start and end terminals. Replace the pass-through under `BUSINESS CODE` in `nodes/workflow_nodes.py`, then update the `@node` contract when the data relationship changes.

`plugins/code_plugin.py` exports the fixed plugin selected by `configs/main.jsonc`. Declare additional resources with `vibeflow.targets.python.sdk`, add them to that plugin, and select their Rulesets explicitly. For split implementations and default colors or shapes, read `kernel/docs/user/multifile-resources.md` from the distribution root.
