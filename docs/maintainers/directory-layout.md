# 仓库目录职责

| 位置 | 所有者与内容 |
| --- | --- |
| 根目录 | 项目入口、许可证、构建与 Git/CI 元数据；不保存临时脚本或运行输出 |
| src/vibeflow | Core、BlockCompiler、Builtin、Python/JavaScript Target、Tooling 的核心源码及运行资源 |
| distribution | 构建器、profile 配置、提示词、项目模板、最小项目和 distribution/docs 用户文档原稿 |
| dist | 最新正式发行目录、对应 ZIP 和校验清单 |
| archive | 被替换的历史发行 ZIP；同版本不同构建可保存在 history 下 |
| sandbox/python、sandbox/javascript | 公开 SDK/CLI 与真实宿主环境中的使用项目，直接加载工作区 src |
| tests | 非沙盒功能、代码、集成、一致性和实现回归；fixtures 保存输入、基线和独立回归 runner |
| quality | 独立的仓库质检工具及其自身测试，不进入产品发行包 |
| references | 外来参考项目，不作为生成产物仓库 |
| tools | 开发、验证、清理和辅助工具 |
| docs | 当前设计、维护说明、执行计划、历史结论与证据索引；图片等正文资源放在 assets |

## 产物与证据

测试、依赖安装和临时构建默认使用自动清理的仓库外工作区。显式保留的工作目录由调用者负责结束后清理，不能放在 dist、archive 或案例源码目录中。

历史审核材料保存于仓库旁的 `VibeFlow-evidence/directory-remediation-20261009`；[索引](evidence/index.md) 记录原位置、大小、SHA-256 和恢复方法。退休测试原稿和原始失败观察属于历史材料，不重新进入测试发现范围。

测试使用的 `tests/fixtures/rule_parity/reference.json` 是输入基线，必须随代码保留；它与一次运行生成的报告有不同用途。不能只根据扩展名认定文件可删。

## 发行

默认构建的两个目录及 ZIP 都进入 dist。正式替换时，被替换的 ZIP 进入 archive；已有同名历史包的内容不覆盖。同版本重建也保存先前字节。生成、验证或事务发布失败时，恢复先前正式产物。

目录整改只搬迁既有 0.15.2 正式 ZIP，并核对其与既有发行目录逐文件一致；当前 0.17.0 源码的验收包在隔离工作区构建，不由目录整改自动提升为正式版本。
