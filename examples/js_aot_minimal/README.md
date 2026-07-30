# Minimal JS/TS AOT example

This project demonstrates a TypeScript node, a TypeScript `base_lib`, JSON
schemas, a generic host Capability, and all three AOT output profiles.

Install the project-owned and locked toolchain:

```bash
cd project
npm ci
cd ..
```

Build a standalone Node ESM:

```bash
PYTHONPATH=../../src python -m vibeflow build \
  --workspace vibeflow_config.jsonc \
  --config project/configs/greeting.jsonc \
  --target node \
  --profile single-esm \
  --out-dir dist-node
```

Build the browser application:

```bash
PYTHONPATH=../../src python -m vibeflow build \
  --workspace vibeflow_config.jsonc \
  --config project/configs/greeting.jsonc \
  --target browser \
  --profile web-app \
  --html project/web/index.template.html \
  --app-entry project/web/app.ts \
  --out-dir dist-web
```

Neither output imports Python or a browser-side VibeFlow runtime. The host owns
the clock implementation and supplies it independently for every
`runWorkflowAsync()` call. This example is explicitly asynchronous because its
clock Capability is declared with `completion: "suspend"`.
