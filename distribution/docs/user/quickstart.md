# 运行发行包自带示例

在解压后的发行包根目录执行下列命令。任选一个示例，验证本地环境后生成审核图。

## 安装示例依赖

两个示例在同一个工作区。生成任一示例的审核图前，先安装 JavaScript 示例的依赖，让审核命令能读取整个工作区。

```bash
npm ci --prefix javascript_project
```

## Python

检查并执行 `python_project` 自带的工作流，再生成审核图。

```bash
python run.py validate --config python_project/configs/main.jsonc
python run.py run --config python_project/configs/main.jsonc --input python_project/probe_input.json
python run.py review --config python_project/configs/main.jsonc
```

节点声明与部署方式见[Python 开发](python-development.md)。

## JavaScript / TypeScript

检查、构建并执行 `javascript_project` 自带的工作流，再生成审核图。

```bash
python run.py validate --config javascript_project/configs/main.jsonc
python run.py build --config javascript_project/configs/main.jsonc --target node --profile esm-module --out-dir javascript_project/build/node
node javascript_project/scripts/workflow_execution_probe.mjs
python run.py review --config javascript_project/configs/main.jsonc
```

节点声明与生成入口见[JavaScript 开发](javascript-development.md)。

## 查看流程

打开 `review` 返回的 HTML 快照链接，或双击发行包根目录的 `vibeflow-preview.html`。在「项目目录」中选择对应示例的工作流。操作说明见[本地预览](local-preview.md)。
