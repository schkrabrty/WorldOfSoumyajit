// Automated structural checks; contrast and rendered layout require browser review.
// npm install --prefix .site-manager/ui-tests jsdom axe-core terser
const fs=require('node:fs'),path=require('node:path');
const modules=path.resolve(__dirname,'../.site-manager/ui-tests/node_modules');
const {JSDOM,VirtualConsole}=require(path.join(modules,'jsdom'));
const axe=fs.readFileSync(path.join(modules,'axe-core/axe.min.js'),'utf8');
const root=path.resolve(process.argv[2]||'.site-manager/gallery-update-build');
(async()=>{
 const findings={};let pages=0;
 for(const filename of fs.readdirSync(root).filter(name=>name.endsWith('.html'))){
  const html=fs.readFileSync(path.join(root,filename),'utf8');
  if(!html.includes('id="header"')||/name="robots"\s+content="[^"]*noindex/i.test(html))continue;
  const dom=new JSDOM(html,{url:'https://worldofsoumyajit.com/'+filename,runScripts:'outside-only',virtualConsole:new VirtualConsole()});
  dom.window.eval(axe);
  const result=await dom.window.axe.run(dom.window.document,{rules:{'color-contrast':{enabled:false}}});
  for(const issue of result.violations){
   const value=findings[issue.id]||={impact:issue.impact,description:issue.help,pages:[],example:issue.nodes[0].html};value.pages.push(filename);
  }
  pages++;dom.window.close();
 }
 const report={pages,limitations:'Static DOM audit; color contrast, layout, media quality, and assistive-technology behavior need separate review.',findings};
 fs.writeFileSync(path.resolve('.site-manager/accessibility-review.json'),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify(report,null,2));if(Object.keys(findings).length)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
