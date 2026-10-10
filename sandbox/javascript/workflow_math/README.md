# JavaScript 嵌套与循环数学

通过真实 TypeScript Plugin、Node、BaseLib、Config 和 AOT 构建执行。共享纯数学库；每个配置只构建一次，trace 矩阵复用同一构建，每次调用使用独立运行状态。

| 场景 | 手写期望及通过条件 |
| --- | --- |
| nested_override | 输入 5：覆盖分支 `5*3+4=19`，同级默认分支 `5*2+1=11`；覆盖不泄漏，嵌套路径正确 |
| loop | 从 4 开始加三次 1：7；三次 carry、迭代事件正确 |
| nested_loop | 从 4 开始，外层两次、内层三次，每次加 1：10；六次 increment、八个内外层迭代事件 |
| edge_roles | 10 加 1 再乘 2：22；调度边不传送 999，数据边不提前触发消费者；实际顺序正确 |
| nested_async | 两层 Nodeset 内 `7*2=14`；deferred/detached 计划与完整路径正确；保留超时诊断和失败后复用检查 |
| task_metadata | 同步 `(10+8)-3=15`、等待能力后 `6*2=12`；区分同步返回与 Promise，核对 TaskPlan 与 event_loop executor；数据释放前不得完成 |
| loop_max_failure | 从 1 开始加 1，目标无法在两次内达到；应报 VF_MAX_STEPS，错误包含 workflow/节点/块路径，end 不执行 |
| trace_matrix | 同一 nested_override 构建分别 full/boundary/off 调用，数字不变；full 有节点事件，boundary 保留 Nodeset 边界，off 不输出事件 |

保留旧断言的公共辅助函数，避免重复编写任务元数据和错误路径检查。新增双层循环直接复用单层的 +1 body。正常源码使用标准 vibeflow.process；自定义 Rule 专项由原 comprehensive_math 和其他保留入口验证。

```bash
python sandbox/javascript/workflow_math/run_all.py --work-dir /tmp/workflow-math-js \
  --toolchain-root /path/to/project-with-installed-node_modules
```

共八组观察，其中 trace_matrix 包含三次独立调用。入口自动纳入 JS integration，接替六项旧任务。原配置仍被 pytest 和架构审查使用，继续保留。详见 [整合归档](../../../docs/maintainers/history/audits/workflow-math-20261010.md)。
