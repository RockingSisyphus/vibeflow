# Minimal JavaScript AOT project

The workflow is `input boundary -> business process -> output boundary`, with explicit start and end terminals. Replace the pass-through under `BUSINESS CODE` in `nodes/process_payload.ts`, then update the `defineNode` contract when the data relationship changes.

`plugins/code_plugin.ts` exports the fixed plugin selected by `configs/main.jsonc`. Declare additional resources with `@vibeflow/plugin`, add them to that plugin, and select their Rulesets explicitly. For split implementations and default colors or shapes, read `kernel/docs/user/multifile-resources.md` from the distribution root.

`scripts/workflow_execution_probe.mjs` runs the built Node module and writes its report under `run_artifacts/`. The root layout Rule declares that output directory so the project remains reviewable after executing the probe.
