# 原生任务管理

使用公开 Python SDK、配置和正式 CLI，验证 A/B/C 并发、B 的失败与 finally、取消请求和等待退出、成功结果、普通 Node 复制名单、另一管理 Node 等待、重复与空名单。分别运行 plan、compiled、block。

```bash
python sandbox/python/task_management/run_all.py --renderer-root /path/to/renderer
```

计时清理保留 40 毫秒探针；判定依据是事件先后顺序。公开 CLI 矩阵还覆盖选择性停止、独立重复启动、名单复制／筛选／合并、非法槽与引用、清理及并发失败、父流程失败、未消费失败、外部 SIGINT、无后续 join 的 workflow 收尾，以及普通／管理 Nodeset 任务目标在单工作线程下的成功和排队停止。

底层操作不响应取消、线程池屏障、规则关闭后的权限及执行锁由 `tests/targets/python/test_task_management.py` 等定向测试补充。反复启动 512 个短任务验证结果保留与执行资源回收。Loop 目标的配置、执行与图形覆盖位于 workflow_math 及 scheduled composite 测试。运行目录与依赖均在仓库外。
