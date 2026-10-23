# 三个独立 Workflow 联合求值（JavaScript）

本目录只负责通用 JS 同进程协作的真实使用项目，以及 Node、浏览器执行器。三个图、输入、独立数值判据与故障预期复用[Python 沙箱说明](../../python/workflow_cooperation_math/README.md)中的共同合同。

A、B 为 async，C 为 sync；两轮异步消息中嵌入一次同步调用，使用发行包官方节点。最终计算 `F=6(3x-y+8)²-27x+43y-180`；输入 `(2,7)` 必须得到 361。五组输入同时运行，校验所有中间值、消息身份、轮次、独立实例、真实终态与释放。四个错误配置必须产生 3631、196、376、358，不能通过正确答案判据。

`run_all.py` 通过正式 browser Target 构建三个 workflow 及故障对照，再将 AOT、通用 Coordinator 和 `verify.mjs` 一起打成单个 IIFE 脚本。删除原项目后，**同一个脚本**分别在 Node 和真实 Chromium 运行。

`browser.cjs` 固定 `headless: true`，使用空白页和离线模式，通过本地文件注入脚本，不启动资产或协调服务。监测注入及协作期间的全部页面请求，必须为零。没有 DOM、酒馆 API 或页面生命周期适配。

```bash
python sandbox/javascript/workflow_cooperation_math/run_all.py \
  --work-dir /path/to/new-work-directory \
  --toolchain-root /path/to/typescript-esbuild-toolchain \
  --puppeteer-root /path/to/mermaid-renderer
```

工具链使用仓库锁文件安装；可通过 `PUPPETEER_EXECUTABLE_PATH` 显式指定 Chromium。默认临时工作目录自动清理；显式目录保留 `report.json`、单文件脚本、AOT 和 Node／Chromium 的真实 trace。缺少 `--puppeteer-root` 只执行 Node，报告为 `REDUCED`，不能算完整通过。

JS integration 与根目录 `python tools/verify_project.py --full` 自动包含该入口。HTTP、跨语言进程协作、取消清理和错误传播继续由现有专项覆盖；本项目不代表 ERA 生产验收。
