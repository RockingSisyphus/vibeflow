# Python 用户资源目录与 Nodeset 折叠

通过正式 CLI 验证所选 Plugin/BaseLib 的 Mermaid 文本、Architecture 完整事实、折叠定义的规则诊断以及真实 checked run。固定项目生成器位于 fixtures.py；共 12 个场景。

使用 tests/fixtures/python/resource_sections/run_all.py，传入 --kernel、--work和 --report ；工作目录必须位于仓库外。HTML 资源和展开交互通过 tooling 下的浏览器验收覆盖。
