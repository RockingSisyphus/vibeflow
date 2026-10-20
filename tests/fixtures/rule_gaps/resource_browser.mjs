/** One browser checks the optional SVG and the primary offline snapshot views. */
import {createRequire} from "node:module";
import {pathToFileURL} from "node:url";
import {serveAssets} from "../../../src/vibeflow/tooling/presentation/mermaid/http_assets.mjs";
const [renderer,svg,output,previewHtml,snapshot] = process.argv.slice(2);
const require=createRequire(renderer+"/package.json");
const puppeteer=require("puppeteer");
const assets = await serveAssets({files: {"graph.svg": svg}});
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
  const preview={views:{},errors:[],network:[]};
  for(const view of ["flow","base_lib","plugin","host_extension"]){
    const tab=await browser.newPage();await tab.setViewport({width:2400,height:1600});
    tab.on("pageerror",error=>preview.errors.push(error.message));
    await tab.setRequestInterception(true);
    tab.on("request",request=>{if(/^https?:/.test(request.url())){preview.network.push(request.url());request.abort();}else request.continue();});
    const url=pathToFileURL(previewHtml);url.hash=new URLSearchParams({snapshot,view}).toString();
    await tab.goto(url.href,{waitUntil:"load"});
    await tab.waitForFunction(()=>document.querySelector("#dimensions").textContent.includes("个可见对象"));
    preview.views[view]=await tab.evaluate(()=>[...document.querySelectorAll("[data-call-path], [data-resource-id]")].flatMap(parent=>{
      const card=parent.querySelector(":scope > .node-card");if(!card)return [];
      const outline=card.querySelector(".card-outline"),box=outline.getBoundingClientRect(),css=getComputedStyle(outline);
      return [{id:parent.dataset.callPath??parent.dataset.resourceId,shape:card.dataset.shape,text:card.textContent,
        outline:{tag:outline.tagName,fill:css.fill,stroke:css.stroke,width:box.width,height:box.height,rx:outline.getAttribute("rx"),points:outline.getAttribute("points"),d:outline.getAttribute("d")},
        labels:[...card.querySelectorAll("text")].map(label=>({text:label.textContent,fill:getComputedStyle(label).fill})),
        ellipses:card.querySelectorAll("ellipse").length,paths:card.querySelectorAll("path").length}];
    }));
    await tab.close();
  }
  console.log(JSON.stringify({nodes:facts,svg:true,preview}));
} finally {try {await browser?.close();} finally {await assets.close();}}
