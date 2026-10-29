/* Real pointer interaction with a synthetic multi-entry preview over loopback HTTP. */
const assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const [renderer,url]=process.argv.slice(2);
const puppeteer=createRequire(renderer)('puppeteer');
(async()=>{
  const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],
    executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
  try {
    const page=await browser.newPage(),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setViewport({width:1500,height:1000});await page.goto(url);
    await page.waitForSelector('[data-call-path="event__boundary"]');
    const order=async paths=>page.evaluate(paths=>paths.map(path=>{
      const element=document.querySelector(`[data-call-path="${path}"]`);
      const box=element.getBoundingClientRect();return {x:box.x,y:box.y,width:box.width,height:box.height};
    }),paths);
    const branchOrder=async()=>{
      const [request,event]=await order(['request__start','event__start']);
      assert(request.x+request.width<event.x,'expansion swapped or overlapped the entrance branches');
    };
    async function toggle(path,expanded){
      await page.click('#fit');
      const element=await page.$(`[data-call-path="${path}"] > ${expanded?'.node-card':'.group-header'}`);
      const box=await element.boundingBox();
      await page.mouse.click(box.x+box.width/2,box.y+box.height/2,{button:'right'});
      assert.equal(await page.$eval('#details h3',e=>e.textContent),path.split('/').pop());
      await page.click('#toggle');
      await page.waitForFunction((path,expanded)=>{
        const element=document.querySelector(`[data-call-path="${path}"]`);
        return element&&Boolean(element.querySelector(':scope > .group-header'))===expanded;
      },{},path,expanded);
      await branchOrder();
    }
    const relativeHeight=async()=>{
      const [start,boundary]=await order(['event__start','event__boundary']);
      const scale=await page.$eval('#zoom',e=>parseFloat(e.value)/100);
      return (boundary.y-start.y)/scale;
    };
    await page.click('#actual');const before=await relativeHeight();await branchOrder();
    await toggle('request__boundary',true);
    assert.equal(await page.$('[data-call-path="event__boundary"] > .group-header'),null);
    // The other branch keeps its internal layering as well as its left/right position.
    await page.click('#actual');assert(Math.abs(await relativeHeight()-before)<1);
    await toggle('event__boundary',true);
    for(const parent of ['request__boundary','event__boundary']){
      const paths=[parent+'/first',parent+'/second'];
      const check=async()=>{const [first,second]=await order(paths);assert(first.x+first.width<second.x,'nested branches changed order');};
      await check();await toggle(paths[0],true);await check();
      await toggle(paths[1],true);await check();
      await toggle(paths[0],false);await check();await toggle(paths[1],false);await check();
    }
    await toggle('request__boundary',false);await toggle('event__boundary',false);
    await page.click('#collapse');await page.waitForFunction(()=>document.querySelectorAll('[data-call-path]').length===6);
    await branchOrder();assert.deepEqual(errors,[]);
    console.log(JSON.stringify({entrance_order:true,nested_order:true,instance_selection:true,independent_layering:true,page_errors:errors}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
