/* Actual offline workflow expansion and named-entry UI acceptance. */
const {createRequire}=require('node:module'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
const [renderer,entry]=process.argv.slice(2),puppeteer=createRequire(renderer)('puppeteer');
(async()=>{
 const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
 const errors=[],network=[];
 try{
  const page=await browser.newPage();await page.setViewport({width:1500,height:1000});
  page.on('pageerror',error=>errors.push(error.message));
  await page.setRequestInterception(true);page.on('request',r=>{if(/^https?:/.test(r.url())){network.push(r.url());r.abort();}else r.continue();});
  await page.goto(pathToFileURL(entry).href);await page.waitForSelector('[data-call-path="work"]');
  assert.match(await page.$eval('[data-call-path="work"]',e=>e.textContent),/启动 workflow · 等待结束/);
  await page.select('#entry','gui');await page.waitForSelector('[data-call-path="gui"]');
  assert.equal(await page.$('[data-call-path="start"]'),null);
  await page.click('[data-call-path="work"]');
  assert.match(await page.$eval('#details',e=>e.textContent),/目标别名|接口操作/);
  await page.evaluate(()=>[...document.querySelectorAll('#details button')].find(b=>b.textContent.includes('原地展开 worker')).click());
  await page.waitForFunction(()=>document.querySelectorAll('[data-call-path*="/@workflow/"]').length===3);
  await page.click('#fit');
  const child=await page.$('[data-call-path*="/@workflow/"][data-call-path$="/work"]');
  await child.click();assert.match(await page.$eval('#details',e=>e.textContent),/worker|peer/);
  const viewport=await page.$('#viewport'),box=await viewport.boundingBox(),before=await page.$eval('#scene',e=>e.getAttribute('transform'));
  const nodeBox=await child.boundingBox();await page.mouse.move(nodeBox.x+nodeBox.width/2,nodeBox.y+nodeBox.height/2);
  await page.mouse.down();await page.mouse.move(nodeBox.x+nodeBox.width/2+35,nodeBox.y+nodeBox.height/2+25,{steps:5});await page.mouse.up();
  assert.notEqual(await page.$eval('#scene',e=>e.getAttribute('transform')),before);
  await page.$eval('#zoom',e=>{e.value='1400%';e.dispatchEvent(new Event('change'));});
  assert.equal(await page.$eval('#zoom',e=>e.value),'1400%');
  await page.click('#collapse');await page.waitForFunction(()=>!document.querySelector('[data-call-path*="/@workflow/"]'));
  await page.select('#entry','cli');await page.waitForSelector('[data-call-path="start"]');
  assert.equal(await page.$('[data-call-path="gui"]'),null);
  await page.goBack();await page.waitForSelector('[data-call-path="gui"]');
  assert.equal(await page.$eval('#entry',e=>e.value),'gui');
  if(process.env.VIBEFLOW_VIEWER_SCREENSHOT){await page.click('#fit');await page.screenshot({path:process.env.VIBEFLOW_VIEWER_SCREENSHOT,fullPage:true});}
  assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
  console.log(JSON.stringify({entry_switch:true,workflow_expansion:true,inner_pan:true,zoom:'1400%',history:true,errors,network}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
