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
