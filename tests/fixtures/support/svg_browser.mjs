/** Shared real SVG observer; callers may reuse its browser for extra evidence. */
import {createRequire} from "node:module";
import {pathToFileURL} from "node:url";
import {serveAssets} from "../../../src/vibeflow/tooling/presentation/mermaid/http_assets.mjs";

export async function observeSvg({renderer,svg,output,additional=async()=>({})}) {
  const require=createRequire(renderer+"/package.json"),puppeteer=require("puppeteer");
  const assets=await serveAssets({files:{"graph.svg":svg}});
  let browser;
  try {
    browser=await puppeteer.launch({headless:true,args:["--no-sandbox","--disable-dev-shm-usage"]});
    const page=await browser.newPage();await page.setViewport({width:2400,height:1600});
    await page.goto(assets.url("graph.svg"),{waitUntil:"networkidle0"});
    const facts=await page.evaluate(()=>[...document.querySelectorAll("g.node")].map(node=>{
      const geometries=[...node.querySelectorAll("rect,polygon,circle,ellipse,path")].filter(item=>!item.closest(".label"));
      const rect=node.getBoundingClientRect();
      const shapes=geometries.map(item=>{const box=item.getBoundingClientRect(),css=getComputedStyle(item);return {tag:item.tagName,fill:css.fill,stroke:css.stroke,width:box.width,height:box.height,rx:item.getAttribute("rx"),points:item.getAttribute("points"),d:item.getAttribute("d")};});
      const labels=[...node.querySelectorAll("p,text,span.nodeLabel")].map(item=>({text:item.textContent,color:getComputedStyle(item).color,fill:getComputedStyle(item).fill}));
      return {id:node.id,text:node.textContent.replace(/\s+/g," ").trim(),width:rect.width,height:rect.height,shapes,labels};
    }));
    if(output)await page.screenshot({path:output,fullPage:true});
    return {nodes:facts,svg:true,...await additional(browser)};
  } finally {try {await browser?.close();} finally {await assets.close();}}
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  const [renderer,svg,output]=process.argv.slice(2);
  console.log(JSON.stringify(await observeSvg({renderer,svg,output})));
}
