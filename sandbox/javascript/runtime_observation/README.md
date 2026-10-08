# JS/TS 运行观测沙箱

通过公开代码 SDK 登记 Node，正式构建 Node.js AOT 并真实执行成功、异常和再次运行。父进程持续读取 JSON；业务主线程同步计算期间，状态线程继续更新时间。检查信息快照、状态重置、两类日志与终端输出。

加入 `--renderer` 可同时构建 browser 产物，在真实 Chromium 页面通过按钮调用 workflow，检查 `onStatus` 的状态顺序及 Node 更新的缓存。`report.json` 保存当次真实观察。

```bash
PYTHONPATH=src:. npm_config_cache=/tmp/vibeflow-npm-cache \
python -B -m sandbox.javascript.runtime_observation.probe \
  --work /tmp/vf-js-observation --toolchain /path/to/project-with-node_modules \
  --renderer /path/to/puppeteer-project --report /tmp/vf-js-observation.json
```

工具链目录安装 TypeScript/esbuild，renderer 目录安装 Puppeteer。使用新的工作目录；不匹配返回非零。pytest 覆盖同步/异步状态回调、非 JSON 数据拒绝及 Host 会话与生命周期；`verify_project.py --full` 另执行真实浏览器状态验收。
