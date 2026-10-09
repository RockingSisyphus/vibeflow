/** Browser evidence over the final composed SVG, including actual geometry. */
import {createRequire} from "node:module";
import {pathToFileURL} from "node:url";
const [renderer,svg,output] = process.argv.slice(2);
const require=createRequire(renderer+"/package.json");
const puppeteer=require("puppeteer");
const browser=await puppeteer.launch({headless:true,args:["--no-sandbox","--disable-dev-shm-usage"]});
try {
  const page=await browser.newPage();await page.setViewport({width:2400,height:1600});
  await page.goto(pathToFileURL(svg).href,{waitUntil:"networkidle0"});
  const facts=await page.evaluate(()=>[...document.querySelectorAll("g.node")].map(node=>{
    const geometries=[...node.querySelectorAll("rect,polygon,circle,ellipse,path")].filter(item=>!item.closest(".label"));
    const rect=node.getBoundingClientRect();
    const shapes=geometries.map(item=>{const box=item.getBoundingClientRect(),css=getComputedStyle(item);return {tag:item.tagName,fill:css.fill,stroke:css.stroke,width:box.width,height:box.height,rx:item.getAttribute("rx"),points:item.getAttribute("points"),d:item.getAttribute("d")};});
    const labels=[...node.querySelectorAll("p,text,span.nodeLabel")].map(item=>({text:item.textContent,color:getComputedStyle(item).color,fill:getComputedStyle(item).fill}));
    return {id:node.id,text:node.textContent.replace(/\s+/g," ").trim(),width:rect.width,height:rect.height,shapes,labels};
  }));
  if(output)await page.screenshot({path:output,fullPage:true});
  console.log(JSON.stringify({nodes:facts,svg:true}));
} finally {await browser.close();}
