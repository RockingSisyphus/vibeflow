/* Normal offline preview, produced by `vibeflow review`. DOM reads only. */
const {createRequire}=require('node:module');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');
const [manifest,entry]=process.argv.slice(2);
const puppeteer=createRequire(manifest)('puppeteer');
(async()=>{
 const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],
  ...(process.env.PUPPETEER_EXECUTABLE_PATH?{executablePath:process.env.PUPPETEER_EXECUTABLE_PATH}:{})});
 const errors=[];
 try{
  const page=await browser.newPage();await page.setViewport({width:1500,height:1000});
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(pathToFileURL(entry).href);await page.waitForSelector('[data-call-path="add_one_flow"]');
  assert.match(await page.$eval('body',e=>e.textContent),/Add One Flow/);
  await page.click('#fit');
  await page.click('#zoom');await page.keyboard.down('Control');await page.keyboard.press('a');await page.keyboard.up('Control');
  await page.keyboard.type('150%');await page.keyboard.press('Enter');
  assert.equal(await page.$eval('#zoom',e=>e.value),'150%');
  await page.click('[data-call-path="add_one_flow"]',{button:'right'});
  await page.waitForSelector('#toggle:not([hidden])');await page.click('#toggle');
  await page.waitForSelector('[data-call-path^="add_one_flow/"]');
  for(const [index,name] of [[2,'Math Tools'],[3,'minimal.python']]){
   await page.click(`#tabs button:nth-child(${index})`);
   await page.waitForFunction(name=>document.querySelector('#scene').textContent.includes(name),{},name);
   await page.click('#fit');
   const resource=await page.$('[data-resource-id]');const box=await resource.boundingBox();
   await page.mouse.click(box.x+box.width/2,box.y+box.height/2);
   await page.waitForFunction(name=>document.querySelector('#details').textContent.includes(name),{},name);
  }
  await page.click('#tabs button:nth-child(1)');
  await page.waitForSelector('[data-call-path^="add_one_flow/"]');
  await page.click('#fit');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({zoom:true,nodeset:true,resources:true,errors}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
