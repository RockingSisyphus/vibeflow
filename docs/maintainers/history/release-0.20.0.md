# VibeFlow 0.20.0

## 中文更新日志

本次以 GitHub 上一个正式分发版本 **v0.18.3（`61600d5`）** 为基线，根据 `v0.18.3..ec27c83` 的 Git 历史整理，包含此前仅在本地构建的 0.19.0、0.19.1 和本轮 0.20.0。此版本包含不兼容的任务调用与结果领取变化。

### 原生任务管理与并发

- 新增任务管理 Node：通过 `flow_kind="task_manager"`、`vibeflow.task_manager` 和有限的 `task_targets` 声明启动目标。目标复用 Node／Nodeset 的输入输出合同和实现，Architecture 展示管理节点及启动关系。
- 通过 `context.tasks` 启动任务、等待任意结果、请求停止和等待实际退出。TaskRef 是普通数据，可用数组保存、筛选和沿数据连边传递；不要求额外 TaskGroup。
- Python 使用线程执行，JavaScript 使用事件循环并发；未引入 JS Worker 执行器。失败结果由管理 Node 决定如何处理，不自动取消兄弟任务。
- workflow 收尾会停止并等待所属任务、finally 清理、SDK 操作及受管后代。停止请求与实际退出分开；未领取失败会在收尾时报告。取消伴随清理失败保留失败信息。

### 结果一次交付与任务卡回收

- `waitAny`／`wait_any` 和 `waitAllExited`／`wait_all_exited` 成功交付结果后，自动移除对应任务记录。父流程保存并转交普通结果，无需手动 release；常驻 workflow 已领取的短任务卡不再累计。
- 已结束但尚未领取的结果仍保留，支持稍后来取。领取后重复等待或停止同一引用（包括复制件）报 `VF_TASK_REF_INVALID`。
- 重叠等待只允许一次接收；整批领取不会因部分引用已被消费而丢失其他任务结果。Python 任务 ID 删除后不复用，并释放已合并的子 trace 对象。
- 修复退出 trace 回调重入等待时可能取得暂定成功结果的问题：回调错误处理完毕后才发布最终 outcome。
- 回收对象是任务卡及内部执行引用；业务自行保存的结果与历史 trace 仍按各自用途保留。

### 修复与文档

- 修复跨 workspace root 的 planned 管理 Node／独立 Nodeset 源码审查遗漏已登记 BaseLib 归属的问题。合法导入恢复正常，真正未登记导入仍被拒绝；不改变 planned 调用的执行身份。
- 新增双 Target 公开任务管理与源码归属沙箱，覆盖取消清理、嵌套归属、排队任务、迟领及消费后的引用失效。
- 用户手册新增完整 Python／TypeScript 接入和迁移示例；仓库 docs 独立说明编译链路、生命周期、运行器与维护验证。修复 GitHub 首页 README 的展示优先级。

### 迁移注意事项

- Workflow ABI 从 **v5 升至 v6**。旧调用级 `async`、`result_key`、`detached` 和停止等待超时入口须改用任务管理接口，没有自动转换层。JS workflow 的 `pipeline.entry_mode="async"` 仍用于异步执行入口。
- 从本地 0.19.x 升级也须修改重复等待逻辑：收到结果后从 pending 名单删除其引用，保存 outcome，再等待剩余任务。其他节点需要结果时，由父流程传递 outcome。
- 修改真实声明与配置后重新生成 Architecture、计划和构建产物。详见分发包中的 `kernel/docs/user/task-management.md`。

### 资产与验证

- `vibeflow-distribution-0.20.0.zip`：人机协同开发包。
- `vibeflow-distribution-autonomous-0.20.0.zip`：自主开发包。
- `SHA256SUMS-0.20.0.txt`：两个 ZIP 的校验值。

两包由项目既有 `python -B distribution/build.py` 构建。第二轮独立全量验收 **18/18 步通过、4458 pytest 通过**；Python integration 104/104、JS integration 50/50、规则对照 1223/1223、资源回归 680/680、适配 207/207。两侧各覆盖 1024 个短任务在 workflow 未退出时领取并回收。正式 ZIP 解压后验证 **25/25 项通过**，包内手册示例另有 **5 项通过**。第一轮 golden 失败记录保留，未用后续 PASS 覆写；这些检查不代替下游项目的业务验收。

### Git 历史依据

- `3dac200`：原生任务管理、Workflow ABI v6 和所属任务统一收尾。
- `c70a724`、`0f307cd`：0.19.0 本地分发包及开发／用户文档。
- `0eda755`、`75a5345`：跨 root 源码归属复现、正式修复及 0.19.1 本地包。
- `ec27c83`：一次交付、任务卡回收、并发接收回归及 0.20.0 本地包。
- `c722d0d`：GitHub 首页 README 展示修复。

[完整提交比较：v0.18.3 → v0.20.0](https://github.com/RockingSisyphus/vibeflow/compare/v0.18.3...v0.20.0)

## English release notes

This release compares against the previous published distribution, **v0.18.3 (`61600d5`)**, using Git history through `ec27c83`. It includes the intervening local 0.19.0 and 0.19.1 builds and introduces breaking task API and result-delivery changes.

### Highlights

- Native task manager Nodes declare finite Node/Nodeset targets and use `context.tasks` to start, wait for any result, request a stop, and wait for actual exit. TaskRefs are ordinary data, transferable through arrays and graph edges; Architecture displays manager Nodes and launch relationships.
- Python executes tasks with threads; JavaScript uses event-loop concurrency, without a Worker executor. Managers choose how to handle failures. Workflow teardown waits for owned execution, finally cleanup, SDK operations and descendants, and reports unreceived failures.
- Waiting now delivers results exactly once and retires the corresponding task records. Parents retain and forward ordinary outcomes. Finished but unreceived results remain available; waiting or stopping a consumed ref raises `VF_TASK_REF_INVALID`. Overlapping batch delivery cannot partially discard results. Python IDs are not reused after retirement.
- Final outcomes are published only after exit trace callbacks complete, including callback errors. Task-card retirement does not bound application-held results or historical traces.
- Fixed false source-ownership rejection for registered BaseLib imports in cross-root planned manager / standalone Nodeset declarations, while preserving rejection of genuinely unowned imports.
- Added public task-management and ownership sandboxes, separate maintainer documentation, executable Python/TypeScript usage examples, and corrected GitHub homepage README precedence.

### Migration

Workflow ABI advances from **v5 to v6**. Replace legacy call-level `async`, `result_key`, `detached` and stop-wait timeout APIs with declared task targets and manager controls. Workflow-level `pipeline.entry_mode="async"` remains the JS asynchronous entry selector. There is no automatic migration layer.

Projects using local 0.19.x must also remove received refs from pending lists and keep returned outcomes instead of querying task results again. Regenerate Architecture, plans and build output after changing declarations or configuration. See `kernel/docs/user/task-management.md` in either package.

### Assets and validation

Both collaborative and autonomous distribution ZIPs and their checksum list are attached. The independent second full run passed **18/18 steps and 4458 pytest tests**, including Python/JS integration, rule parity, resource, adaptation, browser and packaging checks. Each runtime covers 1024 short tasks retired while the workflow remains active. Actual release ZIPs passed **25 extracted-package checks**; handbook examples passed **5 additional checks**. Earlier failed golden checks remain recorded separately. Downstream business acceptance is outside these results.

[Full comparison: v0.18.3 → v0.20.0](https://github.com/RockingSisyphus/vibeflow/compare/v0.18.3...v0.20.0)
