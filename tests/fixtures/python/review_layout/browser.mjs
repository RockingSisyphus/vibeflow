/** Computed geometry and colours from the final, composed SVG. */
import {createRequire} from "node:module";
import {pathToFileURL} from "node:url";
const [renderer, svg, screenshot] = process.argv.slice(2);
const require = createRequire(renderer + "/package.json");
const browser = await require("puppeteer").launch({headless:true,
  args:["--no-sandbox", "--disable-dev-shm-usage"]});
try {
  const page = await browser.newPage();
  await page.setViewport({width:2200,height:1500});
  await page.goto(pathToFileURL(svg).href, {waitUntil:"networkidle0"});
  const result = await page.evaluate(() => ({
    root:document.querySelector("svg")?.getAttribute("aria-roledescription"),
    titles:[...document.querySelectorAll("text.review-title")].map(item => {
      const box = item.getBoundingClientRect();
      return {text:item.textContent,x:box.x,y:box.y,width:box.width,height:box.height};
    }),
    fragments:[...document.querySelectorAll("g.review-inline-fragment")].map(frame => ({
      title:frame.previousElementSibling?.textContent ?? "",
      nodes:[...frame.querySelectorAll("g.node")]
        .filter(item => item.closest("g.review-inline-fragment") === frame).map(item => item.id)
    })),
    nodes:[...document.querySelectorAll("g.node")].map(item => {
      const box = item.getBoundingClientRect();
      const fragments = [];
      for (let frame = item.closest("g.review-inline-fragment"); frame;
           frame = frame.parentElement?.closest("g.review-inline-fragment")) {
        fragments.unshift(frame.previousElementSibling?.textContent ?? "");
      }
      return {id:item.id,text:item.textContent.replace(/\s+/g," ").trim(),
        fragments,
        x:box.x,y:box.y,width:box.width,height:box.height,
        shapes:[...item.querySelectorAll("rect,path,polygon,circle,ellipse")]
          .filter(shape => !shape.closest(".label")).map(shape => {
            const geometry = shape.getBoundingClientRect(), css = getComputedStyle(shape);
            return {tag:shape.tagName,fill:css.fill,stroke:css.stroke,rx:shape.getAttribute("rx"),
              width:geometry.width,height:geometry.height};
          })};
    })
  }));
  if (screenshot) await page.screenshot({path:screenshot,fullPage:true});
  process.stdout.write(JSON.stringify(result));
} finally { await browser.close(); }
