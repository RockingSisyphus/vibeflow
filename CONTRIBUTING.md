# Contributing to VibeFlow

VibeFlow is a strict flowchart runtime for AI-assisted development. Contributions should keep that boundary tight: small nodes, explicit flow edges, checkable contracts, and runnable diagrams.

## Ground Rules

- Do not reintroduce removed public concepts such as `boundary`, `pipeline.loops`, `max_iterations`, edge `max_executions`, or edge `loop`.
- Program control flow must come from explicit `pipeline.edges`; `requires` and `provides` are data contracts only.
- Implemented nodes get `flow_kind` from `NODE_INFO`, not from config.
- Planned nodes and nodesets are for architecture review only; runtime must refuse to execute planned content.
- Nodes should stay small and pure. Real IO belongs outside pure business nodes and must be modeled through the flowchart contract.
- Prefer warnings or policy/plugin hooks for semantic smells; reserve hard errors for rules that protect the core architecture contract.

## Development Setup

Use Python 3.11 or newer.

```bash
python -m pip install -e .
```

## Required Checks

Run these before opening a pull request:

```bash
python -m compileall -q src tests examples
pytest -q
PYTHONPATH=src python examples/integration_sandbox/run_all.py
PYTHONPATH=src python -m vibeflow quality-check --path .
```

If you touch side-effect scanning or purity checks, also run:

```bash
PYTHONPATH=src python -m vibeflow quality-check --path . --check-side-effects
```

## Documentation

- Keep `docs/current_implementation_status.md` aligned with shipped behavior.
- Put user-facing usage guidance in `docs/developer_guide.md`.
- Put maintainer workflow changes in `docs/kernel_development_guide.md`.
- Historical design records may stay in `docs/`, but should not be treated as current API.
