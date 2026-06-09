# 内核软链接目录

`run_all.py` 会在这里创建：

```text
kernel/topology_kernel -> ../../../src/topology_kernel
```

如果 Windows 当前权限不允许目录 symlink，脚本会尝试创建 junction。这里不提交内核副本。
