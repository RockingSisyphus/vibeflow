# 原生任务管理

真实 SDK 声明与 workflow 配置由正式 CLI 构建，再在 Node.js 和真实 Chromium 中调用。覆盖 `esm-module`、`web-app`，验证 A/B/C、失败及 40 毫秒异步 finally、停止请求与等待退出、名单经普通 Node 复制后由另一个管理 Node 使用、重复与空名单。

```bash
python sandbox/javascript/task_management/run_all.py --toolchain-root /path/to/toolchain --puppeteer-root /path/to/renderer
```

公开矩阵还覆盖选择性停止、独立重复启动、名单复制／筛选／合并、非法槽与引用、清理及并发失败、父流程失败、未消费失败、外部 AbortSignal、无后续 join 的 workflow 收尾，以及普通／管理 Nodeset 任务目标。上述配置分别通过 Node.js 与真实 Chromium ESM 验证；web-app 使用同一公开管理流程验证失败通知和清理。

判定使用 trace 因果顺序；页面未处理异常单独收集。更细的屏障、SDK 操作 race、规则关闭后的权限、重复 512 个短任务和原生执行器边界见 `tests/targets/javascript/test_task_management.py`。Loop 目标覆盖位于 workflow_math 与 scheduled composite 测试；两 Target 的三种状态长标签图形在 `tests/tooling/test_task_manager_visuals.py` 中由真实浏览器检查。运行产物、依赖与探针证据均在仓库外临时工作区。
