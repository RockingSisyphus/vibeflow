/** Render SVG with Mermaid's browser API over registered loopback HTTP assets. */
import {createRequire} from "node:module";
import {readFile, writeFile} from "node:fs/promises";
import {dirname, join} from "node:path";
import {fileURLToPath, pathToFileURL} from "node:url";
import {serveAssets} from "./http_assets.mjs";

const args = process.argv.slice(2);
const options = new Map(Array.from({length: args.length / 2}, (_, i) => [args[i * 2], args[i * 2 + 1]]));
const mmdc = options.get("--renderer-cli");
const input = options.get("--input"), output = options.get("--output");
const configFile = options.get("--configFile"), browserFile = options.get("--puppeteerConfigFile");
const theme = options.get("--theme"), background = options.get("--backgroundColor");
const timeout = options.get("--timeout");
const require = createRequire(mmdc);
const puppeteer = require("puppeteer");
const {resolve} = await import(pathToFileURL(require.resolve("import-meta-resolve")));
const moduleDir = name => dirname(fileURLToPath(resolve(name, pathToFileURL(mmdc).href)));
const mounts = {
  mermaid: moduleDir("mermaid"),
  elk: moduleDir("@mermaid-js/layout-elk"),
  zenuml: moduleDir("@mermaid-js/mermaid-zenuml"),
  fontawesome: join(dirname(require.resolve("@fortawesome/fontawesome-free/css/fontawesome.css")), ".."),
  katex: dirname(require.resolve("katex/dist/katex.css")),
};
try { mounts.tidy = moduleDir("@mermaid-js/layout-tidy-tree"); }
catch (error) { if (error.code !== "ERR_MODULE_NOT_FOUND") throw error; }
const config = JSON.parse(await readFile(configFile, "utf8"));
const launch = JSON.parse(await readFile(browserFile, "utf8"));
const definition = await readFile(input, "utf8");
const deadline = Date.now() + Number(timeout) * 1000;
const remaining = () => Math.max(1, deadline - Date.now());
let server, browser, timer;
try {
  server = await serveAssets({mounts, documents: {"index.html":
    '<!doctype html><html><head><meta charset="utf-8"></head><body><div id="container"></div></body></html>'}});
  browser = await puppeteer.launch({...launch, headless: true, dumpio: true, timeout: remaining()});
  const render = async () => {
    const page = await browser.newPage();
    await page.setViewport({width: 800, height: 600, deviceScaleFactor: 1});
    page.setDefaultTimeout(remaining());
    await page.goto(server.url("index.html"));
    for (const css of ["brands", "regular", "solid", "fontawesome"]) {
      await page.addStyleTag({url: server.url(`fontawesome/css/${css}.css`)});
    }
    await page.addStyleTag({url: server.url("katex/katex.css")});
    return page.evaluate(async ({source, config, theme, background, urls}) => {
      const {default: mermaid} = await import(urls.mermaid);
      const {default: elk} = await import(urls.elk);
      const {default: zenuml} = await import(urls.zenuml);
      const {default: tidy} = urls.tidy ? await import(urls.tidy) : {default: []};
      await mermaid.registerExternalDiagrams([zenuml]);
      mermaid.registerLayoutLoaders([...elk, ...tidy]);
      mermaid.initialize({startOnLoad: false, theme, ...config});
      document.body.style.background = background;
      await Promise.all(Array.from(document.fonts, font => font.load()));
      const container = document.querySelector("#container");
      const {svg} = await mermaid.render("my-svg", source, container);
      container.innerHTML = svg;
      container.querySelector("svg").style.backgroundColor = background;
      return new XMLSerializer().serializeToString(container.querySelector("svg"));
    }, {source: definition, config, theme, background, urls: {
      mermaid: server.url("mermaid/mermaid.esm.mjs"),
      elk: server.url("elk/mermaid-layout-elk.esm.mjs"),
      zenuml: server.url("zenuml/mermaid-zenuml.esm.mjs"),
      tidy: mounts.tidy ? server.url("tidy/mermaid-layout-tidy-tree.esm.mjs") : null,
    }});
  };
  const svg = await Promise.race([render(), new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error("Mermaid HTTP render timed out")), remaining());
  })]);
  await writeFile(output, svg);
} catch (error) {
  if (error instanceof Error) {
    console.error(error.stack ?? error.message);
  } else if (error && typeof error === "object") {
    // Puppeteer can reject with a WebSocket ErrorEvent, not an Error. Keep
    // diagnostic fields without dumping the event's process/environment tree.
    const fields = {};
    for (const key of ["name", "message", "code", "errno", "syscall", "signal", "type"]) {
      if (["string", "number"].includes(typeof error[key])) fields[key] = error[key];
    }
    const cause = error.error ?? error.cause;
    if (cause instanceof Error) fields.cause = cause.stack ?? cause.message;
    console.error(JSON.stringify(fields));
  } else {
    console.error(String(error));
  }
  process.exitCode = 1;
} finally {
  clearTimeout(timer);
  try { await browser?.close(); } finally { await server?.close(); }
}
