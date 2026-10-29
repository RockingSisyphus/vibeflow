# 架构阅读与维护：项目、root 与 Workflow

AI 开始项目开发时，应优先阅读已有架构资料，先了解项目和目标 root，再进入相关 workflow，最后按来源定位 Config、Nodeset 和资源实现。本指南统一说明架构资料的层级、阅读顺序、登记与更新方法。

## 三个阅读层级

| 层级 | 资料位置 | 主要内容 |
| --- | --- | --- |
| 项目 | 项目根目录的 `PROJECT_ARCHITECTURE.jsonc` | 项目用途、顶层目录职责、全部注册 root、workflow 清单与资源使用关系 |
| root | 项目总览中 `roots` 数组的对应条目 | root 的 ID、路径、用途、Target，以及其下各 workflow 的路径、说明、入口、架构文档位置和关联 |
| workflow | 所属 root 的 `vibeflow_project.jsonc` 中 `architecture.documents` 登记的文件 | 一份 workflow 的节点、连边、契约、子图、资源、规则与源码来源 |

当前 root 的整体总览保存在项目文档的 `roots` 条目中。发行模板的 `<root>/ARCHITECTURE.jsonc` 对应 `configs/main.jsonc`；一个 root 有多份 workflow 时，应按登记逐份阅读，文件名和存放目录可以不同。

## AI 的优先阅读顺序

1. 阅读项目根目录 `AGENTS.md`，确认适用的开发协议；从项目架构文档了解项目用途、目录分工、各 root 的职责与 Target。
2. 在 `roots` 中选择任务所属条目，查看所列 workflow 清单、入口、说明及相互关系。结合项目配置确认 root 路径，阅读该目录适用的 README 与 `AGENTS.md`。
3. 按 workflow 条目的 `architecture` 路径及 root 配置中的登记打开相关架构文档；任务涉及多个 workflow 时，分别阅读各自文档。
4. 从 workflow 的控制流、数据契约、Nodeset 调用和资源依赖判断变更位置，再沿 `source` 与实现来源打开真实源码。
5. 核对源码与任务要求，在 Config 和资源实现中完成变更，并按本指南更新受影响的生成资料。

例如，修改后台计算请求时，先在项目总览找到 `backend` root，再查看它的请求处理与后台任务 workflow，最后进入对应节点源码。这样可以先确认调用关系和资源归属，再决定复用或修改哪个环节。

## 项目与 root 总览怎么读

`PROJECT_ARCHITECTURE.jsonc` 使用 `vibeflow.project-architecture.v2` 格式：

- `purpose` 和 `directories` 说明项目用途及顶层目录职责。
- `roots` 中每项包含 `id`、`path`、`purpose`、`target` 和 `workflows`。root 的普通子目录不在这里递归展开。
- workflow 条目的 `project_path` 与 `architecture` 均相对项目目录；`entries`、`default_entry` 描述命名入口，`relations` 描述已准备的调用或预期通信关系。
- `resources` 记录资源所有者与使用关系；`used_by_workflows` 表示声明引用，实际执行结果从运行报告读取。
- `inventory_complete` 和 `diagnostics` 说明清单是否完整。条目缺失、登记损坏或资料过期时，按诊断核对配置与源码，必要时重新生成。

## Workflow 架构怎么读

每份文档记录一个 workflow，重点查看：

| 字段 | 阅读目的 |
| --- | --- |
| `project_target`、`workflow.source` | 确认 Target、所属 root 和真实 Config |
| `workflow.nodes`、`workflow.edges` | 理解调用职责、分支、汇合及调度／数据关系 |
| `workflow.inputs`、`workflow.outputs`、入口资料 | 确认公开契约和执行范围 |
| `nodeset_types` | 理解复用子图、Loop body 与内部调用 |
| `node_definitions`、`node_types` | 区分业务定义、默认类型和实际调用 |
| `resources`、实现来源与 `implementation_graph` | 定位 Node、BaseLib、Plugin 的入口、支撑源码及依赖 |
| `rule_selections`、`rule_checks`、`call_policies` | 查看所选规则、检查结果和调用授权 |

检查字段按本次操作的实际输出读取。按来源记录中的 root 与路径定位文件；同一业务定义在不同调用位置可以使用不同参数和规则。源码引用描述实现位置，planned 状态与运行记录分别说明规划和执行情况。

## 在 root 中登记 workflow 文档

在该 root 的 `vibeflow_project.jsonc` 中登记一一对应的源配置与生成文件，路径均相对所属 root：

```jsonc
{
  "project_target": "python",
  "architecture": {
    "documents": [
      {"workflow": "configs/main.jsonc", "document": "ARCHITECTURE.jsonc"},
      {"workflow": "configs/worker.jsonc", "document": "docs/worker-architecture.jsonc"}
    ]
  }
}
```

同一 workflow 登记一次，每份文档使用独立输出路径。业务变更写入真实 Config 与资源源码，架构文档由命令生成。

## 生成与更新

在发行包根目录执行；示例中的 root、Config 与输出路径替换为实际登记值。

```bash
python run.py architecture --config <root>/configs/main.jsonc --output <root>/ARCHITECTURE.jsonc
python run.py architecture --config <root>/configs/main.jsonc --output <root>/ARCHITECTURE.jsonc --check
python run.py preview --workspace vibeflow_config.jsonc
```

第一条生成所选 workflow 文档；`--check` 只核对指定文档。`preview --workspace` 更新项目架构总览、页面资源和项目目录，workflow 文档与审查快照按各自命令生成。

完整 `review` 和项目 `quality-check` 更新项目总览；`review --config` 同时更新所选 workflow 的已登记文档与 HTML 快照。单 workflow 构建发布本次快照及已有项目总览的展示投影。修改 root 登记、workflow 清单或共享资源关系后更新项目总览；修改流程或资源实现后更新受影响的 workflow 文档。

优先使用已有资料开展定位，按实际缺失或变化更新；文档新鲜度检查用于显式核对，不作为业务运行的额外前置条件。HTML 交付与页面操作见[本地预览](local-preview.md)。
