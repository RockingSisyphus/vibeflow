# 跨 root 继承复现

来自 VibeTrain 的 `native_v13_audit_20261021/vibeflow-1.3.1-inheritance-repro.zip`。
原始 1.3.1 对 relative/qualified 导入 × vibetrain/task 入口的结果为 PASS/FAIL/FAIL/PASS。

`tests/targets/python/test_cross_root_inheritance.py` 复制此工程，在独立子进程检查四组组合；
正例补充审核文档登记后执行 review、run、build，删除源码后运行 AOT。
反例在父类中引入错误签名、print 副作用、输入写入，要求原有规则继续诊断实际父类。
源码分析使用物理文件定位相对导入，并用可见源码根建立完整模块名别名；
AOT 保留项目目录关系及插件导出类的原始加载命名空间，避免静态检查与部署后行为分离。
