# topology-kernel

Strict topology runtime prototype for pure-function nodes.

This repository is intended to become a portable kernel that can be reused by Paperflow and other projects. It is deliberately strict:

- every node must be pure;
- nodes cannot call each other;
- configuration owns topology;
- cycles must be explicitly declared and bounded;
- larger behavior should be composed through nested nodesets;
- side effects belong only to a framework-level global boundary, not to nodes.

## Smoke Test

```powershell
python -m pytest tests\unit
$env:PYTHONPATH='src'; python -m topology_kernel --help
```

## Documents

- `docs/kernel_target_vision.md`: target design and long-term goals.
- `docs/current_implementation_status.md`: what is implemented now and what is still missing.
- `docs/strict_kernel_design.md`: detailed design draft migrated from Paperflow.
