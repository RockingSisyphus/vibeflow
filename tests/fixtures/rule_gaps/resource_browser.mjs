/** Resource snapshots and the optional SVG share one real browser process. */
import {pathToFileURL} from "node:url";
import {observeSvg} from "../support/svg_browser.mjs";
const [renderer,svg,output,previewHtml,snapshot]=process.argv.slice(2);
if(!previewHtml||!snapshot)throw new Error("resource evidence requires the preview entry and snapshot ID");
async function inspectPreview(browser){
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
  return {preview};
}
console.log(JSON.stringify(await observeSvg({renderer,svg,output,additional:inspectPreview})));
