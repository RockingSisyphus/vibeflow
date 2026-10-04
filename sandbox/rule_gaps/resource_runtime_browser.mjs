/** Run the actual browser AOT module over HTTP, without Node execution shims. */
import {createRequire} from "node:module";
import {createServer} from "node:http";
import {readFile} from "node:fs/promises";
import {dirname,resolve} from "node:path";
const [renderer,entry,script]=process.argv.slice(2);
const puppeteer=createRequire(renderer+"/package.json")("puppeteer");
const root=dirname(entry);
const server=createServer(async(req,res)=>{
  if(req.url==="/"){res.setHeader("Content-Type","text/html");res.end("<!doctype html><title>Resource Host acceptance</title>");return;}
  try{const file=resolve(root,"."+req.url);if(!file.startsWith(root+"/"))throw Error("invalid path");res.setHeader("Content-Type",file.endsWith(".js")?"application/javascript":"text/plain");res.end(await readFile(file));}
  catch {res.statusCode=404;res.end();}
});
await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
const browser=await puppeteer.launch({headless:true,args:["--no-sandbox","--disable-dev-shm-usage"]});
try{
  const page=await browser.newPage();await page.goto("http://127.0.0.1:"+server.address().port);
  const result=await page.evaluate(async({script})=>{const workflow=await import("/index.js");return await new Function("workflow","return (async()=>{"+script+"})()")(workflow);},{script});
  console.log(JSON.stringify(result));
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
