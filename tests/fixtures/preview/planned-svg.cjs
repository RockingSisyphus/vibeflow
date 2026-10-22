/* Check rendered geometry, labels and nested detail panels in a real browser. */
const {createRequire}=require('node:module'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
const [renderer,file]=process.argv.slice(2),puppeteer=createRequire(renderer)('puppeteer');
(async()=>{
 const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
 try{
  const page=await browser.newPage();await page.goto(pathToFileURL(file).href);
  const result=await page.evaluate(()=>{
   function alpha(element){let value=1;for(let e=element;e;e=e.parentElement)value*=Number(getComputedStyle(e).opacity);return value;}
   return {nodes:[...document.querySelectorAll('.node.plannedNode')].map(g=>{
    const shape=g.querySelector('polygon,rect,circle,path,ellipse'),label=g.querySelector('.label');
    return {shape:alpha(shape),label:alpha(label),dash:getComputedStyle(shape).strokeDasharray,fill:getComputedStyle(shape).fill};
   }),panels:[...document.querySelectorAll('.planned-panel')].map(g=>({alpha:alpha(g),dash:getComputedStyle(g.querySelector(':scope>.review-panel-frame')).strokeDasharray}))};
  });
  assert(result.nodes.length>=3);assert(result.panels.length>=2);
  for(const node of result.nodes){assert(Math.abs(node.shape-.6)<.001,JSON.stringify(node));assert(Math.abs(node.label-.6)<.001,JSON.stringify(node));assert.match(node.dash,/6/);}
  for(const panel of result.panels){assert(Math.abs(panel.alpha-.6)<.001,JSON.stringify(panel));assert.match(panel.dash,/6/);}
  assert(result.nodes.some(node=>node.fill==='rgb(255, 187, 170)'));
  console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
