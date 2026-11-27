<!-- vibeflow-directory-purpose -->
# 中文数学综合示例

计算整数函数 `f(x, y) = (x + y) × (x + y + 1) + 2 × (x − y) + x² + y² + |x − y|`。

- [计算完整公式](project/configs/计算完整公式.jsonc)分三路。一条把 `s = x + y` 交给另一个 Workflow，一条在本地算 `2 × (x − y)`，一条用 Nodeset 算平方与差距项。三项都完成后相加。
- [计算相邻整数乘积](project/configs/计算相邻整数乘积.jsonc)只接收 `s`。先算 `s + 1`，再与 `s` 相乘，将乘积交回主流程。
- [独立计算平方与差距](project/configs/独立计算平方与差距.jsonc)有自己的双整数入口，直接复用 [平方与差距 Nodeset](project/configs/nodeset_types/平方与差距.jsonc)，把 `x² + y² + |x − y|` 当作完整结果。

两个调用点导入同一个 Nodeset 定义。Nodeset 里和主流程顶层的「求两数之差」也引用同一个 Node 定义。两处使用相同的输入与输出类型，差值在顶层用于加倍，在 Nodeset 内用于取绝对值。

本目录保存三个可执行工作流与本地计算应用。审核图、构建、日志和测试副本放在仓库外。

## 运行

在仓库根目录执行端到端测试：

```bash
python tools/run_tests.py -- tests/e2e/test_two_workflow_formula.py
```

手动试用时，在 VibeFlow 已安装的 Python 环境中，将本目录复制到临时工作区，进入副本后生成审核图：

```bash
python -m vibeflow review --workspace vibeflow_config.jsonc --config project/configs/计算相邻整数乘积.jsonc
python -m vibeflow review --workspace vibeflow_config.jsonc --config project/configs/计算完整公式.jsonc
python -m vibeflow review --workspace vibeflow_config.jsonc --config project/configs/独立计算平方与差距.jsonc
```

打开 `vibeflow-preview.html`。在「计算完整公式」里，右键「交给另一流程计算乘积」可以跳到乘积流程，右键「计算平方与差距项」可以原地展开 Nodeset。在独立流程里右键「复用『平方与差距』」，也能展开同一个定义。

执行完整公式：

```bash
python -m vibeflow build --workspace vibeflow_config.jsonc --config project/configs/计算相邻整数乘积.jsonc --out-dir build/product
python -m vibeflow build --workspace vibeflow_config.jsonc --config project/configs/计算完整公式.jsonc --out-dir build/formula
python calculate.py --build-dir build --x 5 --y 2
```

输出为 `{"乘积项":56,"差值项":6,"平方与差距项":32,"结果":94}`。

只执行复用 Nodeset 的独立流程：

```bash
python -m vibeflow build --workspace vibeflow_config.jsonc --config project/configs/独立计算平方与差距.jsonc --out-dir standalone/score
python calculate.py --build-dir standalone --square-gap-only --x 5 --y 2
```

只加载 `standalone/score` 构建目录，输出 `{"平方与差距项":32}`。
