# Python SDK JSON 默认值复现

本组独立观察 Python SDK 的只读声明、NodeRegistry 参数注册及正式 CLI。
探针使用 VibeFlow 与 Python 标准库；生成的 workflow 只读取参数并返回观察值。

在仓库根目录运行：

```bash
python -B sandbox/python/sdk_defaults/array_default_probe.py
python -B sandbox/python/sdk_defaults/default_types_probe.py
python -B sandbox/python/sdk_defaults/validate_probe.py \
  --work /tmp/vibeflow-sdk-defaults-probe \
  --report /tmp/vibeflow-sdk-defaults-probe.json
```

- `array_default_probe.py` 是最小例子：公开 SDK 声明 `array` 默认值 `[]`，
  从插件贡献取得 Descriptor，然后交给公开 NodeRegistry 注册。
  修复前打印默认值类型 `tuple`，随后报 NodeConfigError，退出码为 1。
  修复后声明仍为 tuple，注册成功，退出码为 0。
- `default_types_probe.py` 观察原上报的七类值，并增加浮点、null 和嵌套容器，
  共 14 个案例。每项保存原值、SDK 内部类型、声明导出、注册错误和原生 JSON 对照。
- `validate_probe.py` 在指定的临时目录生成九个独立插件/workflow，正式运行
  `validate`。成功案例继续执行 `run`，失败案例记录 `BLOCKED_BY_VALIDATION`。
  Node 与插件仍明确选择内置 Ruleset，各容器使用原本的 array/object schema。

后两条是调查脚本，退出码 0 表示观察完成。结果以每项 `status`、命令退出码、
正式诊断和运行状态为准。可用 `default_types_probe.py --report PATH` 保存结果。

## 修复前观察

基线为 `2ed8fc0`，观察保存于本目录：

| 范围 | 结果 |
| --- | --- |
| 原上报七类默认值 | 字符串、整数、布尔通过；空/非空列表及字典四项注册失败 |
| 扩展至 14 类值 | 5 项注册通过，9 项失败；浮点和 null 通过，嵌套容器也失败 |
| 原始 JSON 归一化对照 | 14 项均可接受，保留 list/dict 及嵌套原生类型 |
| 正式 CLI 的六个容器案例 | 退出码 1，诊断 WORKSPACE.LOAD，参数为 cleanup_record_roots |
| 正式 CLI 的三个标量对照 | validate 和 run 通过，执行轨迹包含真实参数观察 Node |

[注册观察](default-types-observations.json)及[CLI 原始报告](validate-observations.json)
保存每项结果；最小例子的原始输出见
[stdout](array-default.stdout.txt)与[stderr](array-default.stderr.txt)。

SDK 将 JSON 列表冻结成 tuple、对象冻结成 mappingproxy，声明的 `to_dict()`
可以递归导出为正常 JSON。NodeRegistry 却直接将冻结后的默认值交给
`normalize_node_config_spec`：array 判断只接受 list，而 JSON 快照校验不能序列化
mappingproxy，因而在注册阶段失败。

另外，修复前原生 JSON 对照显示 `merge_node_config` 的两次调用共享可变默认值：
修改第一份参数，会影响第二份参数及保存的默认值。报告单独标记了这一 Core
合并层的隔离失败。

## 修复后验收

Core 配置边界递归生成独立的原生 JSON 快照。SDK Descriptor 保持只读；
Python `run_pure` 每次调用取得独立配置，复用执行计划时也不共享可变参数。

```bash
python -B sandbox/python/sdk_defaults/default_types_probe.py --report /tmp/default-types-fixed.json
python -B sandbox/python/sdk_defaults/validate_probe.py \
  --work /tmp/defaults-cli-fixed --report /tmp/defaults-cli-fixed.json
python -B sandbox/python/sdk_defaults/runtime_isolation_probe.py \
  --work /tmp/defaults-runtime-fixed --report /tmp/defaults-runtime-fixed.json
```

运行隔离探针在 plan、block、compiled 三种模式中分别使用声明默认值、调用点
config 和运行器 override。每项连续执行同一个 Runtime 两次，再创建另一个
Runtime 执行；真实 Node 修改嵌套列表，并检查原生容器、保存的默认值、调用者
override 和只读 Descriptor。任一隔离失败会使该探针退出码非零。

修复后报告分别见[注册](default-types-fixed.json)、[CLI](validate-fixed.json)与
[运行隔离](runtime-isolation-fixed.json)。此前失败记录保留为历史对照。

[完整分发包复验](distribution-fixed.json)记录两个 profile 的包和内核 SHA256。
复验移除源码 PYTHONPATH，使用各自 `run.py`：六类容器默认值共 12 次正式
验证通过，嵌套数组和对象共 4 次实际运行通过。

`tests/core/test_node_config_snapshots.py` 与
`tests/targets/python/test_sdk_defaults_sandbox.py` 将这些期望接入正常回归测试：
注册、正式检查、实际参数及隔离必须通过；非法 JSON、循环值和 schema 类型
不匹配继续拒绝。完整验证入口会执行这两个测试文件。

[完整修复验收](verification.json)保存所测内核源码 SHA256、12 个验证阶段和案例数量。
