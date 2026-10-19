/* Exercise producer snapshots in a real offline page, including historical deep links. */
const {createRequire}=require('node:module');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');
const [renderer,entry,...ids]=process.argv.slice(2);
const puppeteer=createRequire(renderer)('puppeteer');
(async()=>{
  const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
  const errors=[],network=[];
  try{
    const page=await browser.newPage();await page.setViewport({width:1600,height:1000});
    page.on('pageerror',e=>errors.push(e.message));
    await page.setRequestInterception(true);page.on('request',r=>{if(/^https?:/.test(r.url())){network.push(r.url());r.abort();}else r.continue();});
    const context=async path=>page.$eval('[data-call-path="'+path+'"]',e=>e.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:700,clientY:300})));
    const details=()=>page.$eval('#details',e=>Object.fromEntries([...e.querySelectorAll('dt')].map(k=>[k.textContent,k.nextElementSibling.textContent])));
    for(const id of ids){
      // A plain link from the prompt must select this snapshot, not the newest record.
      await page.goto(pathToFileURL(entry).href+'#'+new URLSearchParams({snapshot:id,view:'flow'}));
      await page.waitForSelector('[data-call-path="first"]');
      assert.equal(await page.$eval('.record.active',e=>e.dataset.recordId),id);
      for(const path of ['future','first','second','empty','loop','override']){
        assert.match(await page.$eval('[data-call-path="'+path+'"]',e=>e.textContent),/计划 · 尚未实现/);
        await context(path);const info=await details();
        assert.equal(info['状态'],'planned');
        assert.equal(info.kind,['future','empty'].includes(path)?'blocking':'transparent');
        if(['first','second','empty','loop'].includes(path)){
          assert.equal(info['调用声明状态'],'implemented');assert.equal(info['目标定义状态'],'planned');
        }
      }
      await context('empty');assert(await page.$eval('#toggle',e=>e.disabled));
      const text=await page.$eval('[data-call-path="empty"]',e=>e.textContent);
      assert.match(text,/暂无内部定义/);assert(!text.includes('可展开')&&!text.includes('可右键展开'));
      assert.equal(await page.$$eval('[data-call-path="first/child"]',e=>e.length),0);
      await context('first');assert.equal(await page.$eval('#toggle',e=>e.disabled),false);
      await page.click('#toggle');await page.waitForSelector('[data-call-path="first/child"]');
      assert.equal(await page.$$eval('[data-call-path="second/child"]',e=>e.length),0);
      await context('loop');await page.click('#toggle');await page.waitForSelector('[data-call-path="loop/child"]');
      await context('first');await page.click('#toggle');await page.waitForFunction(()=>!document.querySelector('[data-call-path="first/child"]'));
    }
    // Hold an expansion's layout while switching to another snapshot. Its completion must be ignored.
    await page.waitForSelector('[data-call-path="first"]');
    await page.evaluate(()=>{
      const body=VFLayout.body;let held=false;
      VFLayout.body=async(...args)=>{
        if(!held){held=true;window.layoutHeld=true;await new Promise(resolve=>window.releaseLayout=resolve);}
        return body(...args);
      };
    });
    await context('first');await page.click('#toggle');await page.waitForFunction(()=>window.layoutHeld);
    await page.evaluate(id=>{
      document.querySelector('.record[data-record-id="'+id+'"]').click();window.releaseLayout();
    },ids[0]);
    await page.waitForFunction(id=>document.querySelector('.record.active')?.dataset.recordId===id&&document.querySelector('[data-call-path="first"]'),{},ids[0]);
    assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
    console.log(JSON.stringify({targets:ids.length,page_errors:errors,network_requests:network}));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
