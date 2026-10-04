# Minimal JavaScript AOT project

The workflow is `input boundary -> business process -> output boundary`, with explicit start and end terminals. Replace the pass-through under `BUSINESS CODE` in `nodes/process_payload.ts`, then update the `defineNode` contract when the data relationship changes.

`plugins/code_plugin.ts` exports the fixed plugin selected by `configs/main.jsonc`. Declare additional resources with `@vibeflow/plugin`, add them to that plugin, and select their Rulesets explicitly. For split implementations and default colors or shapes, read `kernel/docs/user/multifile-resources.md` from the distribution root.
