# 集成沙盒

这个目录模拟真实业务项目使用 `topology-kernel` 的方式：业务侧只编写 node、受控 `base_lib`、插件、boundary 和 JSONC 配置；内核通过 `kernel/topology_kernel` 软链接进入项目。

运行：

```powershell
python examples\integration_sandbox\run_all.py
```

脚本会自动创建或刷新 `kernel/topology_kernel` 软链接，批量运行合法配置、非法 node、非法 `base_lib`、非法配置和非法插件，并输出：

- `reports/summary.json`
- `reports/summary.md`
- `reports/mermaid/*.mmd`
- `runs/<case_name>/...`

退出码：

- `0`：全部预期通过。
- `1`：合法 case 失败，或非法 case 未被拒绝。
- `2`：环境错误，例如无法创建软链接或 junction。

本目录包含故意违规的 Python 文件，用于验证内核能拒绝坏代码。因此仓库级通用质量自检默认排除 `integration_sandbox`，避免把反例 fixture 当成内核自身质量问题。
