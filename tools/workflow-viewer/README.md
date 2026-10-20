<!-- vibeflow-directory-purpose -->
# Workflow viewer

Standalone offline viewer of VibeFlow snapshot protocol v2. This directory is the sole source of browser code, styles, fonts and bundled ELK. Open index.html with preview.config.js pointing at a snapshot catalog. It does not execute workflows or interpret business source. Package builders copy these assets, never maintain another source tree. Generated histories and test artifacts belong outside this source directory.

`model.js` joins call/type/Nodeset facts and projects edge roles; `inspector.js` renders full descriptions, effective contracts, parameters and sources. Cards show concise descriptions. Flow edges distinguish scheduling, possible parallel dispatch/all-join and data-only transfer; selecting an edge exposes conditions and both sides of its data contract. Parallel styling describes scheduling topology, not a guarantee of simultaneous execution.

命名入口可按全部或指定入口筛选。操作说明来自快照的调用级 Rule Record；目标图来自同份快照的 workflow_graphs，使用独立命名空间保持资源、样式和调用路径。页面不请求执行服务、不读业务源码、不从历史推测实际目标。
