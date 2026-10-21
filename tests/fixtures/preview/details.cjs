/* Inspect real Python/JavaScript facts through the offline UI. */
const {createRequire}=require('node:module'),{pathToFileURL}=require('node:url'),{join,dirname}=require('node:path'),assert=require('node:assert/strict');
const [renderer,entry,...ids]=process.argv.slice(2),puppeteer=createRequire(renderer)('puppeteer');
(async()=>{const browser=await puppeteer.launch({executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
try{const page=await browser.newPage();await page.setViewport({width:1700,height:1100});const errors=[],network=[];
page.on('pageerror',e=>errors.push(e.message));await page.setRequestInterception(true);page.on('request',r=>{if(/^https?:/.test(r.url())){network.push(r.url());r.abort();}else r.continue();});
const targets=[];
for(const id of ids){
 await page.goto(pathToFileURL(entry).href+'#'+new URLSearchParams({snapshot:id,view:'flow'}));await page.waitForSelector('[data-call-path="emit"]');
 const target=await page.$eval('#identity',e=>e.textContent.split(' · ')[0]);targets.push(target);
 const locate=async value=>{await page.$eval('#search',(e,v)=>e.value=v,value);await page.click('#search-form button');await page.waitForSelector(`[data-call-path="${value}"]`);await page.waitForFunction(v=>document.querySelector('#details h3').textContent===v,{},value);};
 await locate('emit');assert.match(await page.$eval('[data-call-path="emit"] .node-card',e=>e.textContent),/调用职责：emit/);
 const detail=await page.$eval('#details',e=>e.innerText);
 for(const expected of ['类型定义：emit 的完整职责说明。','结果携带本次计算的完整数值。','默认参数','参数约束','调用参数','factor'])assert(detail.includes(expected),target+' missing '+expected);
 const raw=await page.$eval('#details details pre',e=>JSON.parse(e.textContent));assert(raw.call&&raw.node_definition);
 const edge=async(from,to)=>page.$eval(`.edge-line[data-from="${from}"][data-to="${to}"]`,e=>({kind:e.dataset.edgeKind,color:getComputedStyle(e).stroke,dash:getComputedStyle(e).strokeDasharray,marker:e.getAttribute('marker-end'),id:e.dataset.edgeId}));
 const normal=await edge('start','emit'),parallel=await edge('emit','left'),data=await edge('emit','join'),joinEdge=await edge('left','join'),conditional=await edge('choice','yes');
 assert.equal(normal.kind,'flow');assert.equal(parallel.kind,'parallel');assert.equal(joinEdge.kind,'parallel');assert.equal(data.kind,'data');assert.notEqual(data.dash,'none');assert.equal(normal.dash,'none');assert.notEqual(parallel.color,normal.color);assert.notEqual(data.marker,normal.marker);assert.equal(conditional.kind,'flow');
 assert.equal(await page.$$('.edge-line[data-from="start"][data-to="emit"][data-edge-kind="data"]').then(es=>es.length),1);
 // Click the actual enlarged edge hit target, also when the canvas is zoomed.
 const clickEdge=async(from,to)=>{
  await locate(from);await page.$eval('#zoom',e=>{e.value='50%';e.dispatchEvent(new Event('change'));});
  const point=await page.$eval(`.edge-line[data-from="${from}"][data-to="${to}"]`,e=>{const p=e.getPointAtLength(e.getTotalLength()*.55),q=new DOMPoint(p.x,p.y).matrixTransform(e.getScreenCTM());return {x:q.x,y:q.y,id:e.dataset.edgeId};});
  // Center a real interior point on screen without relying on label placement.
  await page.mouse.move(700,400);await page.mouse.down();await page.mouse.move(700+750-point.x,400+450-point.y,{steps:5});await page.mouse.up();
  await page.mouse.click(750,450);await page.waitForFunction(()=>document.querySelector('#details h3').textContent!=='emit'&&document.querySelector('#details h3').textContent!=='choice'&&document.querySelector('#details h3').textContent!=='start');
  return page.$eval('#details',e=>e.innerText);
 };
 const transfer=await clickEdge('emit','join');for(const expected of ['仅传递数据','fixture.payload','结果携带本次计算的完整数值。','消费上游结果，不重新计算。','否'])assert(transfer.includes(expected),target+' edge missing '+expected);
 assert.equal(await page.$$('.edge-selected').then(es=>es.length),1);
 const condition=await clickEdge('choice','yes');assert(condition.includes("route == 'yes'"));
 const schedule=await clickEdge('start','emit');assert(schedule.includes('此边未声明数据传递。'));
 // A data-only shortcut must not contribute to fan-out; safe_any is not an all-join.
 const projection=await page.evaluate(()=>{
  const nodes=[{id:'a',flow_kind:'process'},{id:'b'},{id:'c',join_policy:'safe_any'}];
  return VFModel.graphEdges({nodes,edges:[{from:'a',to:'b',roles:['mainline','schedule','transfer']},{from:'a',to:'c',roles:['data_bypass','transfer']},{from:'b',to:'c',roles:['schedule','transfer']}] }).map(e=>e.kind);
 });assert.deepEqual(projection,['flow','data','flow']);
 // Reopening the same record/view retains its selected edge and camera.
 const transform=await page.$eval('#scene',e=>e.getAttribute('transform'));
 await page.click('#tabs button:nth-child(2)');await page.waitForFunction(()=>document.getElementById('empty').textContent.includes('资源'));
 await page.click('#tabs button:first-child');await page.waitForFunction(()=>document.querySelector('.edge-selected'));
 assert.equal(await page.$eval('#scene',e=>e.getAttribute('transform')),transform);
 await locate('emit');await page.click('#fit');await page.screenshot({path:join(dirname(entry),'details-'+target+'.png')});
}
assert.deepEqual(errors,[]);assert.deepEqual(network,[]);console.log(JSON.stringify({targets,page_errors:errors,network_requests:network}));
}finally{await browser.close();}})().catch(e=>{console.error(e.stack);process.exitCode=1;});
