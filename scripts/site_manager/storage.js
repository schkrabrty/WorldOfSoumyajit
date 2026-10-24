"use strict";

function defaultS3Folder(kind="image"){
 const root=state.storage?.prefix||"My Website related Stuffs/";
 if(kind==="pdf")return root+"Resume/";
 const section=$("#page-form")?.elements.section.value;
 return root+(section==="photography"?"BlogImages/":section==="creativity"?"CreativityImages/":"WorkImages/");
}
function s3FolderFor(url,kind="image"){
 try{
  const value=new URL(url),bucket=state.storage?.bucket||"worldofsoumyajit";
  if(value.hostname.startsWith(bucket+".s3."))return decodeURIComponent(value.pathname.slice(1).replace(/\+/g,' ')).split("/").slice(0,-1).join("/")+"/";
 }catch{}
 return defaultS3Folder(kind);
}
function browseS3Field(input,kind="image"){
 s3Picker({kind,prefix:s3FolderFor(input.value,kind),onSelect:files=>{
  const file=files[0];
  input.value=input.id==='replacement-thumbnail'||input.name==='tile_image'?(file.pair?.small_url||file.url):input.id==='replacement-url'||input.name==='image'?(file.pair?.full_url||file.url):file.url;
  if(input.id==='replacement-url')$("#replacement-thumbnail").value=file.pair?.small_url||'';
  input.dispatchEvent(new Event("input",{bubbles:true}));
 }});
}
function attachS3Field(input,kind="image"){
 if(!input||input.nextElementSibling?.classList.contains("s3-field-button"))return;
 const button=document.createElement("button");button.type="button";button.className="quiet s3-field-button";button.textContent="Choose from S3";
 button.onclick=()=>browseS3Field(input,kind);input.after(button);
}

async function s3Picker({kind="image",multiple=false,prefix,onSelect}){
 let picker=$("#s3-picker");
 if(!picker){picker=document.createElement("dialog");picker.id="s3-picker";document.body.append(picker);}
 let chosen=new Map(),files=[],folder=prefix||defaultS3Folder(kind),root=state.storage?.prefix||"My Website related Stuffs/",next=null;
 picker.innerHTML=`<div class="dialog-heading"><h2>Choose ${kind==='image'?'pictures':kind==='pdf'?'PDF files':'files'} from S3</h2><button class="icon-button" id="s3-close" aria-label="Close S3 picker">×</button></div>
 <div class="s3-location"><button class="secondary" id="s3-home">Website folder</button><button class="secondary" id="s3-up">Up one folder</button><button class="quiet" id="s3-refresh">Refresh</button></div>
 <p class="hint" id="s3-path"></p><input id="s3-search" type="search" placeholder="Search the files in this folder" aria-label="Search S3 files">
 <p id="s3-error" class="form-error" role="alert"></p><div id="s3-folders"></div><div id="s3-files" class="s3-grid"></div>
 <button class="secondary" id="s3-more" hidden>Load more files</button><div class="dialog-actions"><button class="secondary" id="s3-connect">Connect AWS</button><button id="s3-choose" disabled>Choose files</button></div>`;
 if(!picker.open)picker.showModal();
 const error=message=>$("#s3-error").textContent=message;
 const update=()=>{$("#s3-choose").disabled=!chosen.size;$("#s3-choose").textContent=`Choose ${chosen.size||''} file${chosen.size===1?'':'s'}`;};
 const draw=()=>{
  const query=$("#s3-search").value.toLowerCase();
  $("#s3-files").innerHTML=files.filter(file=>file.name.toLowerCase().includes(query)).map(file=>`<button class="s3-file ${chosen.has(file.key)?'selected':''}" data-s3-key="${esc(file.key)}" title="${esc(file.name)}" aria-pressed="${chosen.has(file.key)}">${kind==='image'?`<img src="${esc(file.url)}" alt="" loading="lazy">`:'<span class="s3-file-icon">▤</span>'}<strong>${esc(file.name)}</strong><small>${(file.size/1024).toFixed(0)} KB${file.pair?' · small/full pair':''}</small></button>`).join("")||'<p class="empty">No matching files in this folder. Choose a subfolder or go up.</p>';
  picker.querySelectorAll("[data-s3-key]").forEach(button=>button.onclick=()=>{
   const file=files.find(file=>file.key===button.dataset.s3Key);
   if(chosen.has(file.key))chosen.delete(file.key);else{if(!multiple)chosen.clear();chosen.set(file.key,file);}
   draw();update();
  });
 };
 const load=async(newFolder,more=false)=>{
  $("#s3-choose").disabled=true;error("");$("#s3-path").textContent="Loading…";
  try{
   const result=await api("s3/files?"+new URLSearchParams({prefix:newFolder,kind,...(more&&next?{cursor:next}:{})}));
   folder=result.prefix;root=result.root;next=result.next;files=more?[...files,...result.files]:result.files;
   $("#s3-path").textContent=`${result.bucket} / ${folder}`;
   $("#s3-folders").innerHTML=result.folders.map(path=>`<button class="s3-folder secondary" data-s3-folder="${esc(path)}">▱ ${esc(path.slice(folder.length).replace(/\/$/,''))}</button>`).join("");
   picker.querySelectorAll("[data-s3-folder]").forEach(button=>button.onclick=()=>load(button.dataset.s3Folder));
   $("#s3-up").disabled=folder===root;$("#s3-more").hidden=!next;draw();update();
  }catch(problem){error(problem.message+"\nChoose Connect AWS if the session has expired.");$("#s3-path").textContent=folder;}
 };
 $("#s3-close").onclick=()=>picker.close();$("#s3-search").oninput=draw;$("#s3-home").onclick=()=>load(root);
 $("#s3-up").onclick=()=>load(folder.slice(0,-1).split("/").slice(0,-1).join("/")+"/");
 $("#s3-refresh").onclick=()=>load(folder);$("#s3-more").onclick=()=>load(folder,true);
 $("#s3-connect").onclick=async()=>{try{const result=await api("s3/connect",{});error(result.message);}catch(problem){error(problem.message);}};
 $("#s3-choose").onclick=async event=>{
  const button=event.currentTarget;button.disabled=true;error("Checking that these files can be opened by visitors…");
  try{
   const selected=[...chosen.values()],keys=new Set(selected.map(file=>file.key));
   for(const file of selected){if(file.pair)for(const url of [file.pair.full_url,file.pair.small_url])keys.add(decodeURIComponent(new URL(url).pathname.slice(1)));}
   await api("s3/resolve",{keys:[...keys]});picker.close();await onSelect(selected);
  }catch(problem){error(problem.message);}finally{button.disabled=false;}
 };
 await load(folder);
}

function renderStorage(){
 const settings=state.storage||{};
 main.innerHTML=heading("Your S3 files","Browse the bucket by folder and file type, then choose files for your pages.")+
 `<section class="card"><h2>Connection</h2><p class="hint">Sign in through AWS when prompted. Passwords and MFA stay in the AWS sign-in page.</p><form id="storage-settings"><div class="two-col"><label>Bucket${field('bucket',settings.bucket)}</label><label>AWS region${field('region',settings.region)}</label><label>Website folder${field('prefix',settings.prefix)}</label><label>AWS profile${field('profile',settings.profile)}</label></div><div class="inline-actions"><button>Save connection settings</button><button type="button" class="secondary" id="storage-connect">Connect AWS</button></div></form><p class="hint">${settings.available?'AWS CLI is ready on this computer.':'First run bash scripts/setup_aws.sh in this project to install AWS support.'}</p></section>
 <section class="card"><h2>Browse your files</h2><label>File type<select id="storage-kind">${options({image:'Pictures',pdf:'PDF documents',video:'Video files',audio:'Audio files',archive:'Archives and project packages',all:'All files'},'image')}</select></label><button id="storage-browse">Browse S3 folders</button><div id="storage-selection"></div><p class="hint">The library reads your S3 files. Removing a picture or deleting a page in the manager does not delete the original S3 objects.</p></section>`;
 $("#storage-settings").onsubmit=event=>{event.preventDefault();action(event.currentTarget.querySelector('button'),async()=>{const result=await api('s3/configure',Object.fromEntries(new FormData(event.currentTarget)));message(result.message);await refresh();});};
 if(!settings.available){const button=document.createElement('button');button.type='button';button.className='secondary';button.textContent='Install AWS support';button.onclick=()=>action(button,async()=>{button.textContent='Installing AWS support…';try{message((await api('s3/install',{})).message);await refresh();renderStorage();}finally{button.textContent='Install AWS support';}});$("#storage-connect").before(button);}
 $("#storage-connect").onclick=event=>action(event.currentTarget,async()=>message((await api('s3/connect',{})).message));
 $("#storage-browse").onclick=()=>s3Picker({kind:$("#storage-kind").value,multiple:true,prefix:state.storage.prefix,onSelect:files=>{$("#storage-selection").innerHTML='<div class="file-list">'+files.map(file=>`<a href="${esc(file.url)}" target="_blank" rel="noopener noreferrer">${esc(file.name)}</a><br><span>${esc(file.url)}</span>`).join('<br><br>')+'</div>';}});
}
