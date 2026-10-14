# 0.19.0 本地发布包构建与验证

2026-10-14，用户在原生任务管理实施完成后授权构建新发布包，并指定版本为 0.19.0。此前“不发布版本”的实施范围至此扩展为构建本地发布包，不包括 GitHub 发布、push/tag 或升级 ERA/GSKO。

## 版本与行为

版本唯一来源 `pyproject.toml` 更新为 0.19.0，中文/英文 README 与发行维护说明同步。Workflow ABI 为 `vibeflow.workflow.v6`；AOT manifest 仍为 `vibeflow.aot-build.v2`。管理 Node 使用有限声明目标与普通 TaskRef 数组，workflow 在所属任务实际执行和清理完成后退出。旧 `async/result_key/detached` 调用入口须显式迁移，不提供自动转换。接口详见[原生任务管理](../../../distribution/docs/user/task-management.md)。

## 构建产物

运行仓库现有入口 `python -B distribution/build.py`，默认事务构建两种 profile，内置仓库质量、文档与清单装配、kernel 校验、Python 最小项目验证及执行、ZIP 内容验证均成功。

- `dist/vibeflow-distribution-0.19.0.zip`：collaborative 人机协同开发包。
- `dist/vibeflow-distribution-autonomous-0.19.0.zip`：autonomous 无人值守开发包。
- 对应展开目录为 `dist/vibeflow-distribution` 与 `dist/vibeflow-distribution-autonomous`。
- 沿用已有交付约定，校验值记录于 `dist/SHA256SUMS-0.19.0.txt`；0.18.3 原 ZIP 由构建器归入 `archive`，其原校验清单随之保存，未改写旧记录。

构建日志为 `/home/rockingsisyphus/.cache/vibeflow-task-management-20261014/release-0.19.0-build.log`。ZIP、展开目录与依赖不提交 Git。

## 实际解压包验证

从两个正式 ZIP 分别解压到仓库外 `/home/rockingsisyphus/.cache/vftm/r190`，使用各包自己的 `run.py`，移除环境中的 `PYTHONPATH`，验证脚本不从源码树导入内核。测试配置使用公开沙箱，但执行内核来自发布包。

共 25 项检查通过，报告为该目录下 `report.json`，脚本为 `verify.py`，各命令输出单独保留为日志：

- ZIP 可完整读取，metadata 版本/profile 正确，包含 Python/JS 任务运行器资源。
- 两种包均通过 `verify-kernel`、Python 最小项目 validate/run、JS npm 安装、Node ESM 构建与实际执行。
- 两种包均以 Python plan/compiled/block 执行公开任务管理 failure 场景：B 的 finally 清理结束后才收到失败结果，三个任务实际退出。
- 两种包均以 JS Node ESM 构建并执行同一任务管理场景：结果为 cancelled/failed/cancelled，B 清理早于通知，三个任务实际退出。
- 两个 profile 的内核 ZIP 字节相同。

本次是新发布包的解压验证，未重新执行整个仓库或真实浏览器全矩阵；源码与浏览器完整验收引用此前独立的 full-04 批次（18/18 步通过、4452 pytest 通过），见[实施记录](task-management-implementation-20261014.md)。版本及维护文档更新不修改运行逻辑，也不覆盖此前失败记录。

## 成本、目标与路线复核

沿用项目已有构建工具与两种 profile，没有新增发布流程或资格门禁。新版本保留普通数组、实际退出后通知及统一收尾；结果缓存仍随本次 workflow 累计任务数和输出大小增长，双圆形完整长标签仍以增加留白为代价。解压执行支持原目标，未出现需要改变路线的新证据。后续下游迁移与外部发布另按用户请求开展。
