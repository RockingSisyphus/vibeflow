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

## 目录用途与边界

仅用于：javascript / minimal 案例，验证最小 SDK / CLI 使用、配置加载与短流程执行；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
