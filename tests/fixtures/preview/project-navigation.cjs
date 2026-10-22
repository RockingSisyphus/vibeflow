/* Actual file:// navigation, latest snapshot selection and operation styling. */
const {createRequire}=require('node:module'),{pathToFileURL}=require('node:url'),assert=require('node:assert/strict');
const [renderer,entry,caller,worker,styleJson]=process.argv.slice(2),puppeteer=createRequire(renderer)('puppeteer');
(async()=>{
 const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
 try{
  const page=await browser.newPage(),errors=[],network=[];await page.setViewport({width:1500,height:1000});
  page.on('pageerror',e=>errors.push(e.message));
  await page.setRequestInterception(true);page.on('request',r=>{if(/^https?:/.test(r.url())){network.push(r.url());r.abort();}else r.continue();});
  await page.goto(pathToFileURL(entry).href);await page.waitForSelector('[data-call-path="work"]');
  assert.equal(await page.$eval('[data-call-path="work"] .node-card',e=>e.dataset.workflowOperation),'multiple');
  await page.click('[data-call-path="work"]');assert.match(await page.$eval('#details',e=>e.textContent),/workflow 操作 · multiple/);
  const styles=await page.evaluate(presentations=>{
    const rows=['call','wait','send','receive','kill','self'].map(operation=>{
      const facts={id:operation,preview_operations:[{capability:'vibeflow.workflow',operation}],presentation:presentations[operation]};
      const card=VFShapes.measure(facts),element=VFShapes.draw(card,facts);
      return {shape:element.dataset.shape,fill:element.querySelector('.card-outline').getAttribute('fill')};
    });
    const custom=VFShapes.measure({id:'custom',preview_operations:[{capability:'vibeflow.workflow',operation:'call'}],presentation:{values:{shape:'diamond',fill:'#123456'},sources:{shape:'call',fill:'call'}}});
    const planned=VFShapes.measure({id:'planned',status:'planned',preview_operations:[{capability:'vibeflow.workflow',operation:'wait'}],presentation:{values:{fill:'#abcdef'},sources:{fill:'status'}}});
    return {rows,custom:{shape:custom.shape,fill:custom.values.fill},planned:planned.values.fill};
  },JSON.parse(styleJson));
  assert.equal(new Set(styles.rows.map(s=>s.shape)).size,6);assert.equal(styles.rows[0].fill,'#fef3c7');assert.equal(styles.rows[2].fill,'#e0f2fe');assert.equal(styles.rows[3].fill,'#1e3a8a');assert.equal(styles.rows[4].fill,'#ffe4e6');
  assert.deepEqual(styles.custom,{shape:'diamond',fill:'#123456'});assert.equal(styles.planned,'#abcdef');
  await page.select('#navigation','project');
  assert.equal(await page.$$eval('.project-root',es=>es.length),3);
  assert.equal(await page.$$eval('#records [data-workflow-id]',es=>es.length),5);
  assert.equal(await page.$('[data-root-id="retired"]'),null);
  for(const id of ['worker:configs/deleted.jsonc'])assert.equal(await page.$(`[data-workflow-id="${id}"]`),null);
  assert.equal(await page.$eval('[data-workflow-id="caller:configs/workflow.jsonc"]',e=>e.dataset.recordId),caller);
  assert.match(await page.$eval('[data-workflow-id="caller:configs/workflow.jsonc"]',e=>e.textContent),/最新.*更新于/s);
  assert.match(await page.$eval('[data-workflow-id="worker:configs/future.jsonc"]',e=>e.textContent),/尚未生成审核图.*源文件更新于/s);
  assert.equal(await page.$eval('[data-workflow-id="worker:configs/future.jsonc"]',e=>e.disabled),true);
  assert.match(await page.$eval('[data-workflow-id="worker:configs/broken.jsonc"]',e=>e.textContent),/配置有误/);
  assert.match(await page.$eval('[data-root-id="empty"]',e=>e.textContent),/暂无 workflow/);
  await page.click('[data-workflow-id="worker:configs/workflow.jsonc"]');
  await page.waitForFunction(id=>location.hash.includes('snapshot='+id)&&document.querySelector('[data-call-path="alternate"]'),{},worker);
  await page.click('[data-workflow-id="caller:configs/workflow.jsonc"]');
  await page.waitForFunction(id=>location.hash.includes('snapshot='+id)&&document.querySelector('[data-call-path="gui"]'),{},caller);
  await page.select('#navigation','history');assert.equal(await page.$$eval('#records .record',es=>es.length),6);
  await page.select('#category','review');assert.equal(await page.$$eval('#records .record',es=>es.length),2);
  await page.select('#navigation','project');assert.equal(await page.$$eval('#records [data-workflow-id]',es=>es.length),5);
  const fs=require('node:fs'),path=require('node:path'),recordPath=path.join(path.dirname(entry),'vibeflow-preview','snapshots',caller,'record.json');
  const updated=JSON.parse(fs.readFileSync(recordPath,'utf8'));updated.updated_at=new Date(Date.now()+1000).toISOString();updated.revision++;
  fs.appendFileSync(path.join(path.dirname(entry),'vibeflow-preview','index.js'),'VibeFlowPreview.record('+JSON.stringify(updated)+');\n');
  await page.click('[data-root-id="empty"]>summary');
  await page.click('#refresh');await page.waitForFunction(stamp=>document.querySelector('[data-workflow-id="caller:configs/workflow.jsonc"]').textContent.includes(new Date(stamp).toLocaleString()),{},updated.updated_at);
  assert.equal(await page.$eval('[data-root-id="empty"]',e=>e.open),false);
  assert.equal(await page.$eval('[data-workflow-id="caller:configs/workflow.jsonc"]',e=>e.dataset.recordId),caller);
  if(process.env.VIBEFLOW_PROJECT_SCREENSHOT){await page.click('#project-overview>summary');await page.$eval('#project-content details',e=>e.open=true);await page.click('#fit');await page.screenshot({path:process.env.VIBEFLOW_PROJECT_SCREENSHOT,fullPage:true});}
  const catalogPath=path.join(path.dirname(entry),'vibeflow-preview','project.js');
  const catalog=JSON.parse(fs.readFileSync(catalogPath,'utf8').slice('VibeFlowPreview.project('.length,-3));
  fs.unlinkSync(path.join(path.dirname(entry),'worker','configs','workflow.jsonc'));
  catalog.roots.find(root=>root.id==='worker').workflows=catalog.roots.find(root=>root.id==='worker').workflows.filter(w=>w.id!=='worker:configs/workflow.jsonc');
  fs.writeFileSync(catalogPath,'VibeFlowPreview.project('+JSON.stringify(catalog)+');\n');
  await page.click('#refresh');await page.waitForFunction(()=>document.querySelectorAll('#records [data-workflow-id]').length===4);
  assert.equal(await page.$('[data-workflow-id="worker:configs/workflow.jsonc"]'),null);
  await page.select('#navigation','history');await page.select('#category','');
  assert.equal(await page.$$eval('#records .record',es=>es.length),6);
  await page.select('#navigation','project');
  fs.unlinkSync(catalogPath);
  await page.click('#refresh');await page.waitForFunction(()=>document.querySelectorAll('.project-root').length===0);
  assert.match(await page.$eval('#project-note',e=>e.textContent),/缺少项目目录/);
  assert.equal(await page.$$eval('#records .record',es=>es.length),0);
  await page.select('#navigation','history');assert.equal(await page.$$eval('#records .record',es=>es.length),6);
  assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
  console.log(JSON.stringify({roots:3,workflows:5,latest:true,history:true,deleted:true,unregistered:true,missingInventory:true,styles,errors,network}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
