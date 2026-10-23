# 三个独立 Workflow 联合求值（Python）

本目录只负责官方 workflow 协作的真实数学项目。业务节点在 `project/`；三个图由两 Target 共用的 `tests/fixtures/support/workflow_cooperation.py` 生成，避免维护两套公式、图和预期值。运行器复制发行包的官方 Call、Send、Receive、InvokeSync、Wait 模板，不维护自定义协作协议。

A、B 为 async workflow，C 为 sync workflow，各自拥有独立身份和多个数学节点，命名入口均为 `calculate`：

1. A 计算 `u=3x+y`、`v=y-4`，Call 启动 B，再发送 `{u,v,case_id}`；本地计算 `r=7x-3v`。
2. B Receive 后用 InvokeSync 调用 C。C 分三个节点计算 `t=u-2v`、`s=t²`、`p=s+5v`，立即返回普通输出。
3. B 计算 `b=2p-u`，向 A 回复；A Receive 后计算 `q=b-r`，再发送给 B。
4. B Receive 第二轮输入，计算 `d=q+2v` 并结束；A Wait 取得真正终态及输出，计算 `F=3d+u`。

B 的第二轮使用同一实例内的 Nodeset：保留首轮输入、调用官方 Receive，再求 `d`。这避免在同一图中重复声明官方 Receive 的固定输出 key；没有新增 workflow 或协作执行器。所有数据边显式连接，第二轮不会消费首轮的同类型数据。

整体公式：`F=6(3x-y+8)²-27x+43y-180`。宿主使用独立展开式 `54x²-36xy+6y²+261x-53y+204` 核对答案，不复制业务调用链。

| 输入 `(x,y)` | 答案 |
|---|---:|
| `(2,7)` | 361 |
| `(5,1)` | 2632 |
| `(0,0)` | 204 |
| `(-4,3)` | 351 |
| `(0.5,-1.25)` | 446.125 |

每次同时启动这五组计算，检查所有中间值、消息轮次与发送者、case_id、十五个独立身份、重复读取 B 终态、记录释放及宿主关闭。单独调用 C 必须立即返回且不留记录；通过 InvokeSync 调用异步 A 必须拒绝。

源码和移除原项目后的 AOT 均运行 `plan/block/compiled`。另外构建四个故意算错的 A：首轮交换字段、误发原始 x、第二轮漏减局部项、把首轮回复当成终态输出。对 `(2,7)` 必须分别得到 **3631、196、376、358**，且均与正确值 361 不同，证明判据确实能发现这些故障。故障参数只属于此沙箱业务节点。

运行：

```bash
python sandbox/python/workflow_cooperation_math/run_all.py --work-dir /path/to/new-work-directory
```

默认临时工作目录自动清理。显式工作目录保留 `report.json`、`artifacts/` 下的构建产物和真实运行记录；原项目会在 AOT 验证前移除。Python integration 与根目录 `python tools/verify_project.py --full` 自动包含本入口。

JS 版的同一公式还在 Node 与真实无头 Chromium 的离线页面运行，见[对应沙箱](../../javascript/workflow_cooperation_math/README.md)。HTTP、跨语言进程协作、取消清理和错误传播由原有专项测试继续覆盖；本项目不代表 ERA 生产验收。
