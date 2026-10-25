const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{test}=require('node:test');
const root=path.resolve(__dirname,'..'),{JSDOM}=require(path.join(root,'.site-manager/ui-tests/node_modules/jsdom'));
test('Menu keyboard behavior tracks state, isolates the page, wraps Tab and restores focus',async t=>{
 const dom=new JSDOM('<!doctype html><html lang="en"><body><a class="skip-link" href="#main">Skip</a><div id="wrapper"><header id="header"><a href="#menu">Menu</a></header><main id="main"><p lang="en">Example</p></main></div><div id="menu" inert><a href="/">Home</a><a href="#menu">Close</a></div></body></html>',{url:'https://example.org',runScripts:'outside-only'});
 t.after(()=>dom.window.close());const w=dom.window,d=w.document;
 w.eval(fs.readFileSync(path.join(root,'assets/js/accessibility.js'),'utf8'));
 const opener=d.querySelector('#header a'),menu=d.querySelector('#menu'),links=menu.querySelectorAll('a');
 opener.focus();opener.dispatchEvent(new w.KeyboardEvent('keydown',{key:' ',bubbles:true,cancelable:true}));await Promise.resolve();
 assert.equal(opener.getAttribute('aria-expanded'),'true');assert(!menu.hasAttribute('inert'));assert(d.querySelector('#wrapper').hasAttribute('inert'));assert.equal(d.activeElement,links[0]);
 links[0].dispatchEvent(new w.KeyboardEvent('keydown',{key:'Tab',shiftKey:true,bubbles:true,cancelable:true}));assert.equal(d.activeElement,links[1]);
 links[1].dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));await Promise.resolve();
 assert.equal(opener.getAttribute('aria-expanded'),'false');assert(menu.hasAttribute('inert'));assert(!d.querySelector('#wrapper').hasAttribute('inert'));assert.equal(d.activeElement,opener);
});
