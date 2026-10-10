# 失败示例集

`cases.jsonc` 描述典型违规示例。测试会将这些示例物化到临时目录并确认内核能给出稳定失败规则。

覆盖范围：

- 巨型 node。
- 隐藏副作用。
- 动态导入。
- node 互调。
- module 顶层副作用。
- 未声明环路。
- 非法 boundary。
- `base_lib` 逃逸。
- policy 豁免/降级后处理。
- decision loop 缺少出口。
- explicit edge 重复/冲突。
- quality-check 宽参数、top offenders、score、side-effect alias、敏感文件跳过。
- optional architecture report 不进入 hard gate。

## 目录用途与边界

仅用于：project_quality 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../docs/maintainers/directory-layout.md)。
