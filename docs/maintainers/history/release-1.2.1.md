# VibeFlow 1.2.1

本地分发包构建说明，2026-10-21。

## 变更与迁移

- 命名入口使用 `pipeline.entries` 与 `default_entry`；Python、JS、AOT 和 HTML 按入口选择可达流程，支持共享核心与独立入口契约。
- 提供跨 workflow 的 self / call / wait / send / receive / kill 接口，通过 Capability 与调用级 Rule Record 授权。Python、Node.js 和浏览器接入本机 JSON 通信，宿主和后台实例的清理由作者负责。
- 旧原生 IO 改为显式声明的普通 SDK 端口节点；旧 `io` 配置收到迁移诊断，旧隐式边界需补显式 terminal。迁移方法见[多入口与通信](../../../distribution/docs/user/workflow-coordination.md)。
- Workflow ABI 为 v9，旧 AOT 必须重建；AOT manifest 仍为 v3，展示快照仍为 v2。保留 Python AOT 固定准备资料复用，AOT 运行不生成预览报告。
- 两个 profile 均预装离线 HTML、配置、ELK、样式和空历史；保留展开、入口选择、资源视图和 workflow 操作展示，SVG 作为可选附件。
- 收拢展示事实职责和模块导入来源，更新文档与测试归属；默认测试并发为 12，规则矩阵拆分独立任务，补充真实 HTML 资源展示与 CLI 多入口覆盖。

## 验收依据

构建前代码 `132622f` 已完成正式完整门禁 18/18：pytest 4672、Python 沙箱 103、JS 集成 50（零跳过）、规则 1210/680、适配 207，以及浏览器、wheel 与双 profile 隔离验收。收尾记录提交为 `7310f3e`，详见[测试提效与技术债迭代](../test-and-debt-iterations.md)。本次仅更新版本和构建说明，另外针对新版本执行分发构建、ZIP 解压与包内运行验证。

本次两个 ZIP 均由 `distribution/build.py` 在专用工作区生成，沿用仓库标准双 profile 分发验证：包内 Python 校验与执行、JS 构建和 Node 执行、解压后 Python AOT 构建及移除原项目后的独立运行均通过。另将两个 ZIP 解压到含中文与空格的目录，实际 Chromium 离线打开初始空历史，再由包内 review 生成快照并显示流程；两者页面错误与 HTTP(S) 请求均为空。

验证后从原始 ZIP 交付未被探针修改的两个目录与 ZIP 到 dist，旧 1.1.5 ZIP 和校验清单保存在 archive。构建日志、包元数据、审查结果和浏览器证据见仓库旁 `VibeFlow-evidence/build-1.2.1-20261021`。本次未重复上一阶段的完整测试门禁；新版本分发的实际验证单独记录。
