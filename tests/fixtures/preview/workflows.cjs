/* Actual offline workflow navigation and named-entry acceptance. */
const {createRequire}=require('node:module'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
const [renderer,entry,expected]=process.argv.slice(2),puppeteer=createRequire(renderer)('puppeteer');
(async()=>{
 const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
 const errors=[],network=[];
 try{
  const page=await browser.newPage();await page.setViewport({width:1500,height:1000});
  page.on('pageerror',error=>errors.push(error.message));
  await page.setRequestInterception(true);page.on('request',r=>{if(/^https?:/.test(r.url())){network.push(r.url());r.abort();}else r.continue();});
  await page.goto(pathToFileURL(entry).href);await page.waitForSelector('[data-call-path="work"]');
  assert.equal(await page.$eval('#entry',e=>e.value),'cli');
  assert.match(await page.$eval('[data-call-path="work"]',e=>e.textContent),/入口 other/);
  await page.select('#entry','gui');await page.waitForSelector('[data-call-path="gui"]');
  assert.equal(await page.$('[data-call-path="start"]'),null);
  await page.$eval('[data-call-path="work"]',e=>e.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:650,clientY:250})));
  assert.equal(await page.$eval('#toggle',e=>e.hidden),true);
  assert.match(await page.$eval('#context-targets',e=>e.textContent),/worker:workflow.jsonc.*入口 other/);
  if(expected==='True'){
   assert.equal(await page.$$eval('#context-targets button',items=>items.length),3);
   assert.match(await page.$eval('#context-targets',e=>e.textContent),/预期交互/);
   const missing=await page.$eval('#context-targets button:last-child',e=>({disabled:e.disabled,title:e.title}));
   assert.equal(missing.disabled,true);assert(missing.title.length>0);
  }
  await page.click('#context-targets button');
  await page.waitForFunction(()=>new URLSearchParams(location.hash.slice(1)).get('workflow')==='worker:workflow.jsonc'&&document.querySelector('[data-call-path="alternate"]'));
  assert.equal(await page.$eval('#entry',e=>e.value),'other');
  assert.equal(await page.$('[data-call-path="start"]'),null);
  assert.equal(await page.$('[data-call-path*="/@workflow/"]'),null);
  await page.click('#fit');
  const before=await page.$eval('#scene',e=>e.getAttribute('transform'));
  const box=await (await page.$('[data-call-path="work"]')).boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
  await page.mouse.down();await page.mouse.move(box.x+box.width/2+35,box.y+box.height/2+25,{steps:5});await page.mouse.up();
  assert.notEqual(await page.$eval('#scene',e=>e.getAttribute('transform')),before);
  await page.$eval('#zoom',e=>{e.value='1400%';e.dispatchEvent(new Event('change'));});
  assert.equal(await page.$eval('#zoom',e=>e.value),'1400%');
  await page.goBack();await page.waitForSelector('[data-call-path="gui"]');
  assert.equal(await page.$eval('#entry',e=>e.value),'gui');
  await page.select('#entry','cli');await page.waitForSelector('[data-call-path="start"]');
  await page.click('#project-overview>summary');assert.match(await page.$eval('#project-content',e=>e.textContent),/caller.*worker/s);
  if(process.env.VIBEFLOW_VIEWER_SCREENSHOT){await page.click('#fit');await page.screenshot({path:process.env.VIBEFLOW_VIEWER_SCREENSHOT,fullPage:true});}
  assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
  console.log(JSON.stringify({entry_switch:true,workflow_navigation:true,pan:true,zoom:'1400%',history:true,overview:true,errors,network}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
