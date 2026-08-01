# Contributing to VibeFlow

This guide is for people changing the VibeFlow framework itself. If you are using VibeFlow to build a business project, start with `docs/developer_guide.md` instead.

## Framework Ground Rules

- Do not reintroduce removed public concepts such as `boundary`, `pipeline.loops`, `max_iterations`, edge `max_executions`, or edge `loop`.
- Keep `pipeline.edges` as the only source of executable control flow. `requires` and `provides` are strict key/type data contracts for inbox resolution, not scheduler edges.
- Keep `WorkflowPlan` and `BlockPlan` language-neutral and deterministic. They may contain frozen JSON values, contracts, routes, block references, and source references, but never Python classes, callables, arbitrary objects, or emitted source code.
- Treat the existing Python `ExecutionPlan` as a compatibility execution path. Its portable projection does not mean the Python runtime has already been replaced by an emitter.
- Keep node, `base_lib`, data-schema, Capability, and Host Extension descriptors statically readable. When a static descriptor and legacy Python registration coexist, they must agree.
- Treat `descriptors.host_extensions` as the availability catalog and workflow
  `host_extensions` as the active resource list. Planned Host Extensions belong
  in architecture output, never in bundles or lifecycle execution; the legacy
  `javascript.host_extensions` list is only a compatibility default.
- Keep generated JavaScript modules side-effect-free on import. Per-run state, traces, tasks, cancellation, and Capability wrappers must not leak through mutable module-level business state.
- Keep Capability implementations invocation-scoped and host-owned. A Capability contract or import audit is an explicit dependency boundary, not a security sandbox.
- Keep implemented `flow_kind` semantics owned by registered framework metadata, not duplicated in runnable config.
- Keep planned architecture non-runnable. Design-time placeholders may be visualized and warned about, but must not execute.
- Keep framework rules explainable through stable health findings: `rule_id`, severity, object identity, failure layer, details, and suggested fix type.
- Prefer policy/plugin extension points for project-specific semantics. Put only general framework invariants in core hard errors.

## Development Setup

Use Python 3.11 or newer.

```bash
python -m pip install -e .
```

## Required Checks

Run these before opening a pull request:

```bash
python -m compileall -q src tests examples
python -m pytest -q
PYTHONPATH=src python examples/integration_sandbox/run_all.py
PYTHONPATH=src python -m vibeflow quality-check --path .
```

If you touch side-effect scanning or purity checks, also run:

```bash
PYTHONPATH=src python -m vibeflow quality-check --path . --check-side-effects
```

If you touch the portable plan, descriptors, JS emitter, AOT builder, TypeScript dependency checks, runtime helpers, or AOT package resources, also run:

```bash
npm ci --prefix examples/js_aot_minimal/project
npm ci --prefix examples/typescript_sandbox/project
npm ci --prefix tools/mermaid-renderer
PYTHONPATH=src python examples/js_aot_minimal/run_e2e.py \
  --puppeteer-root tools/mermaid-renderer
PYTHONPATH=src python examples/typescript_sandbox/run_all.py \
  --puppeteer-root tools/mermaid-renderer
```

The minimal example is the quick real-project smoke test. The TypeScript sandbox is the broader conformance and stability suite: node/`base_lib` arithmetic, data transfer, edge roles, branches and joins, nodesets, loops, sync/async ABI, Port, per-run Capabilities, cancellation, trace/error behavior, completion mismatch, illegal imports, source maps, deterministic publication, and all shipped profiles. Do not use `--skip-browser` for release acceptance.

For packaging, CLI-build, embedded `.mjs` resource, or distribution-template changes, reproduce the release boundaries as CI does:

```bash
python -m build
# Install the wheel into an isolated virtual environment and verify:
#   importlib.resources files for aot/resources/toolchain_driver.mjs
#   importlib.resources files for aot/resources/runtime_helpers.mjs
#   vibeflow --help

python build_distribution.py --output /tmp/vibeflow-distribution-smoke
python /tmp/vibeflow-distribution-smoke/run.py build \
  --workspace examples/js_aot_minimal/vibeflow_config.jsonc \
  --config examples/js_aot_minimal/project/configs/greeting.jsonc \
  --target node \
  --profile single-esm \
  --out-dir /tmp/vibeflow-distribution-aot
# Import /tmp/vibeflow-distribution-aot/index.js with Node and call
# runWorkflow() with a fake example.clock Capability.
```

Use a fresh temporary output path for the smoke test. After it passes, `python build_distribution.py` rebuilds the repository-root distribution. Never hand-edit generated `vibeflow_distribution/`; change its source template, documentation, or `src/vibeflow` package and rebuild it.

## Documentation

- Keep `docs/kernel_target_vision.md` aligned with the long-term architecture and explicitly label compatibility paths or not-yet-shipped directions.
- Put Python project usage guidance in `docs/developer_guide.md`.
- Put shipped JS/TS descriptor, node ABI, Workflow ABI, Port, Capability, Host Extension, and build-profile guidance in `docs/js_aot_build.md`; this file is copied into the distribution as `kernel/docs/11_JS_TS与Web_AOT构建指南.md`.
- Put maintainer workflow, validation-matrix, wheel, and distribution instructions in `docs/kernel_development_guide.md`.
- Treat `distribution/kernel_development_pack/docs/` and `distribution/kernel_development_pack/project_template/` as source files for release users. Rebuild the distribution after changing them.
- Keep runnable claims synchronized with `examples/js_aot_minimal` and `examples/typescript_sandbox`.
- Historical design records may stay in `docs/`, but should not be treated as current API.
