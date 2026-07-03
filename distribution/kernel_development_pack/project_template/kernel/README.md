# kernel 目录

这里放分发构建脚本生成的内核单文件归档：

```text
kernel/vibeflow-kernel.zip
```

`run.py` 会通过 `sys.path` 直接从这个归档导入本地内核。业务开发时不需要解包或阅读归档内容。
