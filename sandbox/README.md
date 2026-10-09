# VibeFlow 真实使用沙盒

沙盒按 Python 与 JavaScript 两个 Target 组织，直接使用工作区 src。项目通过公开 SDK、配置和正式 CLI 模拟用户接入；运行输出与依赖放入临时工作区，不留在案例目录。

| 场景 | Python | JavaScript |
| --- | --- | --- |
| 最小接入 | [minimal](python/minimal/README.md) | [minimal](javascript/minimal/README.md) |
| 完整工作流、CLI、宿主与生命周期 | [integration](python/integration/README.md) | [integration](javascript/integration/README.md) |
| 领域插件与真实数值 | [domain_rules](python/domain_rules/README.md) | javascript/domain_rules |
| 外部规则、资料传递与局部覆盖 | [rule_graph](python/rule_graph/README.md) | [rule_graph](javascript/rule_graph/README.md) |
| 多文件 Node、库、Plugin 与 Host | [multifile_resources](python/multifile_resources/README.md) | [multifile_resources](javascript/multifile_resources/README.md) |
| 运行日志、状态与异常 | [runtime_observation](python/runtime_observation/README.md) | [runtime_observation](javascript/runtime_observation/README.md) |

错误配置、运行异常和资源释放属于真实使用场景。内部缓存次数、AST/对象身份、历史实现对照及专门的布局回归属于 tests/fixtures，由功能测试或完整仓库验证入口执行，仍保持原覆盖。

## 验证

```bash
python tools/verify_project.py --full
```

单独运行两 Target 的主要沙盒：

```bash
python sandbox/python/integration/run_all.py
python sandbox/javascript/minimal/run_e2e.py
python sandbox/javascript/integration/run_all.py --puppeteer-root /path/to/renderer
```

默认运行自动清理临时工作区。需要检查产物时使用 runner 的显式工作目录或 --keep-artifacts，目录放在仓库外，检查后及时清理。

覆盖入口见 [TEST_COVERAGE](TEST_COVERAGE.md)，目录职责见 [开发说明](../docs/maintainers/directory-layout.md)，历史原始观察见 [证据索引](../docs/maintainers/evidence/index.md)。
