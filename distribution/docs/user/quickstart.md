# 快速开始

发行包包含两个可运行的最小项目：`python_project` 使用 Python Runtime，`javascript_project` 使用 JS/TS AOT。两个示例均包含起点、输入边界、业务处理、输出边界和终点。

## 确定项目与源码

先阅读根目录 `AGENTS.md`，再按[架构阅读指南](architecture.md)了解项目并定位任务源码。

以下命令使用发行模板的 root 名称；在业务项目中替换为实际路径。目录名和 root ID 可自定义，在 `vibeflow_config.jsonc` 中注册；具体改名步骤及发行元数据的边界见[项目治理](project-governance.md#root-注册与改名)。

## Python

业务代码位于 `python_project/nodes/workflow_nodes.py`，资源插件位于 `python_project/plugins/code_plugin/plugin.py`。修改源码后执行：

```bash
python run.py validate --config python_project/configs/main.jsonc
python run.py run --config python_project/configs/main.jsonc --input python_project/probe_input.json
python run.py quality-check --workspace vibeflow_config.jsonc
```

节点声明与部署方式见[Python 开发](python-development.md)。

## JavaScript / TypeScript

业务代码位于 `javascript_project/nodes/process_payload.ts`，资源插件位于 `javascript_project/plugins/code_plugin/plugin.ts`。首次使用先安装依赖，再生成并执行产物：

```bash
npm ci --prefix javascript_project
python run.py validate --config javascript_project/configs/main.jsonc
python run.py build --config javascript_project/configs/main.jsonc --target node --profile esm-module --out-dir javascript_project/build/node
node javascript_project/scripts/workflow_execution_probe.mjs
```

节点声明与生成入口见[JavaScript 开发](javascript-development.md)。

## 查看流程

```bash
python run.py review --config python_project/configs/main.jsonc
```

打开命令返回的 HTML 快照链接。预览器也可从根目录 `vibeflow-preview.html` 离线打开。页面操作见[本地预览](local-preview.md)，检查及执行报告见[命令与结果](commands-and-results.md)。

后续任务从[文档导航](../README.md)选择对应手册；升级已有项目时先读[迁移说明](rule-system-migration.md)。
