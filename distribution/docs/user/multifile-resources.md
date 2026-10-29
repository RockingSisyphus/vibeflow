# 多文件实现、库依赖与样式

一个资源可以由入口和多个支撑文件组成；多个资源复用的实现用 BaseLib 表达。本节说明文件登记、源码依赖与展示样式。

## 登记支撑文件

Python 的 `@node`、`@base_lib` 及生命周期声明，JS/TS 的 `defineNode`、`defineBaseLib` 和 `definePlugin` 均可用 `implementation_files` 列出支撑源码。路径相对 SDK 声明模块，传递依赖中的支撑源码也逐一登记。

```python
implementation_files=["support.py", "formatting.py"]
```

```ts
implementation_files: ["support.ts", "types.ts"]
```

同一文件可声明多个 Node，各自使用独立 ID。跨文件父类、helper 和 type-only 导入按实际资源归属登记。Plugin 的入口、贡献和支撑文件均位于自身包内。

## 声明库依赖

Node 或生命周期通过 `base_libs` 引用库，BaseLib 通过 `dependencies` 引用其他库：

```python
base_libs=["example.text_tools"]
```

这些声明记录源码依赖。workflow 的 `base_lib.modules` 选择本次使用的独立库，Plugin 私有库随整包选择。

## 资源与调用样式

Node、BaseLib、Plugin 及生命周期声明可用 `presentation` 设置颜色、形状和图标。NodeType 提供默认外观，业务 Node 可覆盖默认，调用点通过 `style` 设置本次展示。业务 Node 还可通过 `tags` / `metadata` 声明标签和自定义资料。

各资源使用自己的 Ruleset：Node 可选 `vibeflow.process`，独立库可选 `vibeflow.base_lib`，生命周期可选 `vibeflow.plugin`，插件声明通过 `declaration_rulesets` 选择声明检查。默认可维护性规则逐文件检查 500 行上限。

## 相关文档

- [项目治理](project-governance.md)：资源目录、跨 root 可见性和 workflow 的库选择。
- [Plugin 与集成](plugins-and-integrations.md)：包声明和生命周期。
- [本地预览](local-preview.md)：查看源码来源、资源关系及样式。
