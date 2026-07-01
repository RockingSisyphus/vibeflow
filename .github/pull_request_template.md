## Summary


## VibeFlow contract impact

- [ ] Changes explicit `pipeline.edges` behavior
- [ ] Changes node purity or source-quality checks
- [ ] Changes planned / implemented behavior
- [ ] Changes flow_kind semantics or diagram output
- [ ] Changes release-package workflow
- [ ] No contract impact

## Checks

- [ ] `python -m compileall -q src tests examples`
- [ ] `pytest -q`
- [ ] `PYTHONPATH=src python examples/integration_sandbox/run_all.py`
- [ ] `PYTHONPATH=src python -m vibeflow quality-check --path .`

## Notes
