# VibeFlow 项目概览

VibeFlow 把 AI 参与开发的程序组织成可执行、可检查、可审阅的显式流程图。小型 Node 承载业务职责，Config 声明控制流，端口契约表达数据流。

## 核心模型

```text
terminal start → input I/O → process / nodeset → output I/O → terminal end
```

## 开发闭环

1. 在真实 Config 和资源源码中表达职责、契约、执行关系及依赖。
2. 按[架构指南](user/architecture.md)维护开发资料，使用 HTML 查看流程与审查结果。
3. 执行结构与源码检查，再运行或构建指定 Target 的程序。
4. 用执行报告、业务测试和真实环境验收确认结果。

两种开发 profile 共用内核、项目模板与执行契约。collaborative 在实现前安排人类审阅；autonomous 在任务授权内自动完成开发闭环。发行包只携带所选 profile 的协议。

首次使用见[快速开始](user/quickstart.md)，完整导航见[用户手册](README.md)。
