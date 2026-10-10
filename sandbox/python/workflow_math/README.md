# 嵌套与循环数学

一个独立 SDK 数学项目，共享小整数节点和纯加法 BaseLib；通过正式 checked run 导出架构和 SVG，每种配置只准备、渲染一次，后续模式使用独立 Runtime。

| 场景 | 手写期望 | 额外通过条件 |
| --- | --- | --- |
| retry | 1 连加三次 2 得到 7 | carry、第三次停止、三次迭代、完整摘要及 qualified 路径；plan/compiled |
| wrapped_retry | Nodeset 内执行上述循环，得到 7 | 包裹层、循环层、迭代层路径完整 |
| outer_fixed | 外层三次，内层每次加两次 1，最终 6 | 外层固定停止；内层条件停止；历史 [2,2,2]；plan/block |
| outer_condition | 外层两次，内层每次加三次 1，最终 6 | 外层条件停止；内层固定停止；历史 [3,3]；plan/compiled |
| nested | `(4+6)*2+5=25` | 子计划参数 factor=2、节点顺序、导出清单、真实执行块及生成源码 |

同一个 nested 配置额外运行 plan/block/compiled × full/boundary/off 的九组矩阵。检查完整节点事件、边界事件顺序、off 仅保留运行摘要，以及 node_hooks 开关下 before_node/after_node/after_run 的表现。外部 Hooks 对象仅作为观察器，业务资源通过真实 SDK Plugin 声明。

共 17 组观察，另有五次 checked run。`expectations.json` 保存手写数字、路径和事件数量；没有调用被测计算来生成期望值。旧双层循环的业务累加从 outer+inner+1 简化为每次加 1，停止条件、carry/collect、迭代次数和路径保持原检查。

```bash
python sandbox/python/workflow_math/run_all.py --work-dir /tmp/workflow-math-python \
  --renderer-root /path/to/installed/mermaid-renderer
```

入口自动纳入 Python integration，替代 13 个旧任务。逐项对应见 [整合归档](../../../docs/maintainers/history/audits/workflow-math-20261010.md)。
