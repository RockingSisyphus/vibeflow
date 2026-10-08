# RuleContext 共享对象图沙箱

`probe.py` 直接使用公开 RuleContext，不导入业务项目、Torch 或 VibeTrain。输入每层只有一个不同 tuple，两个位置引用同一个子对象；另外对照 list、mapping、dataclass、普通服务对象及混合容器。

```bash
python -B sandbox/python/readonly_graph/probe.py --report /tmp/readonly-sharing.json
python -B sandbox/python/readonly_graph/probe.py \
  --kernel dist/vibeflow-distribution/kernel/vibeflow-kernel.zip \
  --depths 4 8 12 16 20 32 64 --report /tmp/readonly-release.json
```

不匹配返回非零。判断依据是共享身份、不同对象数量、嵌套只读性和快照隔离；时间仅供观察。pytest 深层案例用实际遍历次数限制检测重复展开，避免错误实现生成不可控的大树。

`before.json` 与 `released-before.json` 保留修复前源码及报告中原始内核 ZIP 的观察；`after.json` 与 `released-after.json` 记录修复后结果。原始内核 SHA256 为 `e3a964f1804e01eb7a9d4b121cd53b7393d662347a77b3cbeb9f6618130d5095`。普通服务对象保留原实例；此对照不把服务对象的内部状态声明为冻结资料。

`project_validate_probe.py` 可复查已有真实工作流，只执行 validate，将完整 CLI 输出、诊断数量、退出码和耗时保存到指定目录：

```bash
python -B sandbox/python/readonly_graph/project_validate_probe.py \
  --kernel dist/vibeflow-distribution/kernel/vibeflow-kernel.zip \
  --workspace /path/to/project/vibeflow_config.jsonc \
  --config /path/to/project/project/configs/mnist_example.jsonc \
  --report /tmp/mnist-validation.json --timeout 180
```

观察脚本退出 0 表示拿到了结构化报告，业务项目是否通过须读取其中的 `status/exit_code/errors/warnings`。这个工作流观察不执行训练。内置动态调用分析还由 `test_runtime_dispatch.py` 验证：读取 Target 自有 AST 时不调用复制 getter，分析前后原树相同；公开 getter 返回的树仍可独立修改。
