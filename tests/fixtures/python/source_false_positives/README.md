# Python 源码误报回归

本沙箱使用标准库和公开插件 SDK 构造独立 workflow，经正式 `validate` 检查，无需 VibeTrain、Torch 或业务数据。33 个稳定案例覆盖局部变量与模块同名、纯路径类、已登记 helper 的名称、继承入口及真实违规对照。四个合法案例还执行正式 `run`，确认目标 Node 实际执行。

```bash
PYTHONPATH=src:. python -B -m tests.fixtures.python.source_false_positives.probe \
  --work /tmp/vf-source-false-positives --report /tmp/vf-source-false-positives.json
```

工作目录每次使用新路径。任一预期不匹配，脚本返回非零。负例断言目标诊断、严重度、源码位置和退出码，没有用声明加载失败代替目标检查。`tests/targets/python/test_source_false_positives.py` 将全部案例纳入常规回归，还检查 C3 多继承、方法遮蔽、循环及冲突的源码事实。

| 案例 | 目的 |
| --- | --- |
| `node_local_*`、`library_local_*` | 局部 list/dict 的 requests.append/get 不因名称撞上网络库而报错；覆盖模块别名被局部变量遮蔽 |
| `node_pure_*`、`library_pure_path` | PurePath、PurePosixPath、PureWindowsPath 及别名只做路径运算；真实 Path IO、网络调用及 PurePath 被替换成 open 仍报错 |
| `library_named_*` | 已取得源码的 reset/close helper 根据函数体审查；真实 random.seed 和 open 仍报错 |
| `inherited_*`、`missing_method` | 同文件、跨文件和菱形继承、子类覆盖父类；继承的 print、async 和错误签名在实际实现位置报错 |
| `decision_*` | flow.backend 可表达路由输出；普通结果字段仍触发路由声明诊断 |
| `missing_output_branch`、`file_over_limit` | 保留缺失输出和默认逐文件大小限制 |

`before.json` 在修复前源码快照上观察，21/33 案例不符合预期；`after.json` 保存修复后的完整 CLI 结果，33/33 符合预期，四个实际运行均通过。`--kernel` 可以指定含 src/vibeflow 的源码树，`--validate-only` 用于历史静态观察。

`mnist-observation.json` 与 `mnist-report.json` 保存原 VibeTrain MNIST 配置的正式复查结果。观察时使用本仓库源码内核，没有修改该项目的源码、配置或安装内核，没有执行训练。报告中的项目 FAIL 与观察脚本是否完成分别记录。

实际配置约 127 秒返回完整报告，错误从 52 条减少到 31 条，警告仍为 91 条。已确认的误报及连带诊断消除 21 条。剩余报告包括文件超限、一个返回分支缺失输出、ExecutionScope 的副作用及其连带诊断、自定义规则 deepcopy 冻结资料失败；这些不能由最小复现通过推定为已解决。`verification.json` 记录验证命令、计数与边界。

Core 与 Python 回归为 770 passed / 5 skipped；跳过项为既有的 SVG 渲染器测试，本轮 33 个沙箱案例全部执行。仓库独立质量为 0 errors / 0 warnings，其自身测试为 46 passed。本轮未重建发行包，也未执行完整跨 Target、浏览器及发行验证。

历史生成报告和截图已移出夹具目录，原始位置与恢复方法见 [证据索引](../../../../docs/maintainers/evidence/index.md)。上文历史成绩不代替当前运行。

## 目录用途与边界

仅用于：source_false_positives 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
