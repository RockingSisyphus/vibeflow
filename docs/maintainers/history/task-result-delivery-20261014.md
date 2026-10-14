# 0.20.0 任务结果一次交付与回收

2026-10-14，用户确认子任务只负责执行、返回结果和退出；领取后的结果由父流程保存和转交，不再通过 TaskRef 重复查询。随后授权修改。本轮在已有启动、等待、停止与实际退出边界内实现自动回收，没有新增手动 release 接口。

## 当前合同与实现

- 子任务执行、finally、SDK 操作和受管后代全部结束，才产生可领取的最终结果。已经结束但尚未领取的结果仍保留，支持 B 先结束、父流程稍后来取。
- `waitAny` / `wait_any` 返回一个最终结果并消费该任务；`waitAllExited` / `wait_all_exited` 返回整批结果并消费对应任务。接收者保存普通结果数据；名单只保存尚未领取的引用。
- 领取后框架移除任务登记。同一引用及其复制品再次等待或请求停止，报 `VF_TASK_REF_INVALID`。领取前请求停止已经退出的任务仍返回 `already_exited`。
- 重叠等待只有一个接收者成功；整批交付先检查全部记录，不能在发现某张任务卡已消费时悄悄丢失其他结果。父流程退出仍停止并等待剩余任务，报告未领取失败，再退休其记录。
- Python 使用单调递增任务编号，删除记录后不复用 ID；子 trace 在领取或 drain 时合并到运行 trace，不再由 `_completed_traces` 长期持有。JS 删除 records Map 中的已交付条目。历史 trace 与父流程持有的数据仍可能增长，本次不宣称整个 workflow 为常量空间。

运行器修改集中在 Python `runtime/tasks.py` 和 JS `resources/task_helpers.mjs`。两侧公开 task_management 沙箱改用待领取名单和已领取结果两路数据，普通 relay Node 转交结果。声明类型、使用手册、当前设计与 README 同步。旧版本依赖重复等待的项目须迁移；Workflow ABI 仍为 v6，配置形状不变。

退出 trace 回调可能重入等待并随后失败。低成本真实生成 JS 探针发现旧实现先发布成功 outcome，再处理 trace 错误，接收者可能取得暂定成功结果。两侧改为退出 trace 处理完毕后发布最终 outcome，新增 JS 重入回归。原失败证据保存在 `/home/rockingsisyphus/.cache/vftm/consume-trace-reentrance01/`，未覆写。

## 验证与历史失败

证据总目录为 `/home/rockingsisyphus/.cache/vftm/`，不提交依赖、生成项目或运行资产。

| 独立批次 | 结果 | 证据 |
| --- | --- | --- |
| 初次定向 | 23 passed | consume-tests01.log |
| 扩展并发与迟领定向 | 26 passed | consume-tests02.log |
| Python 公开沙箱 | 54 项通过 | consume-python-public01/report.json |
| JS 公开沙箱 | 46 项通过，真实 Chrome | consume-js-public01/report.json |
| 使用手册实际项目 | Python 三模式与 JS 构建/运行通过 | consume-doc-examples.log |
| 全量第一轮 | 17/18 步通过；pytest 4448 passed、9 failed | consume-full01/verification.json、consume-full01.log |
| 集中修复后的定向 | 46 passed | consume-tests03.log |
| 全量第二轮 | 18/18 步通过；pytest 4458 passed | consume-full02/verification.json、consume-full02.log |

第一轮 9 项失败均为代表性 JS 发射源码的旧 golden SHA；逐项确认声明与计划哈希不变，仅更新受运行器变化影响的 9 个源码哈希，没有删断言、改输入或关闭规则。该批次冻结源码并完成全部步骤后，集中处理 golden 和退出回调问题；定向通过后重新运行第二轮。第二轮是独立成绩，不覆盖第一轮失败。

第二轮还通过 Python integration 104/104、JS integration 50/50（无跳过）、规则对照 1223/1223、资源回归 680/680、适配 207/207、浏览器观测、布局、双侧性能、wheel 隔离和两种 profile 打包检查。两侧 1024 个短任务分 16 批创建和接收，workflow 尚未退出时每批任务登记表已为空；返回数据仍可读，旧引用无效，新 ID 不复用。另覆盖迟领、重叠接收和批次交付不部分丢失。

## 执行中的成本、目标与路线复核

沿用两个等待入口作为结果交付边界，减少业务手动清理和遗漏回收的维护负担。父流程显式保管普通结果，不要求子任务猜测是否还有使用者。公开场景与压力回归支持这一机制，没有引入新控制边界。完整验证成本主要来自既有资源编辑、展示与安装链路；第二轮全量前先完成定向验证，全量运行期间冻结修改。后续若要限制历史 trace 或父流程结果缓存，应按各自存储职责处理，不能把这次任务卡回收当作其内存保证。

本地发布包使用已有 `distribution/build.py` 构建 0.20.0；构建与实际解压验证结果另记下节。不包括 push、tag、GitHub 发布或下游项目部署。

## 本地发布与实际解压验证

执行 `python -B distribution/build.py` 成功，生成 collaborative 和 autonomous 两个 0.20.0 目录与 ZIP。构建日志为 `consume-release020.log`。旧 0.19.1 ZIP 由构建器移入 archive，其原校验清单一同保存；新校验值记录于 `dist/SHA256SUMS-0.20.0.txt`，不覆写历史哈希。

分别从正式 ZIP 解压到 `/home/rockingsisyphus/.cache/vftm/r020/`，移除 PYTHONPATH，使用各包自己的 run.py。25 项通过，覆盖版本/profile、内核、Python 最小项目、JS 安装及真实执行、Python 任务场景三模式和 JS 任务场景、两 profile 内核一致；任务沙箱会断言旧引用已失效。报告为 `r020/report.json`，脚本为 `r020/verify.py`，命令日志独立保留。

直接读取解压包用户手册中的代码构成实际项目，包内内核下 Python plan/compiled/block 与 JS 构建/运行共 5 项通过，报告为 `r020/handbook-projects/report.json`。验证脚本初次有 pathlib 名称引用错误，尚未进入产品执行；修正脚本后通过，原 `r020/handbook.log` 与复验 `r020/handbook02.log` 均保留。两包 task-management 使用手册与 canonical 文档字节一致，内部历史文档未进入用户包，见 `r020/documents.json`。

运行器没有在全量第二轮之后修改；其后只补维护记录、导航与机制说明，并重新执行最终仓库质量检查。源码和发布产物的验证保持各自独立分母。
