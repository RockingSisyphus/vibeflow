/* Official synchronous-call navigation, from an offline prepared snapshot. */
const {createRequire}=require('node:module'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
const [renderer,entry,snapshot]=process.argv.slice(2),puppeteer=createRequire(renderer)('puppeteer');
(async()=>{
 const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
 try {
  const page=await browser.newPage(),network=[],errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.setRequestInterception(true);
  page.on('request',request=>{if(/^https?:/.test(request.url())){network.push(request.url());request.abort();}else request.continue();});
  await page.goto(pathToFileURL(entry).href+'#snapshot='+encodeURIComponent(snapshot)+'&view=flow');
  await page.waitForSelector('[data-call-path="calc"] .node-card');
  assert.equal(await page.$eval('[data-call-path="calc"] .node-card',e=>e.dataset.workflowOperation),'invoke_sync');
  await page.$eval('[data-call-path="calc"]',e=>e.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:500,clientY:250})));
  assert.match(await page.$eval('#context-targets',e=>e.textContent),/project:child.jsonc.*evaluate/);
  await page.click('#context-targets button');
  await page.waitForFunction(()=>new URLSearchParams(location.hash.slice(1)).get('workflow')==='project:child.jsonc'&&document.querySelector('#entry').value==='evaluate');
  assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
