const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{test}=require('node:test');
const root=path.resolve(__dirname,'..'),{JSDOM}=require(path.join(root,'.site-manager/ui-tests/node_modules/jsdom'));
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(t,cached=false){
 const dom=new JSDOM('<!doctype html><html><body><label>Caption<input id="caption" value="My own caption"></label></body></html>',{url:'http://localhost',runScripts:'outside-only'});
 t.after(()=>dom.window.close());const w=dom.window,calls=[];
 const draft={title:'Suggested sunset',alt_text:'Orange sunset reflected in a lake',description:'A quiet evening by the lake.',basis:'Actual image content.',notes:''};
 w.pending=new Map();w.api=async(name,data)=>{calls.push({name,data});return name==='descriptions'?{items:cached?[{kind:'image',url:'https://example.org/lake.jpg',draft}]:[]}:draft;};
 require('node:vm').runInContext(fs.readFileSync(path.join(root,'scripts/site_manager/descriptions.js'),'utf8'),dom.getInternalVMContext());
 return {w,d:w.document,calls};
}
test('Generated captions remain editable drafts until explicitly used, and changed sources cannot use stale suggestions',async t=>{
 const {w,d,calls}=fixture(t);let url='https://example.org/lake.jpg',accepted;
 w.attachDescriptionSuggestion(d.querySelector('input'),()=>({kind:'image',url}),'title',value=>accepted=value);
 await tick();const panel=d.querySelector('.description-suggestion');panel.querySelector('button').click();await tick();
 assert.equal(d.querySelector('input').value,'My own caption');assert.equal(accepted,undefined);
 assert.equal(panel.querySelector('textarea').value,'Suggested sunset');
 panel.querySelector('textarea').value='My revised sunset caption';
 [...panel.querySelectorAll('button')].at(-1).click();
 assert.equal(d.querySelector('input').value,'My revised sunset caption');assert.equal(accepted,'My revised sunset caption');
 url='https://example.org/forest.jpg';panel.querySelector('textarea').value='Stale draft';[...panel.querySelectorAll('button')].at(-1).click();
 assert.equal(d.querySelector('input').value,'My revised sunset caption');assert.match(panel.textContent,/source changed/);
 assert.equal(calls.filter(call=>call.name==='describe-media').length,1);
});
test('Cached drafts can be reviewed without generating or overwriting authored text',async t=>{
 const {w,d,calls}=fixture(t,true);
 w.attachDescriptionSuggestion(d.querySelector('input'),()=>({kind:'image',url:'https://example.org/lake.jpg'}),'alt_text');await tick();
 assert.equal(d.querySelector('textarea').value,'Orange sunset reflected in a lake');assert.equal(d.querySelector('input').value,'My own caption');
 assert.equal(calls.length,1);assert.equal(calls[0].name,'descriptions');
});
