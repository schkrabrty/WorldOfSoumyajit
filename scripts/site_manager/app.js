"use strict";
const token = document.querySelector('meta[name="manager-token"]').content;
const main = document.querySelector("main");
const dialog = document.querySelector("#dialog");
let state, view = "pages", current = null, bodyDirty = false, contentDirty = false, htmlMode = false, savedRange = null;
let uploads = [], videos = [], pending = new Map(), selected = new Set(), arranged = [], reviewId = null;
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const $ = selector => document.querySelector(selector);
const field = (name, value="") => `<input name="${name}" value="${esc(value)}">`;
const options = (values, value) => Object.entries(values).map(([key,label]) => `<option value="${esc(key)}" ${key===value?'selected':''}>${esc(label)}</option>`).join("");
const message = (text, error=false) => { const n=$("#notice");n.textContent=text;n.hidden=false;n.className=error?"error":"";if(!error)setTimeout(()=>n.hidden=true,6500); };
async function api(name, data) {
  const response=await fetch("/api/"+name,{method:data===undefined?"GET":"POST",headers:{"X-Manager-Token":token,...(data===undefined?{}:{"Content-Type":"application/json"})},...(data===undefined?{}:{body:JSON.stringify(data)})});
  const result=await response.json();if(!response.ok)throw new Error(result.error||"The operation could not be completed.");return result;
}
async function refresh(){state=await api("state");renderStatus(state.build);}
async function action(button, work){button.disabled=true;try{await work();}catch(error){message(error.message,true);}finally{button.disabled=false;}}
function heading(title,description,actions=""){return `<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${actions}</div>`;}
function renderStatus(status){$("#build-status").textContent=status.running?"Building your preview…":status.error?"Preview needs attention":status.ready?"Preview is up to date":"Preview has not been built";$("#build-status").title=status.error||"";}
function showDialog(title,html,callback){$("#dialog-title").textContent=title;$("#dialog-content").innerHTML=html+`<p class="form-error" role="alert"></p>`;if(!dialog.open)dialog.showModal();if(callback)callback();}
function dialogError(error){$("#dialog-content .form-error").textContent=error.message||error;}
async function photoDialogAction(work){
 const controls=[...$('#dialog-content').querySelectorAll('button,input,textarea'),$('#dialog-close')].map(control=>[control,control.disabled]);
 const cancel=dialog.oncancel;dialog.oncancel=event=>event.preventDefault();
 controls.forEach(([control])=>control.disabled=true);
 try{await work();}catch(error){dialogError(error);}finally{dialog.oncancel=cancel;controls.forEach(([control,disabled])=>control.disabled=disabled);}
}
$("#dialog-close").onclick=()=>dialog.close();
function activate(name){view=name;current=null;document.querySelectorAll("[data-view]").forEach(b=>b.classList.toggle("active",b.dataset.view===name));render();window.scrollTo(0,0);}
document.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>{if(current&&bodyDirty&&!confirm("Leave this page without saving your edits?"))return;activate(b.dataset.view);});
$("#rebuild").onclick=e=>action(e.currentTarget,async()=>{await api("build",{});message("Building a fresh preview.");});

function render(){if(view==="pages")renderPages();if(view==="arrange")renderArrange();if(view==="sections")renderSections();if(view==="people")renderPeople();if(view==="settings")renderSettings();if(view==="history")renderHistory();if(view==="publish")renderPublish();}
function renderPages(){
 main.innerHTML=heading("Your pages","Add something new, or choose a page to update.",'<button id="new-page">+ New page</button>')+
 `<div class="filters"><input id="search" type="search" placeholder="Find a page by title or address" aria-label="Search pages"><select id="filter" aria-label="Filter pages"><option value="">All pages</option>${options({main:"Main pages",...pageCategories()},"")}</select></div><div id="bulk" class="bulk" hidden><span></span><button id="delete-selected" class="danger">Delete selected pages</button></div><div id="page-list" class="page-list"></div>`;
 $("#new-page").onclick=()=>newPageDialog();$("#search").oninput=pageRows;$("#filter").onchange=pageRows;$("#delete-selected").onclick=deleteDialog;pageRows();
}
function pageRows(){
 const search=$("#search").value.toLowerCase(),section=$("#filter").value;
 const pages=state.pages.filter(p=>(!section||(section==="main"?p.main_page:p.section===section))&&`${p.title} ${p.url}`.toLowerCase().includes(search));
 $("#page-list").innerHTML=pages.map(p=>`<div class="page-row">${(p.main_page?p.id==='index.html':p.protected)?'<span title="The homepage is required"></span>':`<input type="checkbox" data-select="${esc(p.id)}" ${selected.has(p.id)?'checked':''} aria-label="Select ${esc(p.title)}">`}<div><h3><button data-edit="${esc(p.id)}">${esc(p.title)}</button></h3><small>${esc(p.url)}</small></div><span class="badge">${esc(p.protected?"Main page":state.groups[p.groups[0]]||"Detail page")}</span><button class="quiet" data-edit="${esc(p.id)}">Edit</button></div>`).join("")||'<p class="empty">No pages match this search.</p>';
 document.querySelectorAll("[data-edit]").forEach(b=>b.onclick=()=>editPage(b.dataset.edit));
 document.querySelectorAll("[data-select]").forEach(b=>b.onchange=()=>{b.checked?selected.add(b.dataset.select):selected.delete(b.dataset.select);bulkStatus();});bulkStatus();
}
function bulkStatus(){const n=$("#bulk");if(!n)return;n.hidden=!selected.size;n.querySelector("span").textContent=`${selected.size} page${selected.size===1?'':'s'} selected`;}
function pageCategories(){return Object.fromEntries(state.section_pages.map(page=>[page.category,page.title]));}
const types={research:"Research or project",tutorial:"Tutorial",showcase:"Student showcase",photography:"Photo gallery or trip",creativity:"Story, artwork, or celebration",general:"Other page"};
function defaultTileGroup(category='works',type='research'){
 const preferred=type==='photography'?'photography':type==='creativity'?'creativity':['tutorial','showcase'].includes(type)?'teaching-tutorials':'research-projects';
 if(state.groups[preferred]&&state.group_categories[preferred]===category)return preferred;
 return Object.keys(state.groups).find(group=>state.group_categories[group]===category)||'';
}
function typeFor(page){if(page.meta.content_type)return page.meta.content_type;if(page.meta.section==="photography")return "photography";if(page.meta.section==="creativity")return "creativity";if(page.tile?.group==="teaching-tutorials")return page.id.includes("showcase")?"showcase":"tutorial";return "research";}
async function editPage(id){
 try{
  const page=id?await api("page?id="+encodeURIComponent(id)):null;current=page||{id:null,body:"",meta:{},heading:"",protected:false};bodyDirty=false;contentDirty=false;htmlMode=false;uploads=[];videos=[];pending=new Map();
  const meta=current.meta,tile=current.tile||{},type=page?typeFor(page):"research";
  main.innerHTML=`<button class="quiet back" id="back-pages">← All pages</button>`+heading(page?"Edit page":"Create a page",page?"Update the details, writing, images, and links below.":"Choose a page type, then add your writing and media.")+
  `<form id="page-form"><div class="grid"><div><section class="card"><h2>Page details</h2><div class="two-col"><label>Page type<select name="type">${options(types,type)}</select></label><label>Page category<select name="section">${options({...pageCategories(),...(current.protected?{main:"Main pages"}:{})},meta.section||(current.protected?"main":"works"))}</select></label></div><label>Page title${field("title",meta.title)}</label><label>Heading on the page${field("heading",current.heading)}</label><label>Page address<div class="hint">Use a short name with English letters, numbers, and hyphens.</div><input name="slug" value="${esc(page?page.id.replace(/\.html$/,""):"")}" ${current.protected?"disabled":""} placeholder="my-new-page"></label><label>Search description<textarea name="description" rows="3" placeholder="A short description of this page">${esc(meta.description)}</textarea></label><label>Sharing image URL${field("image",meta.image)}<span class="hint">Optional. The tile image can use the same URL.</span></label><p class="section-note" id="type-help"></p></section>
  <section class="card"><div class="inline-actions" style="justify-content:space-between;margin-bottom:15px"><h2 style="margin:0">Writing &amp; media</h2><button type="button" class="quiet" id="html-toggle">Edit HTML</button></div>${state.section_pages.some(page=>page.id===current.id)?'<p class="hint">Use Sections to manage this page’s tile groups and each linked page’s Page tile settings to change its picture.</p>':''}<div class="toolbar"><select id="heading-level" class="heading-level" aria-label="Text style" title="The main heading is set in Heading on the page."><option value="p">Paragraph</option><option value="h1" disabled>Main heading (H1)</option><option value="h2">Section heading (H2)</option><option value="h3">Subsection heading (H3)</option><option value="h4">Subsubsection heading (H4)</option></select><button type="button" data-format="bold"><b>Bold</b></button><button type="button" data-format="italic"><i>Italic</i></button><button type="button" data-format="insertUnorderedList">List</button><button type="button" data-tool="link">Add link</button><button type="button" data-tool="person">Add person</button><button type="button" data-tool="photos">Add photos</button><button type="button" data-tool="video">Add video</button><button type="button" data-tool="document">Add PDF</button><button type="button" data-tool="media">Manage media</button></div><div id="editor" class="editor" contenteditable="true" role="textbox" aria-label="Page content" aria-multiline="true" data-placeholder="Write or paste your page content here…"></div><textarea id="html-editor" class="html-editor" hidden aria-label="Page HTML"></textarea></section>
  <details class="card"><summary>Advanced: existing page metadata</summary><p class="hint">Existing research and video information is preserved. You can edit the JSON below when needed.</p><textarea id="metadata" class="html-editor">${esc(JSON.stringify(meta,null,2))}</textarea></details></div>
  <div><section class="card"><h2>Page tile</h2><label class="check-label"><input type="checkbox" name="tile_enabled" ${(current.tile||!page)&&Object.keys(state.groups).length?'checked':''}>Show a tile linking to this page</label>${!Object.keys(state.groups).length?'<p class="hint">Add a section in Sections before enabling a page tile.</p>':''}<div id="tile-fields"><label>Where should it appear?<select name="tile_group"><option value="">Choose a section</option>${options(state.groups,tile.group||defaultTileGroup(meta.section||"works",type))}</select></label><label>Tile title${field("tile_title",tile.title||meta.title)}</label><label>Short caption${field("tile_caption",tile.caption)}</label><label>Tile image URL${field("tile_image",tile.image||meta.image)}</label><label>Image description${field("tile_alt",tile.alt||meta.title)}</label><label>Position in section<input type="number" name="tile_position" min="1" value="${(tile.position??0)+1}"></label><p class="hint">1 places the tile first. Existing image crops and custom decorations are preserved when you edit a tile.</p></div></section><section class="card"><h2>What happens when you save?</h2><p class="hint">The page, its tile, search description, and preview are updated together. Changing its address also creates a redirect and updates links.</p><p class="hint">You can undo changes from Recent changes.</p></section></div></div><div class="save-bar"><small>Saving does not publish the website.</small><button type="button" class="secondary" id="cancel-edit">Cancel</button><button type="submit" id="save-page">Save &amp; build preview</button></div></form>`;
  const form=$("#page-form"),editor=$("#editor");editor.innerHTML=visual(current.body);bindMediaControls(editor);for(const name of ["image","tile_image"])attachS3Field(form.elements[name]);
  attachDescriptionSuggestion(form.elements.tile_alt,()=>({kind:"image",url:form.elements.tile_image.value,context:form.elements.title.value}));
  const pageSuggestion=()=>({kind:"page",url:current.id||"new-page",context:form.elements.title.value+"\n"+form.elements.description.value+"\n"+editor.textContent});
  attachDescriptionSuggestion(form.elements.title,pageSuggestion,"title");attachDescriptionSuggestion(form.elements.heading,pageSuggestion,"title");attachDescriptionSuggestion(form.elements.description,pageSuggestion,"description");
  attachDescriptionSuggestion(form.elements.tile_title,()=>({kind:"image",url:form.elements.tile_image.value,context:form.elements.title.value}),"title");attachDescriptionSuggestion(form.elements.tile_caption,pageSuggestion,"description");
  const leave=()=>{if(!bodyDirty||confirm("Leave this page without saving your edits?"))activate("pages");};$("#back-pages").onclick=leave;$("#cancel-edit").onclick=leave;
  form.oninput=()=>bodyDirty=true;editor.oninput=()=>{bodyDirty=true;contentDirty=true;};$("#html-editor").oninput=()=>{bodyDirty=true;contentDirty=true;};
  form.elements.title.required=true;form.elements.description.required=true;form.elements.slug.required=!current.protected;
  form.elements.title.oninput=()=>{if(!page){form.elements.slug.value=slug(form.elements.title.value);form.elements.heading.value=form.elements.title.value;form.elements.tile_title.value=form.elements.title.value;form.elements.tile_alt.value=form.elements.title.value;}};
  form.elements.type.onchange=()=>{const t=form.elements.type.value;if(!page){const preferred=t==="photography"?"photography":t==="creativity"?"creativity":"works",categories=pageCategories();form.elements.section.value=preferred in categories?preferred:Object.keys(categories)[0];form.elements.tile_group.value=defaultTileGroup(form.elements.section.value,t);}typeHelp();};
  if(!Object.keys(state.groups).length){form.elements.tile_enabled.checked=false;form.elements.tile_enabled.disabled=true;}
  form.elements.tile_group.onchange=()=>{const category=state.group_categories[form.elements.tile_group.value];if(category&&!current.protected)form.elements.section.value=category;};
  form.elements.section.onchange=()=>{if(!page)form.elements.tile_group.value=defaultTileGroup(form.elements.section.value,form.elements.type.value);};
  form.elements.tile_enabled.onchange=()=>{$("#tile-fields").hidden=!form.elements.tile_enabled.checked;form.elements.tile_group.required=form.elements.tile_enabled.checked;};form.elements.tile_enabled.onchange();typeHelp();
  $("#html-toggle").onclick=()=>{if(htmlMode){editor.innerHTML=visual($("#html-editor").value);}else{$("#html-editor").value=serialize();}htmlMode=!htmlMode;editor.hidden=htmlMode;$("#html-editor").hidden=!htmlMode;$("#html-toggle").textContent=htmlMode?"Visual editor":"Edit HTML";};
  document.querySelectorAll("[data-format]").forEach(b=>{b.onmousedown=e=>e.preventDefault();b.onclick=()=>{editor.focus();document.execCommand(b.dataset.format);bodyDirty=true;contentDirty=true;};});
  document.querySelectorAll("[data-tool]").forEach(b=>b.onclick=()=>{rememberSelection();({link:linkDialog,person:personInsertDialog,photos:photosDialog,video:videoDialog,document:documentDialog,media:mediaDialog})[b.dataset.tool]();});
  form.onsubmit=e=>{e.preventDefault();action($("#save-page"),async()=>{
   const values=Object.fromEntries(new FormData(form));let metadata;
   try{metadata=JSON.parse($("#metadata").value);}catch{throw new Error("The advanced metadata must be valid JSON.");}
   const tileURL=(values.tile_image||values.image||'').trim();
   if(form.elements.tile_enabled.checked&&tileURL&&tileURL!==current.tile?.image){
    const row={url:tileURL,thumbnail:''};await prepareS3PhotoRows([row]);
    values.tile_image=row.thumbnail||row.url;form.elements.tile_image.value=values.tile_image;
   }
   const result=await api("save",{id:current.id,revision:current.revision,title:values.title,heading:values.heading,slug:values.slug||current.id?.replace(/\.html$/,""),description:values.description,section:values.section,type:values.type,image:values.image,body:contentDirty?(htmlMode?$("#html-editor").value:serialize()):current.body,metadata,uploads,videos,tile:{enabled:!!form.elements.tile_enabled.checked,group:values.tile_group,title:values.tile_title,caption:values.tile_caption,image:values.tile_image||values.image,alt:values.tile_alt,position:Number(values.tile_position)-1}});
   message(result.message);await refresh();await editPage(result.id);
  });};
  window.scrollTo(0,0);
 }catch(error){message(error.message,true);}
}
function slug(text){return text.normalize("NFKD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"")||"new-page";}
function typeHelp(){const type=$("#page-form").elements.type.value;$("#type-help").textContent=({research:"Add authors with Add person, then include your study summary, publication links, and any presentation videos.",tutorial:"Add the tutorial introduction, project or setup links, and optional videos.",showcase:"Describe the course and your students’ work, then add photos, project links, or videos.",photography:"Add your trip description, then upload several photos or paste their URLs together.",creativity:"Write in Bengali or English, and add your artwork or celebration photos.",general:"Use the editor for your writing, links, images, and videos."})[type];}
function visualTemplateLabels(html){
 const template=document.createElement('template');template.innerHTML=html;
 const walker=document.createTreeWalker(template.content,NodeFilter.SHOW_TEXT),nodes=[];
 while(walker.nextNode())nodes.push(walker.currentNode);
 const pattern=/\{\{\s*site\.cv_labels\.(two_page|full)\b[\s\S]*?\}\}/g;
 for(const node of nodes){
  const matches=[...node.textContent.matchAll(pattern)];if(!matches.length)continue;
  const fragment=document.createDocumentFragment();let cursor=0;
  for(const match of matches){
   fragment.append(document.createTextNode(node.textContent.slice(cursor,match.index)));
   const label=document.createElement('span');label.contentEditable='false';label.className='template-tag';label.dataset.liquid=match[0];label.textContent=state.settings?.cv_labels?.[match[1]]||(match[1]==='two_page'?'Two Page CV':'Full CV');fragment.append(label);cursor=match.index+match[0].length;
  }
  fragment.append(document.createTextNode(node.textContent.slice(cursor)));node.replaceWith(fragment);
 }
 return template.innerHTML;
}
function visual(text){return visualTemplateLabels(text.replace(/\{%[\s\S]*?%\}/g,tag=>{const id=tag.match(/id="([^"]+)"/),name=tag.match(/name="([^"]+)"/);const label=tag.includes("person.html")?(name?.[1]||state.people[id?.[1]]?.name||"Person"):tag.includes("tiles.html")?"Tiles are managed in Arrange tiles":"Shared page content";return `<span contenteditable="false" class="${tag.includes("person.html")?'person-tag':'template-tag'}" data-liquid="${esc(tag)}">${esc(label)}</span>`;}).replace(/src="([^"]+)"/g,(match,url)=>pending.has(url)?`src="/__uploads/${pending.get(url)}" data-source-url="${esc(url)}"`:match));}
function cleanGalleryMarkup(root){
 root.querySelectorAll('a[data-lightbox]').forEach(link=>{
  if(!link.querySelector('img,picture,video,iframe,svg')&&!link.textContent.replace(/[\s\u200b]/g,''))link.remove();
 });
 root.querySelectorAll('.gallery').forEach(gallery=>{
  if(!gallery.querySelector('img,iframe,video,svg')&&!gallery.textContent.replace(/[\s\u200b]/g,''))gallery.remove();
 });
}
function serialize(){const clone=$("#editor").cloneNode(true);cleanGalleryMarkup(clone);clone.querySelectorAll("[data-liquid]").forEach(el=>el.replaceWith(document.createTextNode(el.dataset.liquid)));clone.querySelectorAll("[data-source-url]").forEach(el=>{el.setAttribute("src",el.dataset.sourceUrl);el.removeAttribute("data-source-url");});return clone.innerHTML;}
function rememberSelection(){const selection=getSelection();if(selection.rangeCount&&$("#editor").contains(selection.anchorNode))savedRange=selection.getRangeAt(0).cloneRange();else savedRange=null;}
function insert(html){
 dialog.close();
 if(htmlMode){$("#html-editor").value+="\n"+html;}
 else{
  const editor=$("#editor");editor.focus();
  const selection=getSelection();let range;
  if(savedRange&&editor.contains(savedRange.commonAncestorContainer)){range=savedRange.cloneRange();}
  else{range=document.createRange();range.selectNodeContents(editor);range.collapse(false);}
  if(/^\s*<(section|p|div)\b/i.test(html)){
   const node=range.startContainer.nodeType===Node.ELEMENT_NODE?range.startContainer:range.startContainer.parentElement;
   const block=node.closest?.('.gallery')||node.closest?.("a,picture,figure,p,h1,h2,h3,h4,h5,h6,li");
   if(block&&editor.contains(block)){range.setStartAfter(block);range.collapse(true);}
  }
  range.deleteContents();const fragment=range.createContextualFragment(visual(html)),last=fragment.lastChild;
  range.insertNode(fragment);
  if(last)range.setStartAfter(last);range.collapse(true);
  selection.removeAllRanges();selection.addRange(range);savedRange=range.cloneRange();
 }
 bodyDirty=true;contentDirty=true;
}
function linkDialog(){showDialog("Add a link",`<form id="tool-form"><label>Link text${field("text",getSelection()?.toString())}</label><label>Destination URL<input name="url" type="url" required placeholder="https://…"></label><div class="dialog-actions"><button>Add link</button></div></form>`,()=>{$("#tool-form").onsubmit=e=>{e.preventDefault();const f=e.currentTarget.elements;insert(`<a href="${esc(f.url.value)}">${esc(f.text.value||f.url.value)}</a>`);};});}
function personInsertDialog(){showDialog("Add a person",`<form id="tool-form"><label>Person<select name="person">${options(Object.fromEntries(Object.entries(state.people).map(([id,p])=>[id,p.name])),"")}</select></label><label>Name to display${field("name")}</label><p class="hint">Add a new person first under People &amp; profile links.</p><div class="dialog-actions"><button>Add linked name</button></div></form>`,()=>{const f=$("#tool-form");f.elements.name.value=state.people[f.elements.person.value].name;f.elements.person.onchange=()=>f.elements.name.value=state.people[f.elements.person.value].name;f.onsubmit=e=>{e.preventDefault();const name=f.elements.name.value;if(!name.trim()||name.includes('"')||name.includes("%}"))return dialogError("Choose a name without quote characters.");insert(`{% include person.html id="${f.elements.person.value}" name="${name}" %}`);};});}
async function upload(file){if(file.size>25*1024*1024)throw new Error("Choose a file smaller than 25 MB.");const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(",")[1]);reader.onerror=reject;reader.readAsDataURL(file);});const item=await api("upload",{name:file.name,content});uploads.push(item.id);pending.set(item.url,item.id);return item;}
function photosDialog(){let rows=[];showDialog("Add photos",`<p class="muted">Upload several photos together, or paste existing image URLs. Smaller tile images are prepared automatically for S3 pictures.</p><button class="secondary" id="photos-s3">Choose photos from S3</button><label style="margin-top:16px">Choose photos<input type="file" id="photo-files" accept="image/*" multiple></label><label>Existing image URLs<textarea id="photo-urls" rows="3" placeholder="Full-size URL | small-image URL | caption (one photo per line)"></textarea></label><button class="secondary" id="read-urls">Add URLs to list</button><p class="hint">Drag photos or use the arrows to choose their gallery order before inserting.</p><div id="photo-rows" aria-label="New photo order"></div><p id="photo-progress" role="status" aria-live="polite"></p><div class="dialog-actions"><button id="insert-photos">Insert gallery</button></div>`,()=>{
 const draw=()=>{
  const list=$('#photo-rows'),scrollTop=list.scrollTop;
  list.innerHTML=rows.map((r,i)=>{
   const title=r.caption||`Photo ${i+1}`,source=r.thumbnail||r.url,preview=pending.has(source)?'/__uploads/'+pending.get(source):source;
   return `<div class="photo-row reorder-row" draggable="true" tabindex="-1" data-order-index="${i}" aria-label="${esc(title)}, position ${i+1} of ${rows.length}"><div class="photo-order-heading">${mediaOrderButtons(i,rows.length,title)}${preview?`<img class="media-thumb" src="${esc(preview)}" alt="" loading="lazy" draggable="false">`:''}<strong>Photo ${i+1}</strong></div><label>Full-size image URL<input data-photo="${i}" data-key="url" value="${esc(r.url)}"></label><label>Small image URL (optional)<input data-photo="${i}" data-key="thumbnail" value="${esc(r.thumbnail)}"><span class="hint">S3 pictures get a thumbnail automatically. Other images use the full-size file when blank.</span></label><label>Caption<input data-photo="${i}" data-key="caption" value="${esc(r.caption)}"></label><label>Image description (alt text)<input data-photo="${i}" data-key="alt" value="${esc(r.alt||r.caption)}"></label></div>`;
  }).join('');
  list.querySelectorAll('[data-key=caption]').forEach(input=>{const row=rows[Number(input.dataset.photo)];attachDescriptionSuggestion(input,()=>({kind:'image',url:row.url,context:row.caption}), 'title', value=>row.caption=value);});
  list.querySelectorAll('[data-key=alt]').forEach(input=>{const row=rows[Number(input.dataset.photo)];attachDescriptionSuggestion(input,()=>({kind:'image',url:row.url,context:row.caption}), 'alt_text', value=>row.alt=value);});
  list.scrollTop=scrollTop;
  bindMediaOrder(list,(from,to)=>{rows.splice(to,0,rows.splice(from,1)[0]);draw();$('#photo-progress').textContent=`Moved photo to position ${to+1} of ${rows.length}.`;},()=>!$('#insert-photos').disabled);
  list.querySelectorAll('[data-photo]').forEach(el=>el.oninput=()=>{const row=rows[el.dataset.photo];row[el.dataset.key]=el.value;if(el.dataset.key==='url'){row.thumbnail='';$(`[data-photo="${el.dataset.photo}"][data-key="thumbnail"]`).value='';}});
 };
 $("#photos-s3").onclick=()=>s3Picker({kind:"image",multiple:true,onSelect:files=>{for(const file of files){const url=file.pair?.full_url||file.url;if(!rows.some(row=>row.url===url))rows.push({url,thumbnail:file.pair?.small_url||"",caption:file.name.replace(/\.[^.]+$/,"").replace(/[-_]/g," ")});}draw();}});
 $("#read-urls").onclick=()=>{for(const line of $("#photo-urls").value.split("\n").filter(x=>x.trim())){const [url,...parts]=line.split("|");const paired=parts.length>1||(parts.length>0&&mediaURL(parts[0].trim()));rows.push({url:url.trim(),thumbnail:paired?parts.shift().trim():"",caption:parts.join("|").trim()});}$("#photo-urls").value="";draw();};
 $("#photo-files").onchange=async e=>{const button=$("#insert-photos");button.disabled=true;try{for(const file of e.target.files){const item=await upload(file);rows.push({url:item.url,thumbnail:"",caption:file.name.replace(/\.[^.]+$/,"").replace(/[-_]/g," ")});draw();}}catch(error){dialogError(error);}finally{button.disabled=false;}};
 $("#insert-photos").onclick=async()=>{
  if(!rows.length)return dialogError("Add at least one photo.");
  if(rows.some(r=>!mediaURL(r.url)||(r.thumbnail&&!mediaURL(r.thumbnail))))return dialogError("Use complete image URLs or uploaded photos.");
  await photoDialogAction(async()=>{
   $('#photo-progress').textContent='Preparing pictures…';
   try{
   await prepareS3PhotoRows(rows);draw();
   const form=$("#page-form"),title=form.elements.title.value||"Photo";
   if(!form.elements.tile_image.value)form.elements.tile_image.value=rows[0].thumbnail||rows[0].url;
   if(!form.elements.image.value)form.elements.image.value=rows[0].url;
   insert('<section class="gallery" align="center">\n'+rows.map((r,i)=>`<a href="${esc(r.url)}" data-lightbox="mygallery" data-title="${esc(r.caption||title)}"><img src="${esc(r.thumbnail||r.url)}" alt="${esc(r.alt||r.caption||`${title}, photo ${i+1}`)}" loading="lazy" decoding="async"></a>`).join("\n")+'\n</section><p><br></p>');
   }finally{$('#photo-progress').textContent='';}
  });
 };
 });}

function documentDialog(existing=null){
 showDialog(existing?"Edit PDF link":"Add a PDF",`<button type="button" class="secondary" id="pdf-s3">Choose PDF from S3</button><label>Upload a PDF<input id="pdf-file" type="file" accept="application/pdf"></label><label>PDF URL<input id="pdf-url" value="${esc(existing?.getAttribute('href')||'')}"></label><label>Link text<input id="pdf-title" value="${esc(existing?.textContent||'View document (PDF)')}"></label><p class="hint">Describe the document in the link text. A description does not make the contents of a PDF accessible; its reading order and tags need their own review.</p><div class="dialog-actions"><button id="insert-pdf">${existing?'Update link':'Insert link'}</button></div>`,()=>{
  attachDescriptionSuggestion($('#pdf-title'),()=>({kind:'pdf',url:$('#pdf-url').value,context:$('#pdf-title').value}),'link_text');
  $('#pdf-s3').onclick=()=>s3Picker({kind:'pdf',onSelect:files=>{$('#pdf-url').value=files[0].url;}});
  $('#pdf-file').onchange=event=>action($('#insert-pdf'),async()=>{try{if(event.target.files[0])$('#pdf-url').value=(await upload(event.target.files[0])).url;}catch(error){dialogError(error);}});
  $('#insert-pdf').onclick=()=>{
   const url=$('#pdf-url').value.trim(),text=$('#pdf-title').value.trim();
   if(!mediaURL(url)||!text)return dialogError('Choose a PDF and enter descriptive link text.');
   if(existing){existing.setAttribute('href',url);existing.textContent=text;existing.removeAttribute('aria-label');mediaChanged();mediaDialog();}
   else insert(`<p><a href="${esc(url)}">${esc(text)}</a></p>`);
  };
 });
}
async function deleteDialog(){
 try{
  await refresh();
  const pages=await Promise.all([...selected].map(id=>api("page?id="+encodeURIComponent(id))));
  const replacements=Object.fromEntries(state.pages.filter(page=>!selected.has(page.id)).map(page=>[page.url,page.title]));
  const mainReplacements=Object.fromEntries(state.section_pages.filter(page=>!selected.has(page.id)).map(page=>[page.url,page.title]));
  showDialog("Delete selected pages",`<p>Review the replacement for each page. Main pages keep their linked pages and image files. This complete change can be undone from Recent changes.</p>
  <form id="delete-pages-form">${pages.map((page,i)=>{
   const main=state.section_pages.find(item=>item.id===page.id);
   return `<div class="photo-row"><h3>${esc(page.meta.title)}</h3><p class="hint">${main?'Main page':'Detail page'}</p>
   <label>${main?'Replacement main page':'Replacement page (optional)'}<select data-replacement="${i}">${main?options(mainReplacements,'/'):'<option value="">No replacement</option>'+options(replacements,'')}</select></label>
   ${main?`<label>Sections and tiles<select data-delete-tiles="${i}">${options({move:'Move to the replacement main page',hide:'Remove tiles and sections; keep linked pages'},'move')}</select></label>`:''}</div>`;
  }).join('')}<div class="dialog-actions"><button type="submit" class="danger" id="confirm-delete">Delete ${pages.length} page${pages.length===1?'':'s'}</button></div></form>`,()=>{
   $('#delete-pages-form').onsubmit=async event=>{
    event.preventDefault();const button=$('#confirm-delete');button.disabled=true;
    try{
     const result=await api("delete",{main_pages_revision:state.main_pages_revision,pages:pages.map((page,i)=>({id:page.id,revision:page.revision,replacement:$(`[data-replacement="${i}"]`).value,tile_action:$(`[data-delete-tiles="${i}"]`)?.value}))});
     selected.clear();dialog.close();message(result.message);await refresh();activate("pages");
    }catch(error){dialogError(error);}finally{button.disabled=false;}
   };
  });
 }catch(error){message(error.message,true);}
}

function renderArrange(){
 main.innerHTML=heading("Arrange your tiles","Choose a section, drag tiles into order, and save.")+
 `<section class="card">${Object.keys(state.groups).length?`<label>Section<select id="arrange-group">${options(state.groups,Object.keys(state.groups)[0])}</select></label><p class="hint">Drag a tile or use its arrows. Hold it near the top or bottom of the list to scroll.</p><div id="sort-list" role="group" aria-label="Tile order"></div><p id="tile-order-status" class="hint" role="status" aria-live="polite"></p><div class="dialog-actions"><button id="save-order">Save tile order</button></div>`:'<p class="empty">Add a section in Sections before arranging tiles.</p>'}</section>`;
 if(!Object.keys(state.groups).length)return;
 $("#arrange-group").onchange=()=>{arranged=[...(state.tiles[$("#arrange-group").value]||[])];$("#sort-list").scrollTop=0;sortRows();$("#tile-order-status").textContent='';};
 $("#arrange-group").onchange();
 $("#save-order").onclick=e=>action(e.currentTarget,async()=>{
  const group=$("#arrange-group"),list=$("#sort-list"),status=$("#tile-order-status"),buttons=[...list.querySelectorAll('button')];
  const disabled=buttons.map(button=>button.disabled);group.disabled=true;buttons.forEach(button=>button.disabled=true);list.cancelMediaDrag?.();
  try{const result=await api("reorder",{group:group.value,order:arranged.map(t=>t.page)});message(result.message);await refresh();status.textContent='Tile order saved.';}
  finally{group.disabled=false;buttons.forEach((button,index)=>button.disabled=disabled[index]);}
 });
}
function sortRows(){
 const list=$("#sort-list"),scrollTop=list.scrollTop;list.cancelMediaDrag?.();
 list.innerHTML=arranged.map((tile,index)=>`<div class="sort-row reorder-row" draggable="true" tabindex="-1" data-order-index="${index}" aria-label="${esc(tile.title)}, position ${index+1} of ${arranged.length}">${mediaOrderButtons(index,arranged.length,tile.title)}<img src="${esc(tile.image)}" alt="" draggable="false" loading="lazy"><div class="tile-description"><h3>${esc(tile.title)}</h3><small>${esc(tile.page)}</small></div></div>`).join('')||'<p class="empty">There are no tiles in this section yet.</p>';
 list.scrollTop=scrollTop;
 bindMediaOrder(list,(from,to)=>{
  arranged.splice(to,0,arranged.splice(from,1)[0]);sortRows();
  $('#tile-order-status').textContent=`Moved to position ${to+1} of ${arranged.length}. Choose Save tile order to keep this order.`;
 },()=>!$('#save-order')?.disabled);
}
function renderPeople(){main.innerHTML=heading("People & profile links","Update a profile once to update linked mentions across your website.",'<button id="new-person">+ Add person</button>')+`<section class="card">${Object.entries(state.people).sort((a,b)=>a[1].name.localeCompare(b[1].name)).map(([id,p])=>`<div class="person-row"><div><h3>${esc(p.name)}</h3><a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.url)}</a></div><button class="secondary" data-person="${id}">Edit</button></div>`).join("")}</section>`;$("#new-person").onclick=()=>personDialog();document.querySelectorAll("[data-person]").forEach(b=>b.onclick=()=>personDialog(b.dataset.person));}
function personDialog(id){const person=state.people[id]||{};showDialog(id?"Edit profile":"Add a person",`<form id="person-form"><label>Full name${field("name",person.name)}</label><label>Public profile URL<input name="url" type="url" required value="${esc(person.url)}"></label><label>Other forms of their name<textarea name="aliases" placeholder="One name per line">${esc((person.aliases||[]).join("\n"))}</textarea><span class="hint">Keep short names or initials already used on your pages.</span></label><div class="dialog-actions"><button>Save profile</button></div></form>`,()=>{$("#person-form").onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,b=f.querySelector("button");b.disabled=true;try{const result=await api("person",{id,name:f.elements.name.value,url:f.elements.url.value,aliases:f.elements.aliases.value.split("\n")});dialog.close();message(result.message);await refresh();renderPeople();}catch(error){dialogError(error);}finally{b.disabled=false;}};});}
function renderSettings(){const s=state.settings;main.innerHTML=heading("Shared settings","Manage the photo, CVs, and links used throughout your website.")+`<form id="settings-form"><section class="card"><h2>Your details</h2><label>Default profile photo URL${field("profile_image",s.profile_image)}<span class="hint">Also updates your favicon and default sharing image.</span></label><label>Profile photo description${field("profile_image_alt",s.profile_image_alt)}</label><label>Email address<input type="email" name="email" value="${esc(s.email)}"></label><div class="two-col"><label>Two-page CV URL${field("two_page",s.cv.two_page)}</label><label>Full CV URL${field("full",s.cv.full)}</label><label>Two-page CV link text${field("two_page_label",s.cv_labels?.two_page||"Two Page CV")}</label><label>Full CV link text${field("full_label",s.cv_labels?.full||"Full CV")}</label></div></section><section class="card"><h2>Social and academic profiles</h2>${Object.entries(s.social).map(([key,value])=>`<label>${esc(key.replace(/_/g," "))}<input name="social-${key}" value="${esc(value)}"></label>`).join("")}</section><div class="save-bar"><small>Changes apply throughout the website.</small><button>Save shared settings</button></div></form>`+storageSettingsPanel();bindStorageSettings();for(const name of ["profile_image","two_page","full"])attachS3Field($("#settings-form").elements[name],name==="profile_image"?"image":"pdf");for(const name of ["two_page","full"])attachDescriptionSuggestion($("#settings-form").elements[name+"_label"],()=>({kind:"pdf",url:$("#settings-form").elements[name].value}),"link_text");attachDescriptionSuggestion($("#settings-form").elements.profile_image_alt,()=>({kind:"image",url:$("#settings-form").elements.profile_image.value}));$("#settings-form").onsubmit=e=>{e.preventDefault();const f=e.currentTarget;action(f.querySelector("button"),async()=>{const result=await api("settings",{profile_image:f.elements.profile_image.value,profile_image_alt:f.elements.profile_image_alt.value,email:f.elements.email.value,cv:{two_page:f.elements.two_page.value,full:f.elements.full.value},cv_labels:{two_page:f.elements.two_page_label.value,full:f.elements.full_label.value},social:Object.fromEntries(Object.keys(s.social).map(k=>[k,f.elements['social-'+k].value]))});message(result.message);await refresh();});};}
function renderHistory(){main.innerHTML=heading("Recent changes","Each saved operation has a local backup. Undo the latest change first.")+`<section class="card">${state.history.map(entry=>`<div class="history-row"><div><h3>${esc(entry.label)}</h3><small>${esc(new Date(entry.time).toLocaleString())}${entry.undone?' · Undone':''}</small></div>${entry.canUndo?`<button class="secondary" data-undo="${entry.id}">Undo change</button>`:''}</div>`).join("")||'<p class="empty">Your saved changes will appear here.</p>'}</section>`;document.querySelectorAll("[data-undo]").forEach(b=>b.onclick=()=>action(b,async()=>{const result=await api("undo",{id:b.dataset.undo});message(result.message);await refresh();renderHistory();}));}
function renderPublish(){reviewId=null;main.innerHTML=heading("Review & publish","Check the complete update before sending it to your live website.")+`<section class="card"><h2>1. Build and check your changes</h2><p class="muted">This checks the production pages, local links, sitemap, profile links, redirects, and video dates.</p><button id="review-changes">Review &amp; validate</button><p class="form-error" id="review-error"></p></section><section class="card" id="publish-card" hidden><h2>2. Review the files and publish</h2><p id="review-result"></p><p class="hint">All listed changes, including edits made outside the manager, will be included.</p><div class="file-list" id="review-files"></div><label style="margin-top:20px">Describe this update<input id="commit-message" value="Update website content"></label><button id="publish-now">Publish changes to the website</button><p class="hint">Creates a Git commit and pushes to main on GitHub. Your existing Pages workflow then deploys the website. GitHub access must already be configured on this computer.</p></section>`;
 $("#review-changes").onclick=e=>action(e.currentTarget,async()=>{$("#review-error").textContent="Building and checking your update…";try{const result=await api("review",{});reviewId=result.id;$("#review-error").textContent="";$("#review-result").textContent=result.message;$("#review-files").textContent=result.files.join("\n");$("#publish-card").hidden=false;}catch(error){$("#review-error").textContent=error.message;}});
 $("#publish-now").onclick=e=>action(e.currentTarget,async()=>{const result=await api("publish",{review:reviewId,message:$("#commit-message").value});message(result.message);$("#publish-card").hidden=true;await refresh();});
}
window.addEventListener("beforeunload",event=>{if(current&&bodyDirty){event.preventDefault();event.returnValue="";}});
(async()=>{try{await refresh();render();}catch(error){main.textContent=error.message;message(error.message,true);}})();
setInterval(async()=>{try{renderStatus(await api("status"));}catch{}},2000);
