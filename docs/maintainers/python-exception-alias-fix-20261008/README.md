# F05 修复证据与重放

主记录见[Python 异常出口中的输入别名修复](../python-exception-alias-fix-20261008.md)。原[独立审核](../python-alias-facts-review-20261008.md)及两个原16项脚本不改写；本目录保存原脚本副本和独立 wrapper，所有期待保持原值。

修前 before-F05 固定334个产品文件，与上一轮 after-source-03 一致；原静态16与CLI16各有12项漏检。after-F05 是第一份中间335文件快照；即使它的核心701项通过，后来闭包反例仍否定其整体接受状态。最终使用 after-F05-02，完整335文件清单在 [after-F05-02-source-manifest.json](after-F05-02-source-manifest.json)。

源码最终[汇总](source-fixed-02-summary.json)包含701次核心回归与164项异常控制（112项原控制、52项追加），合计865次。raw36另计36次，保留4项普通未知 write 的旧期待差异；clear3保留1项既有误报，均不能写成原期待全匹配。[164项异常控制](source-fixed02-controls164.json)只读冻结数据，通过SDK、SourceContext及原生RulePlan检查finding、policy、参数证明与AST不变，不导入测试模块或运行业务定义。

以下从仓库根运行。每次使用新的work-root、tag和report路径，避免覆盖原证据。source路径指向包含vibeflow目录的唯一快照，manifest必须属于同一批次。

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/rockingsisyphus/.cache/vf-p2/t \
python -I -B docs/maintainers/python-exception-alias-fix-20261008/replay_frozen_products.py \
  --source dist/python-exception-alias-validation-20261008/after-F05-02 \
  --manifest docs/maintainers/python-exception-alias-fix-20261008/after-F05-02-source-manifest.json \
  --exception-controls docs/maintainers/python-exception-alias-fix-20261008/probe_exception_controls.py \
  --work-root dist/python-exception-alias-validation-20261008/source-new-replay \
  --report-dir dist/python-exception-alias-validation-20261008/new-reports \
  --tag source-new-replay
```

新wheel与两个kernel的实际行为重放使用`--gate`替代`--source`，显式指向本轮完成17阶段的隔离scratch。该目录内应有wheel-venv、distribution和distribution-autonomous；重放5373次回归检查及108次原始观察，不使用历史full-03。

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/rockingsisyphus/.cache/vf-p2/t \
python -I -B docs/maintainers/python-exception-alias-fix-20261008/replay_frozen_products.py \
  --gate /home/rockingsisyphus/.cache/vibeflow-exception-alias-20261008/full-01 \
  --manifest docs/maintainers/python-exception-alias-fix-20261008/after-F05-02-source-manifest.json \
  --work-root dist/python-exception-alias-validation-20261008/packages-new-replay \
  --report-dir dist/python-exception-alias-validation-20261008/new-package-reports \
  --tag packages-new-replay
```

`verify_product_bytes.py`要求显式gate、snapshot、manifest及新report，核对快照、安装wheel、whl、两个直接kernel与两份发行ZIP内嵌kernel共7集合的全部文件。行为重放前后各做一次；加载来源检查与字节相同都不能代替行为检查。

正式全量使用`python -B tools/verify_project.py --full`；源码、测试、工具、sandbox、quality、distribution及pyproject.toml的2340个 Git 可见验收输入，连同15个10月5日已存在且被 Git 忽略的历史日志，共2355个文件在 [full-01-inputs-before.json](full-01-inputs-before.json) 中冻结。旧清单为2336个 Git 可见文件，本轮增加4个 Python 文件；另外15项来自收集范围扩大。新的[full-01结果](full-01-result.json)为17/17通过、退出码0、pytest 4,534 passed；[批次后对照](full-01-inputs-after.json)无新增、缺失或字节变化。

三种新包各18组、1,791次回归检查已完成，合计54组、5,373次，所有组退出码0。包内原始108观察的已知差异继续单列，详见[包内汇总](packaged-validation-summary.json)和[实际执行命令](packaged-execution-commands.json)。完整7集合／各335文件在行为重放[之前](product-byte-proof-before.json)与[之后](product-byte-proof-after.json)均匹配；所有中间失败日志与摘要保留。
