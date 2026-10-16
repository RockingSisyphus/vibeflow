# Minimal Python Runtime project

The workflow is `input boundary -> business process -> output boundary`, with explicit start and end terminals. Replace the pass-through under `BUSINESS CODE` in `nodes/workflow_nodes.py`, then update the `@node` contract when the data relationship changes.

`plugins/code_plugin.py` exports the fixed plugin selected by `configs/main.jsonc`. Declare additional resources with `vibeflow.targets.python.sdk`, add them to that plugin, and select their Rulesets explicitly. For split implementations and default colors or shapes, read `kernel/docs/user/multifile-resources.md` from the distribution root.


部署可从发行包根目录构建完整目录 bundle：

```bash
python run.py build --config python_project/configs/main.jsonc --out-dir python_project/build/aot
python python_project/build/aot/run.py run --input python_project/probe_input.json --runtime-profile train
```

目录可独立搬迁，目标环境安装业务 Python 依赖。资源收集、对象引用和低层 API 见使用手册中的 Python 开发说明。
