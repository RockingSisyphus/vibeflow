# JavaScript fact-view performance observations

Run the formal CLI over four/eight Nodes, one/four shared BaseLibs and one/four
calls of the same Nodeset. A source Rule runs in a real worker and consumes its
local source facts. Each repetition starts a fresh process.

```bash
python -B tests/fixtures/javascript/review_performance/run_all.py \
  --toolchain /tmp/pinned-javascript-toolchain \
  --work /tmp/javascript-review-performance \
  --report /tmp/javascript-review-performance.json
```

`--kernel` selects frozen framework sources; `--baseline` observes old sources
without enforcing new deterministic assertions. The pinned toolchain comes from
the existing test runner and lockfile. Full verification includes this fixture.

Reports keep CLI output, driver requests, Program builds, worker evaluations,
source identity hashing and prepared view counts. A loader observer records
actual Program construction after cache lookup; it changes no decisions or
protocols. Wall-clock medians use three independent processes. Repeated calls
must not repeat source checks; call-rule behavior has separate conformance tests.

## 目录用途与边界

仅用于：review_performance 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
