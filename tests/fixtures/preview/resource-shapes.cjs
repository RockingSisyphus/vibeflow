/* One browser/session validates both actual resource views, without renderer coupling. */
const {createRequire}=require('node:module');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');
const [renderer,entry,encodedShapes]=process.argv.slice(2),shapes=JSON.parse(encodedShapes);
const puppeteer=createRequire(renderer)('puppeteer');
(async()=>{
 const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
 try{
  const page=await browser.newPage(),errors=[],network=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.setRequestInterception(true);
  page.on('request',r=>{if(/^https?:/.test(r.url())){network.push(r.url());r.abort();}else r.continue();});
  await page.goto(pathToFileURL(entry).href);await page.waitForSelector('[data-call-path]');
  for(const tab of [2,3]){
   await page.click(`#tabs button:nth-child(${tab})`);
   await page.waitForFunction(n=>document.querySelectorAll('[data-resource-id] .node-card').length===n,{},shapes.length);
   assert.deepEqual(await page.$$eval('[data-resource-id] .node-card',es=>es.map(e=>e.dataset.shape).sort()),shapes);
   assert.deepEqual(await page.$$eval('[data-resource-id] .card-outline',es=>[...new Set(es.map(e=>getComputedStyle(e).fill))]),['rgb(200, 228, 255)']);
   assert.equal(await page.$$eval('[data-resource-id]',es=>es.length),shapes.length);
  }
  assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
  console.log(JSON.stringify({cards:shapes.length*2,page_errors:errors,network_requests:network}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack||String(e));process.exitCode=1;});
