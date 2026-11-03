const {createRequire}=require('node:module'),assert=require('node:assert/strict');
const [manifest,url,kind]=process.argv.slice(2),puppeteer=createRequire(manifest)('puppeteer');
(async()=>{
 const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],
  ...(process.env.PUPPETEER_EXECUTABLE_PATH?{executablePath:process.env.PUPPETEER_EXECUTABLE_PATH}:{})});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(url);
  const type=async(selector,value)=>{await page.click(selector);await page.keyboard.down('Control');await page.keyboard.press('a');await page.keyboard.up('Control');await page.keyboard.type(value);};
  if(kind==='linear'){
   assert.equal(await page.$eval('#output',e=>e.textContent),'');
   await page.click('#run');await page.waitForFunction(()=>document.querySelector('#output').textContent==='15');
   await type('#x','2');await type('#a','4');await type('#b','1');
   await page.click('#run');await page.waitForFunction(()=>document.querySelector('#output').textContent==='5');
  }else{
   for(const values of [['4','-1'],['2']]){
    await page.click('#start');await page.waitForFunction(()=>document.querySelector('#state').textContent==='运行中');
    for(const value of values){
     const length=await page.$eval('#history',e=>JSON.parse(e.textContent).length);
     await type('#value',value);await page.click('#send');
     await page.waitForFunction(length=>JSON.parse(document.querySelector('#history').textContent).length===length+1,{},length);
    }
    await page.click('#stop');await page.waitForFunction(()=>document.querySelector('#state').textContent==='已停止');
   }
   assert.deepEqual(await page.$eval('#history',e=>JSON.parse(e.textContent)),[14,-1,8]);
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({kind,errors}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
