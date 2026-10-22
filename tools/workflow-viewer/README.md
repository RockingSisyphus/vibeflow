<!-- vibeflow-directory-purpose -->
# Workflow viewer

Standalone offline viewer of VibeFlow snapshot protocol v4. This directory is the sole source of browser code, styles, fonts and bundled ELK. Open index.html with preview.config.js pointing at a snapshot catalog. It does not execute workflows or interpret business source. Package builders copy these assets, never maintain another source tree. Generated histories and test artifacts belong outside this source directory.

`model.js` joins call/type/Nodeset facts and projects edge roles; `inspector.js` renders full descriptions, effective contracts, parameters and sources. Cards show concise descriptions. Flow edges distinguish scheduling, possible parallel dispatch/all-join and data-only transfer; selecting an edge exposes conditions and both sides of its data contract. Parallel styling describes scheduling topology, not a guarantee of simultaneous execution.

Resource tabs show their own resource category without importing adjacent implementation resources. Plugin cards represent selected packages, not their compiler/runtime hooks or contributed Node types. BaseLib cards retain explicit relationships between independent libraries; plugin-contributed libraries, consumers and owning plugins stay out of that graph. Full implementation facts remain in the snapshot for inspection.

命名入口可按全部或指定入口筛选。操作说明来自快照的调用级 Rule Record；目标图来自同份快照的 workflow_graphs，使用独立命名空间保持资源、样式和调用路径。页面不请求执行服务、不读业务源码、不从历史推测实际目标。

顶部折叠总览及左侧项目目录由 PROJECT_ARCHITECTURE.jsonc 的同一份导出投影提供，只列项目一级目录的用途；另外按 root 列出 workflow 的文件名、路径、宏观用途、入口和 architecture 文件位置，不递归列普通子目录。review 或 preview --workspace 更新完整总览；单 workflow 构建只发布快照，不覆盖完整清单。网页刷新只读取导出数据。

Nodeset 右键展开/收起，Call/Kill 右键跳转到目标 workflow；Send/Receive 根据 expected_workflows 提供多个预期交互跳转。目标来自本次快照的 workflow_graphs，不从未来历史补图。Call 显示目标入口，跳转后选中该入口；浏览器后退恢复原 workflow。

操作样式由共享 node_presentation 解析后写入事实，页面不维护另一套配色。Call、Kill、Receive、Send 共用缺角卡片形状 notch-rect，分别为金色、红色、深蓝、浅蓝，卡片直接加粗显示操作名；CallAndWait 保持 Call 样式，wait 不把主操作降为组合样式。当前实例身份由任意 Node 的 context.workflow.self() 读取，没有单独的 Self 协调节点。作者显式样式仍可覆盖默认值。planned Node/Nodeset 使用有效原色、虚线外框和 60% 不透明度，嵌套时不重复衰减，选中框独立显示。
