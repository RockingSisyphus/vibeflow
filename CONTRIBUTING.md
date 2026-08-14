# Contributing to VibeFlow

This guide is for people changing the VibeFlow framework. Project authors should start with `docs/overview.md` and `docs/user/quickstart.md`.

VibeFlow 0.13.2 uses independent Python and JavaScript Target application closures. Every project root declares exactly one `project_target`; do not introduce cross-Target workflow execution or imports. Use the layered packages directly and keep language-specific implementation outside Core.

## Architecture rules

The dependency direction is:

```text
tooling → targets/python ──────┐
        → targets/javascript ─├─→ block_compiler → core
```

- Core is language-neutral and pure in memory. It cannot read files or the environment, start processes, dynamically import code, or depend on a Target or Tooling.
- Block Compiler depends only on Core. `WorkflowPlan` and `BlockPlan` contain frozen data, contracts, routes, IDs and source references, never callables, plugins or generated source.
- Python and JavaScript Targets never import one another.
- Tooling owns file loading, CLI orchestration and presentation. Language analysis belongs to its Target; language-neutral decisions belong to Core.
- `pipeline.edges` defines executable control flow. `requires` and `provides` define data contracts.
- Planned resources remain non-runnable and visible in architecture output.
- Generated JavaScript modules have no import-time business side effects. Invocation state, traces, tasks, cancellation and Capability wrappers are isolated per call or host instance.
- General framework invariants belong in Core. Project-specific behavior belongs in a Node, base_lib, Capability, Target-owned Plugin or JavaScript Host Extension. JS/TS Policy, Compiler and Runtime Plugins use `vibeflow.plugin.v1`; Host Extension remains the separate long-lived host lifecycle boundary.

Stable import families are:

```python
from vibeflow.core import ...
from vibeflow.core.quality import ...
from vibeflow.block_compiler import ...
from vibeflow.targets.python.project import ...
from vibeflow.targets.python.runtime import ...
from vibeflow.targets.python.quality import ...
from vibeflow.targets.javascript.frontend import ...
from vibeflow.targets.javascript.build import ...
from vibeflow.targets.javascript.quality import ...
from vibeflow.tooling.project import ...
from vibeflow.tooling.application.python import ...
from vibeflow.tooling.application.javascript import ...
from vibeflow.tooling.application.python.presentation import ...
```

## Development setup

Use Python 3.11 or newer:

```bash
python -m pip install -e .
```

## Validation

Run the full project gate before opening a pull request:

```bash
python tools/verify_project.py --full
```

It runs the independent repository self-check, tests for every layer, both integration Sandboxes, Python/JavaScript conformance, Node/browser AOT profiles, wheel isolation and a temporary distribution smoke test.

For a focused check, run one independent quality profile:

```bash
python quality/run.py --profile base
python quality/run.py --profile core
python quality/run.py --profile block-compiler
python quality/run.py --profile python-target
python quality/run.py --profile javascript-target
python quality/run.py --profile all
```

The `quality/` project is self-contained, does not import VibeFlow and is not included in the wheel. `python -m vibeflow quality-check` is a different tool: it checks user projects through Tooling file scanning, Target fact extraction and Core Quality evaluation.

The runnable suites are organized by Target:

```bash
PYTHONPATH=src python sandbox/python/integration/run_all.py
PYTHONPATH=src python sandbox/javascript/minimal/run_e2e.py --skip-browser
PYTHONPATH=src python sandbox/javascript/integration/run_all.py --skip-browser
```

Release acceptance must also run the JavaScript integration Sandbox with its real browser dependency; `tools/verify_project.py --full` handles the complete setup.

## Generated files and distribution

Preview workspace cleanup before applying it:

```bash
python tools/clean_workspace.py
python tools/clean_workspace.py --apply
```

The cleaner only removes known generated files. It never handles `.git/`, `references/` or the `distribution/` source templates.

Build a temporary distribution first, then rebuild the formal package after the full gate passes:

```bash
python distribution/build.py \
  --output-dir /tmp/vibeflow-distribution-smoke \
  --archive-dir /tmp/vibeflow-distribution-archives
```

Do not edit generated distribution output. Change canonical sources under `docs/`, `distribution/prompts/` or `src/vibeflow/`, then rebuild.

## Documentation

- Stable user interfaces belong in `docs/user/`.
- Language-neutral design belongs in `docs/design/`.
- Repository and release procedures belong in `docs/maintainers/`.
- Distribution prompts only route agents to canonical user documentation.
- Keep runnable claims synchronized with `sandbox/`.
- Git history and release notes preserve migration history; active guides describe current behavior.
