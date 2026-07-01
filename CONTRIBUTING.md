# Contributing to VibeFlow

This guide is for people changing the VibeFlow framework itself. If you are using VibeFlow to build a business project, start with `docs/developer_guide.md` instead.

## Framework Ground Rules

- Do not reintroduce removed public concepts such as `boundary`, `pipeline.loops`, `max_iterations`, edge `max_executions`, or edge `loop`.
- Keep `pipeline.edges` as the only source of executable control flow. `requires` and `provides` are data-contract diagnostics, not scheduler edges.
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

## Documentation

- Keep `docs/current_implementation_status.md` aligned with shipped behavior.
- Put user-facing usage guidance in `docs/developer_guide.md`.
- Put maintainer workflow changes in `docs/kernel_development_guide.md`.
- Historical design records may stay in `docs/`, but should not be treated as current API.
