/* Standard browser host acceptance with real HTTP/CORS and emitted workflow. */
const {createRequire}=require('node:module'),assert=require('node:assert/strict');
const [renderer,base,url]=process.argv.slice(2),puppeteer=createRequire(renderer)('puppeteer');
(async()=>{
 const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
 try {
  const page=await browser.newPage();await page.goto(base+'/index.html');
  const result=await page.evaluate(async(url)=>{
   const {runWorkflowAsync}=await import('./workflow.mjs');
   const {runConnected}=await import('./workflow_host.mjs');
   const first=await runConnected(runWorkflowAsync,{url,workflow:'browser-0'});
   let cancelled=false;
   try {await runConnected(runWorkflowAsync,{url,workflow:'browser-1'});}
   catch(error){cancelled=error.code==='VF_ABORTED'||error.name==='AbortError';}
   return {first,cancelled};
  },url);
  assert.deepEqual(result,{first:{result:42},cancelled:true});
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
