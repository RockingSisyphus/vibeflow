# 项目治理重构验证索引

原始批次保存在仓库旁的持久目录 `/home/rockingsisyphus/projects/VibeFlow-evidence/project-governance-20261021`。所有阶段失败和后续定向复验分别保留，不以新通过覆盖旧失败。原件未随发行包分发；临时工作目录已按批次清理。

- `project-governance-*.json`：基础、扩大与定向批次，以及浏览器、性能观察。
- `full-01/verification.json` 与 `full-01/full.log`：首轮18阶段完整门禁，15阶段通过，pytest、distribution、repository-quality-final未通过。
- `full-01/*.json.gz`：完整规则、补充及适配观察原件；匹配分别1116/1116、194/194、173/173。

首轮pytest为4648通过、5失败。发行失败原因是原始证据曾错误放入文档目录，后续应归位证据并复验，不能取消目录质检。最新结论见[实施记录](../project-governance-refactor.md)。

集中修复复验：`focused-36.json`为57/57；`runtime-observation-02.json`、`distribution-02.json`及`static-08.json`记录对应通过结果。后续最终完整批次单独存放，不改写首轮失败。

第二轮：`full-02/verification.json`记录17/18阶段通过，唯一失败为文档总目录漏链；pytest4652通过、1失败。完整原始日志及三个矩阵的压缩观察位于同目录。

最终验收：`full-03/verification.json`记录18/18阶段通过，`full-03/full.log`记录正式入口和全部输出，合计约1252.30秒，默认12并发。pytest4653/4653、规则1116/1116、补充194/194、适配173/173；两端沙盒、真实浏览器、性能、sdist/wheel、两个profile及最终质检/清理均通过。`focused-37.json`为补齐文档总目录后的49/49定向复验。本索引不把首两轮失败改成通过。
