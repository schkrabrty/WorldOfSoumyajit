// Native drag handlers and settings flows, exercised without changing live content.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {test}=require('node:test');
const root=path.resolve(__dirname,'..'),directory=path.join(__dirname,'site_manager');
const {JSDOM}=require(path.join(root,'.site-manager/ui-tests/node_modules/jsdom'));
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const tile=index=>({page:`/tile-${index}.html`,title:`Tile ${index}`,image:`https://example.org/${index}.jpg`,caption:`Caption ${index}`,alt:`Alt ${index}`,artwork:{crop:'custom',award:index===0}});

function fixture(t,count=4){
 const dom=new JSDOM(fs.readFileSync(path.join(directory,'index.html'),'utf8'),{url:'http://localhost/__manager/',runScripts:'outside-only',pretendToBeVisual:true});
 t.after(()=>dom.window.close());const w=dom.window,d=w.document,calls=[];
 w.scrollTo=()=>{};w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
 const state={groups:{first:'First section',second:'Second section',empty:'Empty section'},tiles:{first:Array.from({length:count},(_,i)=>tile(i)),second:[tile(100)],empty:[]},group_categories:{first:'works',second:'works',empty:'works'},section_pages:[],people:{},history:[],storage:{bucket:'test-bucket',region:'us-east-1',prefix:'Website/',profile:'test-profile',available:true,thumbnails_ready:true},settings:{profile_image:'https://example.org/portrait.jpg',profile_image_alt:'Portrait',email:'author@example.org',cv:{two_page:'https://example.org/short.pdf',full:'https://example.org/full.pdf'},social:{}},build:{ready:true}};
 w.fetch=async(url,request={})=>{
  const name=String(url).replace('/api/',''),data=request.body?JSON.parse(request.body):undefined;calls.push({name,data});
  let value={message:'Saved'};
  if(name==='state')value=state;
  if(name==='descriptions')value={items:[]};
  if(name==='s3/configure')Object.assign(state.storage,data);
  if(name==='reorder')state.tiles[data.group]=data.order.map(url=>state.tiles[data.group].find(tile=>tile.page===url));
  return {ok:true,json:async()=>structuredClone(value)};
 };
 const app=fs.readFileSync(path.join(directory,'app.js'),'utf8');
 vm.runInContext(app.slice(0,app.indexOf('(async()=>{try{await refresh();render();')),dom.getInternalVMContext());
 for(const name of ['media.js','descriptions.js','storage.js'])vm.runInContext(fs.readFileSync(path.join(directory,name),'utf8'),dom.getInternalVMContext());
 w.eval('state='+JSON.stringify(state));
 return {w,d,state,calls};
}
function dragEvent(w,type,target,y=0,x=100){
 const event=new w.Event(type,{bubbles:true,cancelable:true});
 Object.defineProperties(event,{clientX:{value:x},clientY:{value:y},dataTransfer:{value:{setData(){}}}});target.dispatchEvent(event);return event;
}
function drag(w,from,to,after=true){
 dragEvent(w,'dragstart',from);const over=dragEvent(w,'dragover',to,after?1:-1);
 assert(over.defaultPrevented);assert(to.classList.contains(after?'drop-after':'drop-before'));
 assert(dragEvent(w,'drop',to,after?1:-1).defaultPrevented);
}

test('Tiles drag both ways, keep complete records, retain arrow controls, and save only on request',async t=>{
 const {w,d,state,calls}=fixture(t);w.activate('arrange');
 const rows=()=>[...d.querySelectorAll('#sort-list [data-order-index]')];
 assert.equal(rows().length,4);assert(rows().every(row=>row.draggable));
 drag(w,rows()[0],rows()[3]);
 assert.deepEqual(JSON.parse(w.eval('JSON.stringify(arranged)')),[tile(1),tile(2),tile(3),tile(0)]);
 assert.equal(calls.filter(call=>call.name==='reorder').length,0);
 drag(w,rows()[3],rows()[0],false);
 rows()[0].querySelector('[data-order-direction="1"]').click();
 assert.deepEqual(JSON.parse(w.eval('JSON.stringify(arranged)')),[tile(1),tile(0),tile(2),tile(3)]);
 assert(d.activeElement.closest('[data-order-index="1"]'),'Keep keyboard focus with the moved tile');
 assert.match(d.querySelector('#tile-order-status').textContent,/Save tile order/);
 await d.querySelector('#save-order').onclick({currentTarget:d.querySelector('#save-order')});
 assert.deepEqual(calls.find(call=>call.name==='reorder').data,{group:'first',order:['/tile-1.html','/tile-0.html','/tile-2.html','/tile-3.html']});
 assert.deepEqual(state.tiles.first,[tile(1),tile(0),tile(2),tile(3)]);assert.deepEqual(state.tiles.second,[tile(100)]);
 assert.equal(d.querySelector('#tile-order-status').textContent,'Tile order saved.');
 d.querySelector('#arrange-group').value='second';d.querySelector('#arrange-group').dispatchEvent(new w.Event('change'));
 assert.equal(rows().length,1);assert(rows()[0].querySelector('[data-order-direction="1"]').disabled);
 d.querySelector('#arrange-group').value='empty';d.querySelector('#arrange-group').dispatchEvent(new w.Event('change'));
 assert.equal(rows().length,0);assert.match(d.querySelector('#sort-list').textContent,/no tiles/i);
});

test('Tile saving freezes drag and section changes and preserves the order after an API failure',async t=>{
 const {w,d}=fixture(t);w.activate('arrange');let reject;
 w.fetch=()=>new Promise((resolve,no)=>reject=no);
 const save=d.querySelector('#save-order'),list=d.querySelector('#sort-list');
 const pending=save.onclick({currentTarget:save});
 assert(save.disabled);assert(d.querySelector('#arrange-group').disabled);assert([...list.querySelectorAll('button')].every(button=>button.disabled));
 const event=dragEvent(w,'dragstart',list.firstElementChild);assert(event.defaultPrevented);
 reject(new Error('Connection failed'));await pending;
 assert(!save.disabled);assert(!d.querySelector('#arrange-group').disabled);
 assert.deepEqual(JSON.parse(w.eval('JSON.stringify(arranged)')),[tile(0),tile(1),tile(2),tile(3)]);
 assert.match(d.querySelector('#notice').textContent,/Connection failed/);
 assert(list.querySelector('[data-order-direction="-1"]').disabled,'Restore the boundary button’s original state');
 assert(!list.querySelector('[data-order-direction="1"]').disabled);
});

test('Tiles scroll while the pointer stays at an edge and stop on exit, section changes, and navigation',t=>{
 const {w,d}=fixture(t,16);w.activate('arrange');
 const frames=new Map();let next=0;w.requestAnimationFrame=callback=>{frames.set(++next,callback);return next;};w.cancelAnimationFrame=id=>frames.delete(id);
 const step=time=>{const callbacks=[...frames.values()];frames.clear();callbacks.forEach(callback=>callback(time));};
 const list=d.querySelector('#sort-list'),rows=[...list.querySelectorAll('[data-order-index]')];
 list.getBoundingClientRect=()=>({top:100,bottom:400,left:0,right:500,height:300});
 Object.defineProperties(list,{scrollHeight:{value:1600},clientHeight:{value:300}});list.scrollTop=200;
 rows.forEach((row,index)=>row.getBoundingClientRect=()=>({top:100+index*100-list.scrollTop,bottom:200+index*100-list.scrollTop,height:100}));
 d.elementFromPoint=(x,y)=>rows[Math.floor((y-100+list.scrollTop)/100)];
 dragEvent(w,'dragstart',rows[2],110);dragEvent(w,'dragover',rows[4],399);step(0);const first=list.scrollTop;step(16);step(32);
 assert(first>200&&list.scrollTop>first,'Continue scrolling down without more mouse movement');
 dragEvent(w,'dragover',rows[3],250);step(48);const middle=list.scrollTop;step(64);assert.equal(list.scrollTop,middle);
 dragEvent(w,'dragover',rows[2],101);step(80);step(96);assert(list.scrollTop<middle,'Continue scrolling upward at the top edge');
 dragEvent(w,'dragleave',list,90);assert.equal(frames.size,0);
 dragEvent(w,'dragover',rows[4],399);step(112);assert(frames.size>0);
 d.querySelector('#arrange-group').value='second';d.querySelector('#arrange-group').dispatchEvent(new w.Event('change'));
 assert.equal(frames.size,0);assert.equal(list.scrollTop,0);
 d.querySelector('#arrange-group').value='first';d.querySelector('#arrange-group').dispatchEvent(new w.Event('change'));
 const fresh=list.querySelectorAll('[data-order-index]');dragEvent(w,'dragstart',fresh[2],110);dragEvent(w,'dragover',fresh[4],399);step(128);
 w.renderPeople();const previous=list.scrollTop;step(144);assert.equal(list.scrollTop,previous);assert.equal(frames.size,0);
});

test('The sidebar stays simple and S3 configuration preserves unsaved shared profile edits',async t=>{
 const {w,d,calls}=fixture(t);
 assert.equal(d.querySelector('[data-view="storage"]'),null);assert.equal(d.querySelector('[data-view="descriptions"]'),null);
 assert.equal(typeof w.attachDescriptionSuggestion,'function');assert.equal(typeof w.s3Picker,'function');
 w.activate('settings');await tick();
 const profile=d.querySelector('#settings-form');profile.elements.email.value='unsaved@example.org';
 assert.equal(d.querySelector('#storage-settings').closest('#settings-form'),null,'Keep independent forms separate');
 const form=d.querySelector('#storage-settings');form.elements.bucket.value='new-bucket';
 form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await tick();await tick();
 assert.deepEqual(calls.find(call=>call.name==='s3/configure').data,{bucket:'new-bucket',region:'us-east-1',prefix:'Website/',profile:'test-profile'});
 assert.equal(d.querySelector('#settings-form').elements.email.value,'unsaved@example.org');
 assert.equal(d.querySelector('#storage-settings').elements.bucket.value,'new-bucket');
 assert(!calls.some(call=>call.name==='settings'),'Connection changes do not save unfinished profile edits');
 assert(d.querySelector('#storage-connect'));assert(d.querySelector('#settings-form .s3-field-button'));
});
