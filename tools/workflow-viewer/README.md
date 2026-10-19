<!-- vibeflow-directory-purpose -->
# Workflow viewer

Standalone offline viewer of VibeFlow snapshot protocol v2. This directory is the sole source of browser code, styles, fonts and bundled ELK. Open index.html with preview.config.js pointing at a snapshot catalog. It does not execute workflows or interpret business source. Package builders copy these assets, never maintain another source tree. Generated histories and test artifacts belong outside this source directory.

`model.js` joins call/type/Nodeset facts and projects edge roles; `inspector.js` renders full descriptions, effective contracts, parameters and sources. Cards show concise descriptions. Flow edges distinguish scheduling, possible parallel dispatch/all-join and data-only transfer; selecting an edge exposes conditions and both sides of its data contract. Parallel styling describes scheduling topology, not a guarantee of simultaneous execution.
