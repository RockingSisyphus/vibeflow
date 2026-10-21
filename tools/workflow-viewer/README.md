<!-- vibeflow-directory-purpose -->
# Workflow viewer

Standalone offline viewer of VibeFlow snapshot protocol v3. This directory is the sole source of browser code, styles, fonts and bundled ELK. Open index.html with preview.config.js pointing at a snapshot catalog. It does not execute workflows or interpret business source. Package builders copy these assets, never maintain another source tree. Generated histories and test artifacts belong outside this source directory.

`model.js` joins call/type/Nodeset facts and projects edge roles; `inspector.js` renders full descriptions, effective contracts, parameters and sources. Cards show concise descriptions. Flow edges distinguish scheduling, possible parallel dispatch/all-join and data-only transfer; selecting an edge exposes conditions and both sides of its data contract. Parallel styling describes scheduling topology, not a guarantee of simultaneous execution.

Resource tabs show their own resource category without importing adjacent implementation resources. Plugin cards represent selected packages, not their compiler/runtime hooks or contributed Node types. BaseLib cards retain explicit relationships between libraries; consumers and owning plugins stay out of that graph. Full implementation facts remain in the snapshot for inspection.

命名入口可按全部或指定入口筛选。操作说明来自快照的调用级 Rule Record；目标图来自同份快照的 workflow_graphs，使用独立命名空间保持资源、样式和调用路径。页面不请求执行服务、不读业务源码、不从历史推测实际目标。

左侧可在历史记录与项目目录之间切换。项目目录读取 `project.js` 的全部 root/workflow（包含空 root、未生成预览及损坏配置），并合并已有历史；每个 workflow 只显示按生成时间选择的最新快照及其更新时间。旧运行的状态晚更新不会替换新快照。目录在 review/build 或 `preview --workspace` 时更新，页面刷新只重读导出的目录和记录，不扫描源码或自动生成图。旧目录缺少 `project.js` 时仅列出已有记录，并明确提示补齐方式。

workflow 操作卡片依据已有调用级事实使用独立形状和配色：call 双边框、wait 六边形、send/receive 方向相反的平行四边形、kill 圆角框、self 圆形；多种操作使用青色文档形。只替换 native 样式，显式声明和 planned 状态配色优先，原 SVG 对照不变。
