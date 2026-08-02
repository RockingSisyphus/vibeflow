# VibeFlow 分发开发包

本模板对应 VibeFlow 0.10.1。发布物包含一个通用内核和两个彼此独立的示例 root：

```text
vibeflow-distribution/
├── python_project/       # project_target: python
├── javascript_project/   # project_target: javascript
├── kernel/
├── DISTRIBUTION.json
├── vibeflow_config.jsonc
└── run.py
```

每个 root 必须在自己的 `vibeflow_project.jsonc` 中声明一个 `project_target`。Python root 用 Registry 绑定 Python node、base_lib 和 Plugin；JavaScript root 用静态 descriptor 绑定 JS/TS node、base_lib、Plugin、Capability 和 Host Extension。一个 workspace 可以同时包含两个 root，但单次 workflow 和 nodeset import 不跨 Target。

## 构建发布物

在仓库根目录运行：

```bash
python distribution/build.py
```

默认采用“预验证后成对发布、失败完整回滚”：

```text
dist/vibeflow-distribution/
archive/vibeflow-distribution-0.10.1.zip
```

临时验证可指定：

```bash
python distribution/build.py \
  --output-dir /tmp/vibeflow-distribution \
  --archive-dir /tmp/vibeflow-archives
```

`--output` 暂作为 `--output-dir` 的兼容别名。构建器先完成质量自检，在临时位置生成目录、内核 manifest、`DISTRIBUTION.json` 和确定性 ZIP，全部验证通过后再依次发布目录和 ZIP；任一发布步骤失败都会完整回滚到发布前的目录/ZIP 配对。ZIP 只有 `vibeflow-distribution/` 一个顶层目录。

## 使用示例

Python：

```bash
python run.py validate --config python_project/configs/main.jsonc
python run.py review --config python_project/configs/main.jsonc --output reports/python.svg
python run.py run --config python_project/configs/main.jsonc --run-root runs
```

JavaScript/TypeScript：

```bash
npm ci --prefix javascript_project
python run.py review --config javascript_project/configs/linear.jsonc \
  --output reports/javascript.svg
python run.py build --config javascript_project/configs/linear.jsonc \
  --target node --profile single-esm --out-dir output/node
python run.py build --config javascript_project/configs/linear.jsonc \
  --target browser --profile web-app \
  --html javascript_project/web/index.template.html \
  --app-entry javascript_project/web/app.ts \
  --out-dir output/web
```

workflow 不声明 Browser/Node 平台。每次 `build --target` 选择本次构建所需实现。VibeFlow 检查流程图、ABI、资源边界并调用 esbuild；完整 TypeScript 类型、lint、平台 API 兼容性和业务结果由项目自己的 `tsc`、ESLint、Vitest、Playwright 或真实宿主测试负责。

`javascript_project/configs/browser_permanent_port_host.jsonc` 是正式包内的
异步长期示例：无界 loop 通过 Browser Host Extension 接收 `window.message`，经
TS Node/base_lib 计算后从 `vibeflow.port` 发送结果，并可由 `host.stop()` 取消。

## 文档职责

- `project_template/README.md`：用户快速入口。
- `project_template/AGENTS.md`：AI 必须遵守的高优先级规则。
- `docs/00–08`：按主题展开的用户规则。
- 源码仓库 `docs/developer_guide.md` 与 `docs/js_aot_build.md` 会分别复制成内核文档 `10` 和 `11`。

历史实施计划不进入分发包。内核文件和文档由
`kernel/MANIFEST.sha256` 保护；用户可以修改两个项目 root、根 README 和
AGENTS。完整的 Python/JavaScript 语义测试保留在源码仓库的 `sandbox/`。
