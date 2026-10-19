/* Real file:// browser acceptance. The producer supplies facts; the browser owns shapes and layout. */
const {createRequire}=require('node:module');
const {pathToFileURL}=require('node:url');
const {join,dirname}=require('node:path');
const {writeFile,readFile}=require('node:fs/promises');
const assert=require('node:assert/strict');
const [renderer,entry,pythonId,javascriptId,standalone]=process.argv.slice(2);
const puppeteer=createRequire(renderer)('puppeteer');
(async()=>{
  const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
  const errors=[],network=[];
  try {
    const page=await browser.newPage();await page.setViewport({width:1500,height:1000});
    page.on('pageerror',e=>errors.push(e.message));
    await page.setRequestInterception(true);page.on('request',r=>{if(/^https?:/.test(r.url())){network.push(r.url());r.abort();}else r.continue();});
    if(pythonId==='--resources') {
      await page.goto(pathToFileURL(entry).href);
      await page.waitForSelector('[data-call-path]');
      for(const [index,id] of [[2,'base_lib:layout.helper'],[3,'plugin_declaration:layout.resources']]) {
        await page.click(`#tabs button:nth-child(${index})`);
        await page.waitForFunction(id=>[...document.querySelectorAll('[data-resource-id]')].some(e=>e.dataset.resourceId===id),{},id);
        await page.click('[data-resource-id="'+id+'"]');
        assert.match(await page.$eval('#details',e=>e.textContent),/source|sources/);
        assert(await page.$eval('[data-resource-id="'+id+'"]',e=>e.querySelector('.node-card')!==null));
        if(index===2){
          assert.equal(await page.$eval('[data-resource-id="'+id+'"] .card-outline',e=>getComputedStyle(e).fill),'rgb(255, 230, 179)');
          await page.click('[data-resource-id="node:layout.step"]');
          const text=await page.$eval('#details',e=>e.innerText);
          assert(text.includes('输出契约')&&text.includes('The calculated fixture value.'));
          const linked=await page.$eval('#details details pre',e=>JSON.parse(e.textContent));
          assert(linked.node_type&&linked.resource);
          assert(text.includes('最终样式')&&text.includes('#d6eaff'));
        }
      }
      await page.click('#tabs button:nth-child(4)');
      await page.waitForFunction(()=>document.getElementById('empty').textContent.includes('资源'));
      assert.equal(await page.$$('.resource-card').then(e=>e.length),0);
      assert.equal(errors.length,0);assert.equal(network.length,0);
      console.log(JSON.stringify({resources:true,page_errors:errors,network_requests:network}));return;
    }
    await page.goto(pathToFileURL(entry).href+'#'+new URLSearchParams({snapshot:pythonId,view:'flow'}));
    const wait=async count=>page.waitForFunction(n=>document.querySelectorAll('[data-call-path]').length===n,{},count);
    await wait(4);
    const geometry=await page.evaluate(()=>{
      const svg=VFShapes.node('svg',{width:1200,height:1000});document.body.append(svg);
      const shapes=['rect','rounded','stadium','circle','dbl-circ','diamond','lean-r','lean-l','trap-b','hex','fr-rect','cyl','doc','cloud'];
      const failures=[];
      for(const shape of shapes){
        const facts={id:shape,display_name:'Readable card',presentation:{values:{shape}}};
        const card=VFShapes.measure(facts),graphic=VFShapes.draw(card,facts);svg.append(graphic);
        const item={x:2000,y:3000,width:card.width,height:card.height,card};
        const shell=graphic.querySelector('.card-outline'),cx=card.width/2,cy=card.height/2;
        for(let i=0;i<40;i++){
          const angle=i*Math.PI/20,ux=Math.cos(angle),uy=Math.sin(angle);
          const p=VFShapes.connection(item,{x:item.x+cx+ux*2000,y:item.y+cy+uy*2000});
          const x=p.x-item.x,y=p.y-item.y;
          // Independent browser SVG fill geometry, rather than the canvas path used by routing.
          if(!shell.isPointInFill(new DOMPoint(x-ux*.3,y-uy*.3))||shell.isPointInFill(new DOMPoint(x+ux*.3,y+uy*.3)))failures.push({shape,i,x,y});
        }
        graphic.remove();
      }
      const resource={kind:'node',type_key:'fixture.external',display_name:'External resource',external:true};
      const resourceCard=VFShapes.measure(resource,{'fixture.external':{external:true,contract:{requires:[{key:'input'}],provides:[]}}});
      const rows=resourceCard.rows.map(r=>r.text);
      svg.remove();return {failures,rows};
    });
    assert.deepEqual(geometry.failures,[]);assert(geometry.rows.includes('外部依赖'));
    assert(geometry.rows.includes('fixture.external'));assert(geometry.rows.includes('1 输入 · 0 输出'));
    const icons=await page.evaluate(async()=>{
      const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
      svg.style.cssText='position:fixed;left:-10000px;top:0;width:1200px;height:500px';document.body.append(svg);
      const cards=['fab:fa-github','far fa-circle','fa:fa-user','M'].map((icon,index)=>{
        const facts={id:'icon-'+index,display_name:'图标标题',presentation:{values:{icon}}};
        const card=VFShapes.draw(VFShapes.measure(facts),facts);card.setAttribute('transform',`translate(${index*280},0)`);svg.append(card);return card;
      });
      await document.fonts.ready;
      const results=cards.map(card=>{
        const div=card.querySelector('foreignObject div'),style=div?getComputedStyle(div,'::before'):null;
        const icon=card.querySelector('foreignObject,.card-icon').getBoundingClientRect(),title=card.querySelector('.card-title').getBoundingClientRect();
        return {family:style?.fontFamily,weight:style?.fontWeight,overlaps:icon.bottom>title.top};
      });svg.remove();return results;
    });
    assert.match(icons[0].family,/Brands/);assert.equal(icons[0].weight,'400');
    assert.match(icons[1].family,/Free/);assert.equal(icons[1].weight,'400');
    assert.match(icons[2].family,/Free/);assert.equal(icons[2].weight,'900');
    assert(icons.every(icon=>!icon.overlaps));
    if(standalone){
      await page.goto(pathToFileURL(standalone).href+'#'+new URLSearchParams({snapshot:pythonId,view:'flow'}));
      await wait(4);
      assert.equal(await page.$eval('[data-call-path="first"] .node-card',e=>e.dataset.shape),'fr-rect');
      await page.goto(pathToFileURL(entry).href+'#'+new URLSearchParams({snapshot:pythonId,view:'flow'}));await wait(4);
    }
    async function locate(query,path=query){await page.$eval('#search',(e,p)=>e.value=p,query);await page.click('#search-form button');await page.waitForFunction(p=>document.querySelector(`[data-call-path="${p}"]`),{},path);}
    await locate('first/inner/shape_cloud');
    await page.waitForFunction(()=>document.querySelectorAll('[data-call-path^="first/inner/shape_"]').length===14);
    const shapes=await page.$$eval('[data-call-path^="first/inner/shape_"]',es=>es.map(e=>{
      const card=e.querySelector('.node-card'),graphic=card.querySelector('.card-outline');
      return {path:e.dataset.callPath,fill:getComputedStyle(graphic).fill,shape:card.dataset.shape,bbox:card.getBBox().width};
    }));
    assert.match(await page.$eval('[data-call-path="first/inner/shape_circle"]',e=>e.textContent),/外部依赖/);
    assert.equal(shapes.length,14);assert(shapes.every(s=>s.fill==='rgb(214, 234, 255)'&&s.bbox>0));
    assert.equal(new Set(shapes.map(s=>s.shape)).size,14);
    assert.equal(await page.$eval('[data-call-path="first/inner/shape_circle"] .card-outline',e=>e.tagName),'ellipse');
    assert.equal(await page.$eval('[data-call-path="first/inner/shape_diamond"] .card-outline',e=>e.tagName),'polygon');
    assert.equal(await page.$eval('[data-call-path="first/inner/shape_cloud"] .card-outline',e=>e.tagName),'path');
    const endpoints=await page.$$eval('path[data-from^="first/inner/shape_"]',paths=>paths.flatMap(path=>{
      const length=path.getTotalLength();return [path.getPointAtLength(0),path.getPointAtLength(length)].map(p=>({x:p.x,y:p.y}));
    }));
    assert.equal(endpoints.length,26);assert(endpoints.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
    // ELK needs actual label text to place it between nodes rather than at (0,0).
    const labelPosition=await page.evaluate(async()=>{
      const data={bodies:VFModel.bodies({workflow:{nodes:[{id:'a'},{id:'b'}],edges:[{from:'a',to:'b',when:'ready'}]}})};
      const graph=await VFLayout.body({data,state:{expanded:new Set()},elk:new ELK()},'workflow');
      return {label:graph.edges[0].labels[0],a:graph.values[0],b:graph.values[1]};
    });
    assert(labelPosition.label.y>labelPosition.a.y+labelPosition.a.height);
    assert(labelPosition.label.y+labelPosition.label.height<labelPosition.b.y);
    const deepPath='first/inner/shape_rect/'+Array(5).fill('next').join('/')+'/bottom';
    await locate('bottom',deepPath);
    await page.click('#collapse');await wait(4);await locate('first/inner/shape_cloud');
    // Panning begins on an inner Node; a click alone must retain selection behavior.
    const inner=await page.$('[data-call-path="first/inner/shape_cloud"] .node-card');const bounds=await inner.boundingBox();
    const before=await page.$eval('#scene',e=>e.getAttribute('transform'));
    await page.mouse.move(bounds.x+bounds.width/2,bounds.y+bounds.height/2);await page.mouse.down();
    await page.mouse.move(bounds.x+bounds.width/2+70,bounds.y+bounds.height/2+35,{steps:6});await page.mouse.up();
    assert.notEqual(await page.$eval('#scene',e=>e.getAttribute('transform')),before);
    await page.$eval('#zoom',e=>{e.value='1000%';e.dispatchEvent(new Event('change'));});
    assert.match(await page.$eval('#scene',e=>e.getAttribute('transform')),/scale\(10\)/);
    await page.click('#plus');assert.match(await page.$eval('#scene',e=>e.getAttribute('transform')),/scale\(12.5\)/);
    await page.click('#actual');await locate('first');
    // Right-click title/container preserves its screen anchor through layout.
    const center=async()=>page.$eval('[data-call-path="first"]',e=>{const b=e.getBoundingClientRect();return [b.x+b.width/2,b.y+b.height/2];});
    const anchor=await center();
    await page.$eval('[data-call-path="first"]',e=>e.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:700,clientY:300})));
    await page.click('#toggle');await wait(4);
    const after=await center();assert(Math.abs(after[0]-anchor[0])<1&&Math.abs(after[1]-anchor[1])<1);
    await locate('second/inner/shape_diamond');
    assert.equal(await page.$$eval('[data-call-path^="first/"]',es=>es.length),0);
    await page.click('#collapse');await wait(4);
    // Original SVG is the actual saved SVG, and mode/view state is independent.
    await page.select('#mode','original');await page.waitForSelector('#scene image');
    assert.equal(await page.$$eval('#scene [data-call-path]',es=>es.length),0);
    await page.select('#mode','structured');await wait(4);
    await page.click('#tabs button:nth-child(2)');await page.waitForFunction(()=>document.getElementById('empty').textContent.includes('资源'));
    assert(!await page.$('#scene .node-card'));
    await page.click('#tabs button:first-child');await wait(4);
    const stable=await page.$eval('#scene',e=>e.getAttribute('transform'));
    const index=join(dirname(entry),'vibeflow-preview/index.js');
    const script=await readFile(index,'utf8');
    // Add an unfinished run and ensure manual refresh preserves current snapshot/transform.
    const old=JSON.parse(script.split('\n').filter(Boolean)[0].slice('VibeFlowPreview.record('.length,-2));
    const run={...old,id:'unfinished',category:'run',status:'running',views:['flow']};
    const completed={...run,status:'succeeded',revision:50};
    await writeFile(index,script+[completed,run].map(r=>'VibeFlowPreview.record('+JSON.stringify(r)+');\n').join(''));
    await page.click('#refresh');await page.waitForFunction(()=>document.getElementById('count').textContent==='3 / 3');
    assert.equal(await page.$eval('#scene',e=>e.getAttribute('transform')),stable);
    await page.select('#category','run');assert.equal(await page.$$('.record').then(e=>e.length),1);
    assert.match(await page.$eval('.record',e=>e.textContent),/运行成功/);
    await page.click('.record');await page.waitForFunction(()=>document.getElementById('empty').textContent.includes('snapshot.js'));
    await page.select('#category','');
    const snapshotPath=join(dirname(entry),'vibeflow-preview/snapshots',pythonId,'snapshot.js');
    const payload=JSON.parse((await readFile(snapshotPath,'utf8')).slice('VibeFlowPreview.snapshot('.length,-3));
    // An in-progress preview becomes viewable after manual refresh, without
    // changing the selected operation or pretending it already passed.
    const pending={...old,id:'pending',category:'review',status:'reviewing',views:[]};
    await writeFile(index,script+'VibeFlowPreview.record('+JSON.stringify(pending)+');\n');
    await page.click('#refresh');await page.waitForSelector('[data-record-id="pending"]');
    await page.click('[data-record-id="pending"]');
    await page.waitForFunction(()=>document.getElementById('empty').textContent.includes('正在生成'));
    const pendingDir=join(dirname(entry),'vibeflow-preview/snapshots/pending');
    await require('node:fs/promises').mkdir(pendingDir,{recursive:true});
    await writeFile(join(pendingDir,'snapshot.js'),'VibeFlowPreview.snapshot('+JSON.stringify({...payload,id:'pending'})+');\n');
    await writeFile(index,script+'VibeFlowPreview.record('+JSON.stringify({...pending,status:'passed',revision:50,views:['flow']})+');\n');
    await page.click('#refresh');await wait(4);
    assert.equal(new URLSearchParams((await page.url()).split('#')[1]).get('snapshot'),'pending');
    // Historical links choose the latest past target, even when a future snapshot exists.
    const mainLines=script.split('\n').filter(Boolean).map(s=>JSON.parse(s.slice('VibeFlowPreview.record('.length,-2)));
    const mainRecord=mainLines.filter(r=>r.id===pythonId).reduce((a,b)=>a.revision>b.revision?a:b);
    mainRecord.created_at='2026-01-01T00:00:00.123400+00:00';mainRecord.revision++;
    const targetWorkflow={id:'remote:other.jsonc',root_id:'remote',path:'other.jsonc',name:'历史目标工作流',target:'python'};
    const past={...mainRecord,id:'target-past',workflow:targetWorkflow,created_at:'2026-01-01T00:00:00.123300+00:00'};
    const future={...past,id:'target-future',created_at:'2026-01-01T00:00:00.123500+00:00'};
    const fs=require('node:fs/promises');
    for(const record of [past,future]){
      const dir=join(dirname(entry),'vibeflow-preview/snapshots',record.id);await fs.mkdir(dir,{recursive:true});
      await writeFile(join(dir,'snapshot.js'),'VibeFlowPreview.snapshot('+JSON.stringify({...payload,id:record.id,workflow:targetWorkflow})+');\n');
    }
    await writeFile(index,script+[mainRecord,past,future].map(r=>'VibeFlowPreview.record('+JSON.stringify(r)+');\n').join(''));
    await page.click('#refresh');await page.waitForFunction(()=>document.getElementById('count').textContent==='4 / 4');
    await page.goto(pathToFileURL(entry).href+'#'+new URLSearchParams({snapshot:pythonId,view:'flow',call:'first'}));await page.reload();await wait(4);
    await page.waitForSelector('.selection-outline');
    assert.ok(await page.$$eval('#details button',buttons=>buttons.some(b=>b.textContent.startsWith('来源 · '))));
    const originalPosition=await page.$eval('#scene',e=>e.getAttribute('transform'));
    await page.$$eval('#details button',buttons=>buttons.find(b=>b.textContent.startsWith('历史目标')).click());
    await page.waitForFunction(()=>new URLSearchParams(location.hash.slice(1)).get('snapshot')==='target-past');
    assert.equal(await page.$eval('#identity',e=>e.textContent.split(' · ')[0]),'历史目标工作流');
    await page.goBack();await wait(4);assert.equal(new URLSearchParams((await page.url()).split('#')[1]).get('snapshot'),pythonId);
    assert.equal(await page.$eval('#scene',e=>e.getAttribute('transform')),originalPosition);
    await page.click('#tabs button:last-child');
    await page.waitForFunction(()=>document.querySelectorAll('.resource-card').length===3);
    assert.equal(await page.$$('.edge-line').then(es=>es.length),3);
    await page.click('[data-resource-id="remote:other.jsonc"]');
    await page.$$eval('#details button',buttons=>buttons.find(b=>b.textContent.startsWith('查看 workflow')).click());
    await page.waitForFunction(()=>new URLSearchParams(location.hash.slice(1)).get('snapshot')==='target-past');
    await page.goBack();await page.waitForFunction(()=>document.querySelectorAll('.resource-card').length===3);
    await page.click('#tabs button:first-child');await wait(4);
    assert.equal(await page.$eval('#scene',e=>e.getAttribute('transform')),originalPosition);
    await page.$$eval('#details button',buttons=>buttons.find(b=>b.textContent.startsWith('缺失目标')).click());
    assert.match(await page.$eval('#details',e=>e.textContent),/absent.jsonc/);
    await page.goto(pathToFileURL(entry).href+'#'+new URLSearchParams({snapshot:javascriptId,view:'flow'}));await page.reload();await wait(4);
    await locate('loop/inner/shape_dbl_circ');
    await page.waitForFunction(()=>document.querySelectorAll('[data-call-path^="loop/inner/shape_"]').length===14);
    await page.select('#mode','original');
    await page.waitForFunction(()=>document.getElementById('empty').textContent.includes('review --with-svg'));
    // An explicitly rendered attachment may finish after facts have been cached.
    // Refresh its metadata without reloading the page or resetting native state.
    const jsSnapshotPath=join(dirname(entry),'vibeflow-preview/snapshots',javascriptId,'snapshot.js');
    const jsPayload=JSON.parse((await readFile(jsSnapshotPath,'utf8')).slice('VibeFlowPreview.snapshot('.length,-3));
    await writeFile(join(dirname(jsSnapshotPath),'review.svg'),'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><rect width="200" height="100" fill="#abcdef"/></svg>');
    await writeFile(jsSnapshotPath,'VibeFlowPreview.snapshot('+JSON.stringify({...jsPayload,artifacts:{svg:'review.svg'}})+');\n');
    const jsRecord=mainLines.filter(r=>r.id===javascriptId).reduce((a,b)=>a.revision>b.revision?a:b);
    await writeFile(index,(await readFile(index,'utf8'))+'VibeFlowPreview.record('+JSON.stringify({...jsRecord,revision:jsRecord.revision+1,artifacts:{svg:'review.svg'}})+');\n');
    await page.click('#refresh');await page.waitForSelector('#scene image');
    await page.select('#mode','structured');
    await page.waitForSelector('[data-call-path="loop/inner/shape_dbl_circ"]');
    await page.screenshot({path:join(dirname(entry),'browser-acceptance.png')});
    console.log(JSON.stringify({shapes:shapes.length,network_requests:network,page_errors:errors}));
    assert.equal(errors.length,0);assert.equal(network.length,0);
  }finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
