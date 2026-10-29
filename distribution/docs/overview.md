# VibeFlow 项目概览

VibeFlow 把 AI 参与开发的程序组织成可执行、可检查、可审阅的显式流程图。小型 Node 承载业务职责，Config 声明控制流，端口契约表达数据流。

## 核心模型

```text
terminal start → input I/O → process / nodeset → output I/O → terminal end
```

| 概念 | 职责 |
| --- | --- |
| NodeType | 可复用的节点外观与默认局部规则 |
| Node | 具有明确职责和端口契约的原子处理单元 |
| NodesetType / Nodeset | 可复用子图的定义及其一次调用 |
| Config | 调用实例、显式连边、公共输入输出和资源选择 |
| Rule / Ruleset | 普通代码实现的检查及其组合关系 |
| Plugin | 提供类型、规则、Schema、Capability 和生命周期扩展的资源包 |
| BaseLib | 多个资源复用的辅助实现 |
| Capability | 宿主提供给工作流的显式 API |
| [架构资料](user/architecture.md) | 项目与工作流的阅读入口 |
| Target | 执行或生成工作流的语言后端：Python Runtime/AOT、JavaScript AOT |

## 开发闭环

1. 在真实 Config 和资源源码中表达职责、契约、执行关系及依赖。
2. 按[架构指南](user/architecture.md)维护开发资料，使用 HTML 查看流程与审查结果。
3. 执行结构与源码检查，再运行或构建指定 Target 的程序。
4. 用执行报告、业务测试和真实环境验收确认结果。

两种开发 profile 共用内核、项目模板与执行契约。collaborative 在实现前安排人类审阅；autonomous 在任务授权内自动完成开发闭环。发行包只携带所选 profile 的协议。

首次使用见[快速开始](user/quickstart.md)，完整导航见[用户手册](README.md)。
