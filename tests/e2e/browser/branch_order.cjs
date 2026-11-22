const assert=require('node:assert/strict'),{createRequire}=require('node:module'),{pathToFileURL}=require('node:url');
const [manifest,entry]=process.argv.slice(2),puppeteer=createRequire(manifest)('puppeteer');
(async()=>{
 const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],
  ...(process.env.PUPPETEER_EXECUTABLE_PATH?{executablePath:process.env.PUPPETEER_EXECUTABLE_PATH}:{})});
 try{
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.setViewport({width:1600,height:1100});await page.goto(pathToFileURL(entry).href);
  await page.waitForSelector('[data-call-path="event__boundary"]');
  const order=async(left,right)=>page.evaluate((left,right)=>{
   const a=document.querySelector(`[data-call-path="${left}"]`).getBoundingClientRect();
   const b=document.querySelector(`[data-call-path="${right}"]`).getBoundingClientRect();
   return Math.sign(a.x-b.x);
  },left,right);
  const initial=await order('request__start','event__start');assert.notEqual(initial,0);
  async function toggle(path,expanded){
   await page.click('#fit');
   const prefix=`[data-call-path="${path}"]`;
   const element=await page.$(prefix+' > .group-header')||await page.$(prefix+' > .node-card');
   const box=await element.boundingBox();await page.mouse.click(box.x+box.width/2,box.y+box.height/2,{button:'right'});
   await page.click('#toggle');
   await page.waitForFunction((path,expanded)=>{
    const element=document.querySelector(`[data-call-path="${path}"]`);
    return !!element&&!!element.querySelector(':scope > .group-header')===expanded;
   },{},path,expanded);
   assert.equal(await order('request__start','event__start'),initial,'expansion changed the entrance order');
  }
  await toggle('request__boundary',true);
  assert.equal(await page.$('[data-call-path="event__boundary"] > .group-header'),null);
  await toggle('event__boundary',true);
  for(const parent of ['request__boundary','event__boundary']){
   const first=parent+'/first',second=parent+'/second';
   const before=await order(first,second);assert.notEqual(before,0);
   for(const [path,expanded] of [[first,true],[second,true],[first,false],[second,false]]){
    await toggle(path,expanded);assert.equal(await order(first,second),before,'expansion changed nested branch order');
   }
  }
  await toggle('request__boundary',false);await toggle('event__boundary',false);
  assert.deepEqual(errors,[]);console.log(JSON.stringify({entrance_order:true,nested_order:true,instance_selection:true,page_errors:errors}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
