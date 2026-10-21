# Python SDK JSON 默认值复现

本组独立观察 Python SDK 的只读声明、NodeRegistry 参数注册及正式 CLI。
探针使用 VibeFlow 与 Python 标准库；生成的 workflow 只读取参数并返回观察值。

在仓库根目录运行：

```bash
python -B tests/fixtures/python/sdk_defaults/array_default_probe.py
python -B tests/fixtures/python/sdk_defaults/default_types_probe.py
python -B tests/fixtures/python/sdk_defaults/validate_probe.py \
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

## 目录用途与边界

仅用于：sdk_defaults 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
