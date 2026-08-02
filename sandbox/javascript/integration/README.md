# VibeFlow TypeScript Sandbox

This sandbox exercises the JavaScript/TypeScript AOT project format without
containing host-specific integration code.

Positive workflows:

- `project/configs/linear.jsonc` computes `(x + a) - b` with two TypeScript
  nodes importing the registered pure `sandbox.math` base_lib;
- `project/configs/fanout_join.jsonc` fans out into add/subtract branches and
  rejoins them with `join_policy: "all"`;
- `project/configs/edge_roles.jsonc` separates a transfer-only data edge from
  a schedule-only control edge and proves neither role leaks into the other;
- `project/configs/branch_join.jsonc` conditionally selects one branch and
  rejoins it with `join_policy: "any_active"`;
- `project/configs/nodeset.jsonc` computes `(x + a) - b` inside a reusable
  nodeset;
- `project/configs/nested_override.jsonc` applies a qualified config override
  to one of two sibling nested `math` nodes and proves it does not leak;
- `project/configs/nested_async.jsonc` nests two nodesets around a deferred
  result and a detached task, then verifies qualified task paths, cleanup
  timeout location, and successful reuse after cleanup failure;
- `project/configs/loop.jsonc` carries a number through a bounded three-step
  while loop;
- `project/configs/loop_stop_when.jsonc` stops from body data and collects each
  carried value;
- `project/configs/loop_max_failure.jsonc` verifies the stable bounded-loop
  failure when the stop condition cannot converge in time;
- `project/configs/async_capability.jsonc` combines a Promise node with a
  per-run injected `sandbox.storage` Capability. The execution-model case
  proves its serial suspend, deferred TaskPlan and Capability all use the JS
  event loop rather than a thread executor;
- `project/configs/optional_input.jsonc` adds an optional offset, treating an
  omitted `required: false` input as zero;
- `project/configs/detached.jsonc` checks detached cleanup and timeout behavior
  through a fake `sandbox.audit` Capability;
- `project/configs/port_math.jsonc` verifies the async
  `receive → TypeScript math node/base_lib → send` Port chain;
- `project/configs/host_extension.jsonc` selects the implemented
  `sandbox.math_host` at workflow scope and carries an unbundled planned Host
  Extension for architecture review. The runnable case verifies import/create
  side-effect freedom, explicit start/stop, idempotent stop, Capability
  injection, instance config, and manifest packaging;
- `project/configs/permanent_port_host.jsonc` combines an asynchronous Host
  Extension with an unbounded loop and the
  `receive → TypeScript math node/base_lib → send` Port path. The runner stops
  the host while the next receive is pending and verifies `VF_ABORTED` cleanup;
- `project/configs/browser_permanent_port_host.jsonc` runs that permanent Port
  topology in a real headless browser for both `web-app` and `esm-module`.
  Browser `window.message` inputs are routed into two isolated Host instances;
  the primary instance processes two values, reaches its third pending
  `receive`, and is cancelled by idempotent `stop()` with `VF_ABORTED`. The
  cases also reject import/create side effects and any `unhandledrejection`;
- `project/configs/runtime_node_failure.jsonc` and
  `project/configs/runtime_output_failure.jsonc` exercise the stable error ABI
  for node exceptions and output Schema failures.

The negative configs under `project/configs/negative/` each select one isolated
invalid node or workflow. In addition to direct dependency violations, they
exercise barrel, package alias and symlink paths, base_lib reverse imports,
undeclared external packages, package-root escapes and indirect Node builtins.
The source audit rejects dynamic code, module-level or discarded Promise work,
long-lived node listeners and mutable module state, with stable diagnostic
codes, owners and source locations. Completion mismatches, a suspending node or
a deferred TaskPlan inside a synchronous workflow remain covered as separate
execution-model failures.

The runner also verifies that the default synchronous ABI returns a plain,
non-thenable value immediately, while the explicit `runWorkflowAsync` ABI
returns a Promise and remains pending across a held suspending Capability. It
inspects the generated plan for `completion`, `schedule`, `executor` and
TaskPlan metadata, confirms JS uses `event_loop` rather than pretending to
spawn Python-style threads, and covers import side-effect freedom, repeated and concurrent
call isolation, input preflight, cancellation, trace modes and trace callback
errors, Capability isolation, declaration-file consumption under strict
TypeScript, source-map origins, deterministic manifests, atomic publication,
single-file bundling, and the `web-app` no-auto-start contract.

From the repository root, run the complete sandbox with:

```bash
PYTHONPATH=src python sandbox/javascript/integration/run_all.py
```

The runner copies the fixture to a temporary directory and runs `npm ci` there,
including the project-owned TypeScript/esbuild toolchain and Puppeteer. All
dependencies and build outputs are removed on exit. Pass `--keep-artifacts` to
retain the copied project, toolchain, browser driver, builds and report under
`sandbox/javascript/integration/.artifacts/`.

The official VibeFlow distribution contains a curated JavaScript example root
under `javascript_project/`; the repository-only integration sandbox is not
copied into the release.  The example root imports the colocated
`kernel/vibeflow-kernel.zip`, so it does not need a source checkout or an
installed Python package:

```bash
cd <release>/vibeflow-distribution
python run.py validate --config javascript_project/configs/linear.jsonc
python run.py build --config javascript_project/configs/linear.jsonc \
  --target node --profile single-esm --out-dir output/javascript
```

The complete 65-case integration runner, including its browser installation,
remains in this source repository.  The release example keeps its own locked
TypeScript/esbuild toolchain and does not share dependencies with the Python
example root.

The default runner and CI gate require the Puppeteer browser cases and do not
skip them. Use `--skip-browser` only for an explicitly reduced local run when
Puppeteer is unavailable. The runner builds the
positive and negative fixtures through VibeFlow's normal build API. The
`web-app` fixture only registers a button handler; importing its generated
module does not auto-run `runWorkflow()`. Reports are temporary by default;
with `--keep-artifacts`, stable JSON and Markdown summaries are written under
`.artifacts/reports/`.
