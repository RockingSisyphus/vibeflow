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

## 目录用途与边界

仅用于：source_false_positives 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
