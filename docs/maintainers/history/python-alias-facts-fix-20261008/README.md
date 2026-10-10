# F03/F04 独立行为重放

这里新增验证脚本和证据；原审核及其脚本保持原样。修复前唯一产品来源是本地提交 `5b9f9763ab7051fc964a4d83a1419d87a621b4c9` 的 Git 对象，不是并行修改中的工作区。334 个产品文件及原审核哈希见 `before-source-and-audits.json`。

`alias_facts_probe.py` 的固定矩阵共 128 项：27 项通过 public Core `compile_ruleset/execute_rule_plan` 的 ordinary PythonSource 路由，101 项逐案调用正式 Python CLI `validate`。Node、BaseLib、Plugin 的项目声明使用 canonical SDK 和配置字段，代码体只被验证、不执行业务。

- F03：四资源类型，list/set/dict/generator、lambda default、nested comprehension 的局部 `sys`／改名 `item`／真实宿主别名对照；局部属性读取和直接宿主读取控制。92 项。
- F04：Node `run_pure` 与 module helper 两条路径，global/nonlocal binder、direct/helper `pop`、owned 输入／普通局部字典对照；同名 caller local、lambda 参数、推导式局部输入控制。20 项。
- 普通 I/O 策略：四资源类型的局部 `sys`／`item` 属性别名 `write()`，分别使用 `none`／`python_io`。16 项。`none` 应拒绝未知普通 I/O，但不能冒认 `sys` 宿主；`python_io` 保持既有许可。

指定提交的 before 回放为 96/128 匹配、32 项不符：24 项 F03 局部对象误认宿主、4 项 F04 直接输入突变漏检、4 项未知 `write()` 冒认宿主。所有真实宿主负控、改名与无关局部控制、helper 输入突变负控均符合预期。334 个文件的运行前后哈希与 Git 对象一致，全部 101 个 CLI 子进程来源审查无外部产品模块。`--expect before` 只要求观测到不匹配，逐案 fixed 期待不会改变。

从仓库根目录重放（work 必须使用新目录，详细逐案 stdout/stderr 留在 ignored dist）：

```bash
TMPDIR=/home/rockingsisyphus/.cache/vf-p2/t python -I -B \
  docs/maintainers/python-alias-facts-fix-20261008/alias_facts_probe.py \
  --source dist/python-alias-facts-validation-20261008/before-5b9f976 \
  --work dist/python-alias-facts-validation-20261008/before-replay-new \
  --report dist/python-alias-facts-validation-20261008/before-replay-new.json \
  --expect before
```

修复后可指定唯一冻结源码的包含 `vibeflow/` 的根目录并使用 `--expect fixed`。同一脚本支持隔离生成包：

```bash
# wheel：使用正式 gate 生成的非 editable wheel-venv 解释器，不传 --source/--kernel。
FULL_GATE/wheel-venv/bin/python -I -B \
  docs/maintainers/python-alias-facts-fix-20261008/alias_facts_probe.py \
  --work dist/python-alias-facts-validation-20261008/wheel-replay-new \
  --report dist/python-alias-facts-validation-20261008/wheel-replay-new.json \
  --expect fixed

# 两 profile：分别使用各自的新 kernel ZIP，其他参数相同。
python -I -B docs/maintainers/python-alias-facts-fix-20261008/alias_facts_probe.py \
  --kernel FULL_GATE/distribution/kernel/vibeflow-kernel.zip \
  --work dist/python-alias-facts-validation-20261008/collaborative-replay-new \
  --report dist/python-alias-facts-validation-20261008/collaborative-replay-new.json \
  --expect fixed
# autonomous 改为 FULL_GATE/distribution-autonomous/kernel/vibeflow-kernel.zip。
```

`FULL_GATE` 替换为根节点统一协调的新正式验收目录。新正式完整 gate 通过后，可运行 `bash docs/maintainers/python-alias-facts-fix-20261008/replay_products.sh /absolute/FULL_GATE`，完整收集三个产品的正式矩阵和原36项脚本。

原36项脚本包含局部 `alias.write()` 在 `none` 下预期完全无 finding 的案例。身份修复后，既有未知 I/O 叶策略仍可能正确产生普通 I/O finding。因此 `replay_original_alias_review.py` 保留原输出和原期待，在另一份 origin JSON 里分类宿主诊断、输入诊断和普通未知 `write()`。不会把这类历史期待不一致改写成“36/36”。修复前原36项为18不符，见 `legacy36-before.json`；最终源码原期待4项不符，全部为普通未知 `write()`，其他语义差异为0，见 `source03-original36-origin.json`。

最终产品源码固定为 `after-source-03`，334文件清单见 `after-source-03-manifest.json`。前两份快照保留求值顺序与 nested binder 暂态输入残留的中间观察，不代表最终版本。最终源码共669次独立检查，回归检查差异为0；clear3的1项原语义边界单列，原36另计36次观察。实际产品模块来源均在选定快照中，详见 `source03-summary.json`。新包使用正式全量 full-03 生成的产品，17/17通过、退出码0，见 `full-03-result.json`。

## 独立补充矩阵

`packaged_writeback_probe.py` 的原 91 项逐字节保存；最终扩展版另存为 `packaged_writeback103_probe.py`，保留原 91 项并增加 12 项末态与提前／异常出口控制，共 103 项。它们通过 SDK → RulePlan 验证输入归属、控制流和已求值接收者。`replay_input_evaluation_review.py` 提供唯一产品来源的适配入口，通过 AST 读取保存的原脚本 literal，不改案例或期待；支持 `--source`／`--kernel`／非 editable wheel 和以下 `--review`：

- `evaluation12`：原 12 项接收者／下标／位置与关键字参数求值顺序。
- `nested_clear3`：原 3 项 nested clear，包括这次新增的同调用内先写 owned、再覆盖局部字典回归。单独调用 clear 的原始期待为允许，而不可变基线 `5b9f9763ab7051fc964a4d83a1419d87a621b4c9` 与中间版本均保守拒绝；raw 原期待及不匹配保留，另用该基线观察核对这个既有边界，不把它算作新增修复通过。
- `writeback_exits3`：原 3 项 return／raise／可能抛错调用之前已经写入的输入别名。
- `writeback_exits5`：独立新增 5 项，在保留原 3 项的同时增加下标／属性查找可能抛错的控制。原 3 项脚本与期待保持原样，两个矩阵分别报告。

原脚本、before／中间证据以及逐字节保存哈希见 `additional-independent-probes.json`。固定基线 `5b9f9763ab7051fc964a4d83a1419d87a621b4c9` 重放表明：evaluation12 原3项不匹配；nested_clear3 原1项不匹配属于上述既有边界；writeback_exits3 原3项漏检。最终源码的 evaluation12、writeback103、writeback_exits3／5全部匹配，nested_clear3保留1项旧边界而新增回归差异为0；各份来源与逐案证据分文件记录。

```bash
python -I -B docs/maintainers/python-alias-facts-fix-20261008/replay_input_evaluation_review.py \
  --source /absolute/FROZEN_SOURCE --review evaluation12 --expect fixed \
  --report /absolute/NEW_REPORT.json
```

`replay_products.sh` 已纳入新增的 128／103／12／3／3／5 项以及未改变期待的原 36 项，三产品失败也会完整收集。103 项包含原 91 项，不重复计数。所有探针只分析业务代码体，不运行其中的 host 操作或输入突变。

## 旧矩阵的包级回归入口

新正式完整 gate 通过后，运行：

```bash
bash docs/maintainers/python-alias-facts-fix-20261008/replay_old_products.sh /absolute/FULL_GATE
```

该入口对 fresh wheel、collaborative kernel、autonomous kernel 各运行原 F01 40／正式72、原 F02 180／正式89、声明归属34、Python效果873、输入合同20、JS参数33，共 `1341×3=4023` 项。原矩阵、期待与旧审核不修改，失败也会完整收集。逐案项目与日志放在 ignored `dist/python-alias-facts-validation-20261008/old-package-probes/`。

所有可执行脚本依赖都保存在项目 docs 目录。输入20与效果873从此前独立脚本逐字节保存；JS33仅因脚本移到 docs 而修正 checkout 来源守卫的父目录层级，33项案例与期待不变。效果873命令显式拒绝仓库 `src` 来源，所有入口统一 `-I -B` 并记录实际产品模块来源。保存/调整哈希见 `preserved-probe-scripts.json`。它们不会依赖 ignored dist 中的旧验证脚本，也不导入源码 tests。JavaScript 使用该 fresh gate 的 `pytest/javascript-toolchain`，属于 gate 生成的真实运行依赖。

最终 full-03 已通过，两个入口已对其 fresh wheel、collaborative kernel、autonomous kernel 实际执行，所有45个探针组成功退出。三产品共4785次检查，另计108次原36观察；raw36每产品4项普通未知write差异、clear3每产品1项既有误报边界单列，不声称原期待全部匹配。逐案、产品来源与完整统计见 `packaged-validation-summary.json`。

`verify_final_product_bytes.py` 仅用标准库，比较冻结快照、wheel安装目录、whl、两个直接kernel及两个发行ZIP内嵌kernel的全334文件清单。重放前后分别保存 `product-byte-proof-before.json` 与 `product-byte-proof-after.json`，7份集合均逐字节一致，profile、版本和元数据同时匹配；安装产生的pyc单列记录。重放命令中的正式gate目录为 `/home/rockingsisyphus/.cache/vibeflow-alias-facts-20261008/full-03`。

原审核3项及docs保存的脚本／补充证据均按保护清单核对。原91项脚本保存在本目录；ignored dist中的临时探针路径后来用于103项扩充版，旧路径的哈希差异如实保留，不能推导成所有临时原路径都未改变。

## 目录用途与边界

仅用于：历史专题 python-alias-facts-fix-20261008 的可阅读审核、修复与决策记录；保持当时口径，不追加机器输出或用作当前规范。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../directory-layout.md)。
