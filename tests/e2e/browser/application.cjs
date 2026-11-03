/* Drive the actual application button; only read its visible result. */
const {createRequire}=require('node:module'),{pathToFileURL}=require('node:url');
const [manifest,entry]=process.argv.slice(2);
const puppeteer=createRequire(manifest)('puppeteer');
(async()=>{
 const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],
  ...(process.env.PUPPETEER_EXECUTABLE_PATH?{executablePath:process.env.PUPPETEER_EXECUTABLE_PATH}:{})});
 try{
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(/^https?:/.test(entry)?entry:pathToFileURL(entry).href);
  await page.click('#run');
  await page.waitForFunction(()=>document.querySelector('#result').textContent.length>0,{timeout:90000});
  const output=await page.$eval('#result',e=>e.textContent);
  if(errors.length)throw Error(errors.join('\n'));
  console.log(output);
 }finally{await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
