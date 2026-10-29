# JavaScript fact-view performance observations

Run the formal CLI over four/eight Nodes, one/four shared BaseLibs and one/four
calls of the same Nodeset. A source Rule runs in a real worker and consumes its
local source facts. Each repetition starts a fresh process.

```bash
(
mountpoint -q /home/rockingsisyphus/ai-tmp || exit 1
probe_tmp="$(mktemp -d /home/rockingsisyphus/ai-tmp/review-performance.XXXXXXXX)"
trap 'rm -rf -- "$probe_tmp"' EXIT
export TMPDIR="$probe_tmp" TMP="$probe_tmp" TEMP="$probe_tmp"
python -B tests/fixtures/javascript/review_performance/run_all.py \
  --toolchain /path/to/javascript-toolchain \
  --work "$probe_tmp/work" --report "$probe_tmp/performance.json"
# 阅读报告并提取必要结论后退出；本次生成物自动清理。
)
```

`--kernel` selects frozen framework sources; `--baseline` observes old sources
without enforcing new deterministic assertions. The pinned toolchain comes from
the existing test runner and lockfile. Full verification includes this fixture.

Reports keep CLI output, driver requests, Program builds, worker evaluations,
source identity hashing and prepared view counts. A loader observer records
actual Program construction after cache lookup; it changes no decisions or
protocols. Wall-clock medians use three independent processes. Repeated calls
must not repeat source checks; call-rule behavior has separate conformance tests.

## 原生编译服务内存复现

`memory_probe.py` 使用真实 CLI 比较 8 节点单文件、8 节点 8 文件、12 节点
12 文件的 JS/Python build 和 review。需要本机 Python 已安装 `psutil`，以及
传入已有的 TypeScript 7.0.2 / esbuild 0.28.1 工具链目录。

```bash
(
mountpoint -q /home/rockingsisyphus/ai-tmp || exit 1
probe_tmp="$(mktemp -d /home/rockingsisyphus/ai-tmp/memory-probe.XXXXXXXX)"
trap 'rm -rf -- "$probe_tmp"' EXIT
export TMPDIR="$probe_tmp" TMP="$probe_tmp" TEMP="$probe_tmp"
python -B tests/fixtures/javascript/review_performance/memory_probe.py \
  --toolchain /path/to/javascript-toolchain --output "$probe_tmp/results.json"
# 每组的摘要已打印；可在退出此子 shell 前查看 JSON 或提取必要结论。
)
```

输入图和临时内核副本自动在已挂载的 AI 专用临时区生成、退出时删除。
它直接测量当前源码，不保留已退役的多环境缓存或每请求关闭的实验分支。
Architecture 生成在测量外完成；计量仅覆盖待测命令。
RSS 是 CLI 与全部后代的合计采样峰值，可能重复计算共享页；每格一次运行，
不作为跨机器内存或速度门禁。本次定位结论见
[JS 检查会话说明](../../../../docs/maintainers/javascript-check-sessions.md#内存与行为复验)。

## 目录用途与边界

仅用于：review_performance 专项实现回归的固定输入、预期及 runner；只保留有当前加载方的材料，运行产物写入临时工作区。

- 新文件按上述用途归属；新增子目录同时写明职责，不能作为临时收纳箱。
- 一次运行的日志、缓存、依赖安装和候选构建放在仓库外临时工作区，用完清理。
- 已确定过时且不再使用的内容直接删除；需要追溯时使用 Git 历史，不默认另建归档。

完整归位规则见[仓库目录职责](../../../../docs/maintainers/directory-layout.md)。
