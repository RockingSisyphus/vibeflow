/* Real three-workflow graphs retain independent reading positions across jumps. */
const {createRequire}=require('node:module'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
const [renderer,entry,idsJson]=process.argv.slice(2),ids=JSON.parse(idsJson),puppeteer=createRequire(renderer)('puppeteer');
(async()=>{
 const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
 try{
  const page=await browser.newPage(),errors=[],network=[];
  await page.setViewport({width:1500,height:1100});
  page.on('pageerror',error=>errors.push(error.message));
  await page.setRequestInterception(true);page.on('request',request=>{if(/^https?:/.test(request.url())){network.push(request.url());request.abort();}else request.continue();});
  const waitRecord=async(id,name)=>{
   await page.waitForFunction((id,name)=>new URLSearchParams(location.hash.slice(1)).get('snapshot')===id&&
    document.querySelector('#records .record.active')?.dataset.recordId===id&&
    document.querySelector('#identity').textContent.startsWith(name+' · ')&&document.querySelector('#scene').children.length>0,{},id,name);
  };
  const reading=()=>page.evaluate(()=>({transform:document.querySelector('#scene').getAttribute('transform'),
   zoom:document.querySelector('#zoom').value,entry:document.querySelector('#entry').value,
   selected:document.querySelector('#details h3').textContent,
   expanded:Boolean(document.querySelector('[data-call-path="second_round/receive_next"]'))}));
  const position=async(percent)=>{
   await page.$eval('#zoom',(element,value)=>{element.value=value;element.dispatchEvent(new Event('change'));},percent);
   const bounds=await (await page.$('#viewport')).boundingBox();
   await page.mouse.move(bounds.x+20,bounds.y+30);await page.mouse.down();
   await page.mouse.move(bounds.x+65,bounds.y+60,{steps:5});await page.mouse.up();
  };
  const context=path=>page.$eval('[data-call-path="'+path+'"]',element=>element.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:650,clientY:250})));
  const sidebar=async(id,name)=>{await page.click('[data-record-id="'+id+'"]');await waitRecord(id,name);};
  const jump=async(path,id,name)=>{await context(path);await page.click('#context-targets button');await waitRecord(id,name);};
  await page.goto(pathToFileURL(entry).href+'#'+new URLSearchParams({snapshot:ids.a,workflow:'cooperation:configs/b.jsonc',view:'flow',entry:'calculate'}));
  await waitRecord(ids.b,'b');
  await sidebar(ids.a,'a');await page.select('#entry','calculate');
  await position('65%');await context('call');const a=await reading();
  await page.click('#context-targets button');await waitRecord(ids.b,'b');
  await context('second_round');await page.click('#toggle');await page.waitForSelector('[data-call-path="second_round/receive_next"]');
  await position('55%');await context('invoke');const b=await reading();
  await page.click('#context-targets button');await waitRecord(ids.c,'c');
  await position('150%');await context('shift');await page.click('#identity');const c=await reading();
  await sidebar(ids.a,'a');assert.deepEqual(await reading(),a);
  await sidebar(ids.b,'b');assert.deepEqual(await reading(),b);
  await sidebar(ids.c,'c');assert.deepEqual(await reading(),c);
  await sidebar(ids.a,'a');await jump('call',ids.b,'b');assert.deepEqual(await reading(),b);
  await jump('invoke',ids.c,'c');assert.deepEqual(await reading(),c);
  await page.goBack();await waitRecord(ids.b,'b');assert.deepEqual(await reading(),b);
  await page.goForward();await waitRecord(ids.c,'c');assert.deepEqual(await reading(),c);
  // Explicitly reading an older B keeps that record when A links back to B.
  await sidebar(ids.old_b,'b');await page.select('#entry','calculate');await position('95%');
  await context('invoke');const old=await reading();
  await sidebar(ids.a,'a');await jump('call',ids.old_b,'b');assert.deepEqual(await reading(),old);
  await sidebar(ids.b,'b');assert.deepEqual(await reading(),b);
  assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
  console.log(JSON.stringify({independentRecords:true,independentCamera:true,expanded:true,selection:true,history:true,olderTarget:true,errors,network}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
