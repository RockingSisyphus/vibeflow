# 多文件资源沙箱

`python/` 包含 Python Node、BaseLib 与生命周期 Plugin；`javascript/` 同时包含 Node、BaseLib、Plugin 和多文件 Host。两者真实数值结果均为 6。Host 的支撑对象在工厂内创建；`types.d.ts` 使用 type-only 导入。

四类资源显式填写 `implementation_files`、Ruleset 和展示字段。模型功能块使用浅蓝色；Host 与库展示在资源区，实际类型导入和资源依赖保留在 Architecture 中。

在项目根目录安装其锁定工具链，再从仓库运行：

```bash
PYTHONPATH=src python -m vibeflow validate --workspace sandbox/resources/javascript/vibeflow_config.jsonc --config sandbox/resources/javascript/workflow.jsonc --json
PYTHONPATH=src python -m vibeflow review --workspace sandbox/resources/javascript/vibeflow_config.jsonc --config sandbox/resources/javascript/workflow.jsonc --output sandbox/resources/javascript/ARCHITECTURE.svg
PYTHONPATH=src python -m vibeflow build --workspace sandbox/resources/javascript/vibeflow_config.jsonc --config sandbox/resources/javascript/workflow.jsonc --target browser --profile single-esm --out-dir /tmp/vibeflow-resource-demo
```

`ARCHITECTURE.jsonc` 与 `ARCHITECTURE.svg` 是正式审核产物。资源专项矩阵从这些真实 SDK 项目复制隔离夹具；通过正式 CLI 检查修改、重新运行、恢复和最终图形：

```bash
python sandbox/rule_gaps/run_all.py --group resources --work /tmp/vibeflow-resource-cases --report /tmp/vibeflow-resource-cases.json
```

runner 自动准备锁定工具链和 Mermaid/Puppeteer，也可用 `--toolchain/--renderer` 复用安装。每项观察保存命令、退出码、诊断及产物位置；图形案例使用真实浏览器验证最终 SVG。历史的 1,219 项规则对照和 205 项接口案例继续由各自 runner 保留，新矩阵由完整验证入口一起执行。

公开接入说明见 [多文件资源文档](../../docs/user/multifile-resources.md)。[验收记录](../../docs/design/multifile-resources-results.md)、[案例对应表](../../docs/design/multifile-resource-cases.md) 和 [机器报告](../multifile_resources_report.json) 保存完整验证结果；正式图的浏览器截图及日志位于 `evidence/`。通用 Host 案例不替代 GSKO 的生产环境验收。
