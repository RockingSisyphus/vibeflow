# 分段数学与工作流调度

通过真实 Python SDK Plugin、Node、BaseLib 和 Config 执行小整数计算。一个独立入口包含四种拓扑，复用加法实现，每次调用使用独立运行状态。

主要公式：`u=a+b`，`v=c+d`；当 `u>=v` 时 `w=u+1`，否则 `w=v-1`；最后 `result=w+u`。

| 输入 a,b,c,d | u | v | 分支 | w | result |
| --- | ---: | ---: | --- | ---: | ---: |
| 2,3,1,2 | 5 | 3 | left | 6 | 11 |
| 1,1,2,3 | 2 | 5 | right | 4 | 6 |
| 1,2,1,2 | 3 | 3 | left（等号边界） | 4 | 7 |

| 配置 | 模拟用户的组织方式 | 通过条件 |
| --- | --- | --- |
| linear | 将 `(2+3)+1-1=5` 拆成串行节点，中间复制一次值 | 每个中间值、最终 5、六个节点的顺序、边次数、摘要与停止状态正确 |
| split | 分段函数的两个分支分别结束，各自算出 `w+u` | 三组常量全部正确；未选中分支及其终点不执行、不输出结果；选中终点正确 |
| join | 两个互斥分支产生不同 key、相同 `selected_w` 类型，之后统一计算 `w+u` | `any_active` 汇合；`exactly_one` 只解析一个活跃 provider；原始 source key 正确；输出 11、6、7 |
| bypass | 按顺序算 `u`、`w=u+1`、`w+u`，并通过数据旁路把 u 直接送给 finish | 结果 11；finish 仍等待 left；`u→finish` 在架构事实中标识为仅传递数据；虚线绘制由独立浏览器专项验收 |

每个配置均运行 plan/full、compiled/boundary、compiled/full，共 24 组独立观察。compiled 必须生成一个完整执行块，通过 `run_graph_block` 使用公共图协调器，不能包含 `_run_node(`。完整 trace 检查节点、边、类型解析；边界 trace 只检查块事件与摘要。每个配置另执行一次正式 checked run，验证 health 无 error、架构文档、结构化快照及预览入口。

```bash
python sandbox/python/piecewise_math/run_all.py
# 保存产物及逐项检查报告；目录应位于仓库外且尚未使用
python sandbox/python/piecewise_math/run_all.py --work-dir /path/outside/repository/vibeflow-piecewise-review
```

Python integration 自动执行此入口。11 个旧任务及断言迁移位置见 [替代归档](../../../docs/maintainers/history/audits/piecewise-math-20261010.md)。异常调度、循环边界、异步清理等专项继续独立保留。

## 目录用途与边界

仅用于：python / piecewise_math 案例，验证以分段数学流程验证分支、汇合与数据旁路；保留真实项目输入与 runner。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
