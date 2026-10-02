# Python 业务分类与领域规则示例

`project/bundles/domain.jsonc` 同时提供 Node、分类、Rule 和 Ruleset。
Node 类只包含执行代码。模型分类默认浅蓝色，数据变换分类默认浅绿色；
调用点仍可覆盖展示属性，连接和执行继续使用原生 Node 契约。

本例的领域约定是：`model_forward` 必须是 `model_block` Node 的直接方法，
每个块恰好包含一个这样的定义。普通计算 helper 可以复用，引用 helper
不会让其中的模型定义自动获得合法归属。这是示例插件明确选择的约定，
并不代表 VibeFlow 能自动识别任意模型代码。

规则使用公开的 Python SourceContext：已选择的节点、文本、隔离 AST、
符号、调用关系和 Node→helper 归属；它不读取文件，也不导入业务 Node。
模型规则集局部覆盖 `node_interface.allowed_methods`，允许 `model_forward`；
效果检查仍由所选择的 `vibeflow.process` 规则集决定。

在仓库根目录运行：

```bash
python -m vibeflow validate --workspace sandbox/python/domain_rules/vibeflow_config.jsonc --config sandbox/python/domain_rules/project/configs/model.jsonc --json
python -m vibeflow quality-check --workspace sandbox/python/domain_rules/vibeflow_config.jsonc --json
python -m vibeflow review-rules --workspace sandbox/python/domain_rules/vibeflow_config.jsonc --config sandbox/python/domain_rules/project/configs/model.jsonc --json
python -m vibeflow export-mermaid --workspace sandbox/python/domain_rules/vibeflow_config.jsonc --config sandbox/python/domain_rules/project/configs/model.jsonc
python -m vibeflow run --workspace sandbox/python/domain_rules/vibeflow_config.jsonc --config sandbox/python/domain_rules/project/configs/model.jsonc --input sandbox/python/domain_rules/input.json --run-root /tmp/vibeflow-domain-runs
```

原生工作流先计算模型块 `3 × 2`，再由数据变换块加 `1`，结果为 `7`。
`review-rules` 只加载声明及组合图，不导入 Node 或 Rule 的实现。
