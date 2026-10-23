// Load a single bundle in a real, headless page. No asset/coordinator server.
const {createRequire}=require("node:module");
const puppeteer=createRequire(process.argv[2])("puppeteer");
(async()=>{
  const browser=await puppeteer.launch({headless:true,
    executablePath:process.env.PUPPETEER_EXECUTABLE_PATH,
    args:["--no-sandbox","--disable-setuid-sandbox"]});
  try{
    const page=await browser.newPage();
    await page.goto("about:blank");
    const requests=[];
    page.on("request",request=>requests.push(request.url()));
    await page.setOfflineMode(true);
    await page.addScriptTag({path:process.argv[3]});
    const result=await page.evaluate(()=>CooperativeMath.run());
    if(requests.length)throw Error("unexpected network requests: "+JSON.stringify(requests));
    console.log(JSON.stringify({...result,headless:true,networkRequests:requests.length}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
