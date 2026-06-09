# 05. BaseLib 与 Boundary 规范

## base_lib

`base_lib/` 放纯函数 helper。它可以被 node 导入，用来减少 node 内部重复逻辑。

合法示例：

```python
def add(left: float, right: float) -> float:
    return left + right
```

base_lib 应保持：

- 无文件、网络、数据库、进程等副作用。
- 无可变全局状态。
- 不导入 node、boundary、runtime。
- 依赖链不要过长。
- 函数短小、分支少、嵌套浅。

项目 policy 中可声明允许的 base_lib 路径和模块：

```jsonc
{
  "policy": {
    "base_lib": {
      "allowed_paths": ["../base_lib"],
      "allowed_modules": ["base_lib"]
    }
  }
}
```

## boundary

boundary 是唯一允许承载真实副作用的地方，例如文件、网络、数据库、浏览器、外部系统调用。

boundary 必须实现四个方法：

```python
class DemoBoundary:
    def before_run(self, run_config):
        return {}

    def after_run(self, outputs, run_config):
        return {}

    def before_iteration(self, iteration, state):
        return {}

    def after_iteration(self, iteration, outputs, state):
        return {}
```

注册 boundary：

```python
from topology_kernel import BoundaryRegistry
from boundaries import DemoBoundary


def build_boundary_registry() -> BoundaryRegistry:
    registry = BoundaryRegistry()
    registry.register("demo.boundary", DemoBoundary)
    return registry
```

配置 boundary：

```jsonc
{
  "boundary": {
    "type": "demo.boundary",
    "config": {"run_dir": "runs/demo"},
    "consumes": ["effects.request"],
    "provides": ["io.result"],
    "allowed_paths": ["runs"]
  }
}
```

boundary 返回的 key 必须在 `provides` 中声明。boundary 产物路径必须位于运行目录或 `allowed_paths` 中。

