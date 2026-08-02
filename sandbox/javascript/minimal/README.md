# Minimal JavaScript/TypeScript AOT Sandbox

This project demonstrates a TypeScript node, a TypeScript `base_lib`, JSON
schemas, a generic host Capability, and all three AOT output profiles.

From the repository root, run the complete smoke test. The runner copies the
fixture into a temporary directory, installs the locked project toolchain
there, and removes all generated files on exit:

```bash
PYTHONPATH=src python sandbox/javascript/minimal/run_e2e.py
```

The runner also installs Puppeteer in its temporary workspace. Use
`--puppeteer-root <path>` only to reuse an existing installation, or
`--skip-browser` for a toolchain-only run.

Use `--keep-artifacts` to retain the copied project and build outputs under
`sandbox/javascript/minimal/.artifacts/`.

To invoke the normal build command directly, first install the fixture's
project-owned toolchain and then build a standalone Node ESM:

```bash
npm ci --prefix sandbox/javascript/minimal/project
PYTHONPATH=src python -m vibeflow build \
  --workspace sandbox/javascript/minimal/vibeflow_config.jsonc \
  --config sandbox/javascript/minimal/project/configs/greeting.jsonc \
  --target node \
  --profile single-esm \
  --out-dir dist-node
```

Build the browser application:

```bash
PYTHONPATH=src python -m vibeflow build \
  --workspace sandbox/javascript/minimal/vibeflow_config.jsonc \
  --config sandbox/javascript/minimal/project/configs/greeting.jsonc \
  --target browser \
  --profile web-app \
  --html sandbox/javascript/minimal/project/web/index.template.html \
  --app-entry sandbox/javascript/minimal/project/web/app.ts \
  --out-dir dist-web
```

Neither output imports Python or a browser-side VibeFlow runtime. The host owns
the clock implementation and supplies it independently for every
`runWorkflowAsync()` call. This example is explicitly asynchronous because its
clock Capability is declared with `completion: "suspend"`.
