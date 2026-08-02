# VibeFlow repository quality checker

This directory is a self-contained standard-library Python project. It checks
the VibeFlow repository itself and deliberately does not import `vibeflow`.
It is not included in the VibeFlow wheel or distribution package.

Run all profiles from the repository root:

```bash
python quality/run.py --profile all
```

Run one profile or emit the stable JSON report:

```bash
python quality/run.py --profile core
python quality/run.py --profile javascript-target --format json
```

Profiles are `base`, `core`, `block-compiler`, `python-target`,
`javascript-target`, and `all`. JavaScript checks require Node.js 22 or newer.
Exit status `0` means the selected profile passed, `1` means it found repository
violations, and `2` means the checker could not run (for example, the requested
repository or Node.js executable was missing).

The checker's own tests use only `unittest`. The runner also prevents test
bytecode from being written into the source tree:

```bash
python quality/test.py
```
