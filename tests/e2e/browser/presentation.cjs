/* Authored SDK presentation, read from the real rendered workflow and resources. */
const {createRequire}=require('node:module'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
const [manifest,entry]=process.argv.slice(2),puppeteer=createRequire(manifest)('puppeteer');
(async()=>{
 const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],
  ...(process.env.PUPPETEER_EXECUTABLE_PATH?{executablePath:process.env.PUPPETEER_EXECUTABLE_PATH}:{})});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.setViewport({width:1600,height:1100});await page.goto(pathToFileURL(entry).href);
  const toggle=async(path,child)=>{
   await page.waitForSelector('[data-call-path="'+path+'"]');await page.click('#fit');
   const prefix='[data-call-path="'+path+'"]';
   const card=await page.$(prefix+' > .group-header')||await page.$(prefix+' > .node-card');
   const box=await card.boundingBox();await page.mouse.click(box.x+box.width/2,box.y+box.height/2,{button:'right'});
   await page.click('#toggle');await page.waitForSelector('[data-call-path="'+child+'"]');
  };
  await toggle('outer_a','outer_a/inner_a');
  await toggle('outer_a/inner_a','outer_a/inner_a/left');
  assert.equal(await page.$eval('[data-call-path="outer_a/inner_a/left"] .card-outline',e=>getComputedStyle(e).fill),'rgb(214, 234, 255)');
  assert.equal(await page.$('[data-call-path="outer_b/inner_a"]'),null,'expanding one call must leave the other collapsed');
  for(const [tab,label,color] of [[2,'layout.helper','rgb(255, 230, 179)'],[3,'Layout lifecycle','rgb(217, 230, 255)']]){
   await page.click('#tabs button:nth-child('+tab+')');
   await page.waitForFunction(label=>document.querySelector('#scene').textContent.includes(label),{},label);
   const cards=await page.$$('[data-resource-id]');let found=false;
   for(const card of cards){
    if(!(await card.evaluate(e=>e.textContent)).includes(label))continue;
    assert.equal(await card.$eval('.card-outline',e=>getComputedStyle(e).fill),color);found=true;
   }
   assert(found,'authored resource is missing: '+label);
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({nodes:true,resources:true,independentCalls:true,errors}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
