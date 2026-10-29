/* Real file:// browser acceptance. The producer supplies facts; the browser owns shapes and layout. */
const {createRequire}=require('node:module');
const {pathToFileURL}=require('node:url');
const {join,dirname}=require('node:path');
const {writeFile,readFile}=require('node:fs/promises');
const assert=require('node:assert/strict');
const [renderer,entry,pythonId,javascriptId,standalone,encodedShapes]=process.argv.slice(2);
const shapeNames=encodedShapes?JSON.parse(encodedShapes):[];
const puppeteer=createRequire(renderer)('puppeteer');
(async()=>{
  const browser=await puppeteer.launch({headless:true,args:['--no-sandbox'],executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
  const errors=[],network=[];
  try {
    const page=await browser.newPage();await page.setViewport({width:1500,height:1000});
    page.on('pageerror',e=>errors.push(e.message));
    await page.setRequestInterception(true);page.on('request',r=>{if(/^https?:/.test(r.url())){network.push(r.url());r.abort();}else r.continue();});
    if(pythonId==='--empty') {
      const failed=[];page.on('requestfailed',r=>failed.push(r.url()));
      await page.goto(pathToFileURL(entry).href);
      await page.waitForFunction(()=>document.getElementById('count').textContent==='0 / 0');
      assert.equal(await page.$eval('#notice',e=>e.textContent),'');
      assert.match(await page.$eval('#empty',e=>e.textContent),/尚无预览记录/);
      assert.equal(await page.$$eval('.record, [data-call-path]',es=>es.length),0);
      assert.deepEqual(errors,[]);assert.deepEqual(network,[]);assert.deepEqual(failed,[]);
      console.log(JSON.stringify({records:0,page_errors:errors,network_requests:network,failed_resources:failed}));return;
    }
    if(pythonId==='--resources') {
      await page.goto(pathToFileURL(entry).href);
      await page.waitForSelector('[data-call-path]');
      for(const [index,id] of [[2,'base_lib:layout.helper'],[3,'plugin_declaration:layout.resources']]) {
        await page.click(`#tabs button:nth-child(${index})`);
        await page.waitForFunction(id=>[...document.querySelectorAll('[data-resource-id]')].some(e=>e.dataset.resourceId===id),{},id);
        assert.deepEqual(await page.$$eval('[data-resource-id]',es=>es.map(e=>e.dataset.resourceId)),[id]);
        assert.equal(await page.$$eval('[data-edge-id]',es=>es.length),0);
        await page.click('[data-resource-id="'+id+'"]');
        assert.match(await page.$eval('#details',e=>e.textContent),/source|sources/);
        assert(await page.$eval('[data-resource-id="'+id+'"]',e=>e.querySelector('.node-card')!==null));
        if(index===2){
          assert.equal(await page.$eval('[data-resource-id="'+id+'"] .card-outline',e=>getComputedStyle(e).fill),'rgb(255, 230, 179)');
        }else{
          assert.equal(await page.$eval('[data-resource-id="'+id+'"] .card-outline',e=>getComputedStyle(e).fill),'rgb(217, 230, 255)');
        }
      }
      await page.click('#tabs button:nth-child(4)');
      await page.waitForFunction(()=>document.getElementById('empty').textContent.includes('关联'));
      assert.equal(await page.$$('.resource-card').then(e=>e.length),0);
      assert.equal(errors.length,0);assert.equal(network.length,0);
      console.log(JSON.stringify({resources:true,page_errors:errors,network_requests:network}));return;
    }
    await page.goto(pathToFileURL(entry).href+'#'+new URLSearchParams({snapshot:pythonId,view:'flow'}));
    const wait=async count=>page.waitForFunction(n=>document.querySelectorAll('[data-call-path]').length===n,{},count);
    await wait(4);
    const geometry=await page.evaluate(shapes=>{
      const svg=VFShapes.node('svg',{width:1200,height:1000});document.body.append(svg);
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
      const resource={kind:'node',definition_id:'fixture.external',display_name:'External resource',external:true};
      const resourceCard=VFShapes.measure(resource,{node_definitions:{'fixture.external':{external:true,contract:{requires:[{key:'input'}],provides:[]}}}});
      const rows=resourceCard.rows.map(r=>r.text);
      svg.remove();return {failures,rows};
    },shapeNames);
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
    await page.waitForFunction(n=>document.querySelectorAll('[data-call-path^="first/inner/shape_"]').length===n,{},shapeNames.length);
    // Expanded calls are groups, never a disconnected invocation card above their body.
    const groups=await page.evaluate(()=>['first','first/inner'].map(path=>{
      const g=document.querySelector(`[data-call-path="${path}"]`),header=g.querySelector(':scope > .group-header');
      const box=header.getBBox(),inner=g.querySelector(':scope > svg');
      return {card:!!g.querySelector(':scope > .node-card'),title:header.querySelector('.card-title').textContent,
        description:[...header.querySelectorAll('.card-description')].map(e=>e.textContent).join(''),
        clear:box.y+box.height<inner.transform.baseVal.consolidate().matrix.f,
        boundary:!!g.querySelector(':scope > .call-boundary')};
    }));
    assert.deepEqual(groups.map(g=>g.card),[false,false]);
    assert.deepEqual(groups.map(g=>g.title),['first','inner']);
    assert.deepEqual(groups.map(g=>g.description),['真实预览测试 first','真实预览测试 inner']);
    assert(groups.every(g=>g.clear&&g.boundary));
    const shapes=await page.$$eval('[data-call-path^="first/inner/shape_"]',es=>es.map(e=>{
      const card=e.querySelector('.node-card'),graphic=card.querySelector('.card-outline');
      return {path:e.dataset.callPath,fill:getComputedStyle(graphic).fill,shape:card.dataset.shape,bbox:card.getBBox().width};
    }));
    assert.match(await page.$eval('[data-call-path="first/inner/shape_circle"]',e=>e.textContent),/外部依赖/);
    assert.equal(shapes.length,shapeNames.length);assert(shapes.every(s=>s.fill==='rgb(214, 234, 255)'&&s.bbox>0));
    assert.deepEqual(shapes.map(s=>s.shape).sort(),shapeNames);
    assert.equal(await page.$eval('[data-call-path="first/inner/shape_circle"] .card-outline',e=>e.tagName),'ellipse');
    assert.equal(await page.$eval('[data-call-path="first/inner/shape_diamond"] .card-outline',e=>e.tagName),'polygon');
    assert.equal(await page.$eval('[data-call-path="first/inner/shape_cloud"] .card-outline',e=>e.tagName),'path');
    const endpoints=await page.$$eval('path[data-from^="first/inner/shape_"]',paths=>paths.flatMap(path=>{
      const length=path.getTotalLength();return [path.getPointAtLength(0),path.getPointAtLength(length)].map(p=>({x:p.x,y:p.y}));
    }));
    assert.equal(endpoints.length,(shapeNames.length-1)*2);assert(endpoints.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
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
    // Locating a tall expanded group centers the whole group; fit before dragging its header.
    await page.click('#fit');
    const header=await page.$('[data-call-path="first"] > .group-header');const headerBounds=await header.boundingBox();
    const beforeHeaderDrag=await page.$eval('#scene',e=>e.getAttribute('transform'));
    const hx=headerBounds.x+headerBounds.width/2,hy=headerBounds.y+headerBounds.height/2;
    await page.mouse.move(hx,hy);await page.mouse.down();
    await page.mouse.move(hx+50,hy+30,{steps:6});await page.mouse.up();
    assert.notEqual(await page.$eval('#scene',e=>e.getAttribute('transform')),beforeHeaderDrag);
    // Right-click title/container preserves its screen anchor through layout.
    const center=async()=>page.$eval('[data-call-path="first"]',e=>{const b=e.getBoundingClientRect();return [b.x+b.width/2,b.y+b.height/2];});
    const anchor=await center();
    await page.$eval('[data-call-path="first"] > .group-header .card-title',e=>e.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:700,clientY:300})));
    await page.click('#toggle');await wait(4);
    assert(await page.$('[data-call-path="first"] > .node-card'));
    assert(!await page.$('[data-call-path="first"] > .group-header'));
    const after=await center();assert(Math.abs(after[0]-anchor[0])<1&&Math.abs(after[1]-anchor[1])<1);
    await locate('second/inner/shape_diamond');
    assert.equal(await page.$$eval('[data-call-path^="first/"]',es=>es.length),0);
    await page.click('#collapse');await wait(4);
    // Original SVG is the actual saved SVG, and mode/view state is independent.
    await page.screenshot({path:join(dirname(entry),'browser-acceptance.png')});
    console.log(JSON.stringify({shapes:shapes.length,network_requests:network,page_errors:errors}));
    assert.equal(errors.length,0);assert.equal(network.length,0);
  }finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
