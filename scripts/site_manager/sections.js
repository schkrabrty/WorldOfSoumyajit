"use strict";

let sectionPageId='index.html',sectionBusy=false;
function sectionPage(){return state.section_pages.find(page=>page.id===sectionPageId)||state.section_pages[0];}

async function sectionAction(work){
 if(sectionBusy)return;
 sectionBusy=true;
 const controls=[...main.querySelectorAll('button,input,select'),...dialog.querySelectorAll('button,input,select'),...document.querySelectorAll('[data-view]')].map(control=>[control,control.disabled]);
 const cancel=dialog.oncancel;dialog.oncancel=event=>event.preventDefault();
 controls.forEach(([control])=>control.disabled=true);
 try{await work();}catch(error){if(dialog.open)dialogError(error);else message(error.message,true);}
 finally{sectionBusy=false;dialog.oncancel=cancel;controls.forEach(([control,disabled])=>control.disabled=disabled);}
}

async function saveSectionChange(data,closeDialog=false){
 const result=await api('sections',{page:sectionPageId,revision:state.sections_revision,...data});
 if(closeDialog)dialog.close();
 await refresh();renderSections();message(result.message);
}

function renderSections(){
 const page=sectionPage();sectionPageId=page.id;
 main.innerHTML=heading('Main pages & sections','Add main pages and arrange their sections. Changes are saved locally and appear in the preview.','<div class="inline-actions"><button id="new-page">+ New page</button><button id="reload-sections" class="secondary">Reload</button></div>')+
 `<section class="card"><label>Main page<select id="section-page">${options(Object.fromEntries(state.section_pages.map(item=>[item.id,item.title])),page.id)}</select></label>
 <div class="inline-actions section-actions"><button id="add-section">+ Add section</button><button class="secondary" id="edit-main-page">Edit page</button><a class="button secondary" href="${esc(page.url)}" target="_blank" rel="noopener noreferrer">Preview this page ↗</a></div>
 <p class="hint">Use the checkboxes in Pages and Delete selected to remove main or detail pages. The homepage is required.</p>
 <label class="check-label"><input type="checkbox" id="section-navigation" ${page.navigation?'checked':''}>Show section links above the tiles</label>
 <p class="hint">Use the arrows to move a section. Each move saves immediately. New page tiles appear first within their chosen section by default.</p>
 <div id="section-list" class="section-list">${page.sections.map((section,index)=>`<div class="section-row">
  <div class="section-description"><h3>${esc(section.title)}</h3><small>${section.count} tile${section.count===1?'':'s'} · Heading ${section.show_heading?'shown':'hidden'}</small></div>
  <div class="section-row-actions"><button class="icon-button" data-section-move="${index}" data-direction="-1" ${index===0?'disabled':''} aria-label="Move ${esc(section.title)} earlier">↑</button>
  <button class="icon-button" data-section-move="${index}" data-direction="1" ${index===page.sections.length-1?'disabled':''} aria-label="Move ${esc(section.title)} later">↓</button>
  <button class="secondary" data-section-edit="${esc(section.id)}">Edit</button><button class="quiet" data-section-delete="${esc(section.id)}">Remove</button></div></div>`).join('')||'<p class="empty">There are no sections on this page yet. Add a section to start placing tiles here.</p>'}</div>
 <p class="hint">To arrange pictures inside a section, use Arrange tiles. You can undo section changes from Recent changes.</p></section>`;
 $('#section-page').onchange=event=>{sectionPageId=event.target.value;renderSections();};
 $('#new-page').onclick=()=>newPageDialog('main');
 $('#edit-main-page').onclick=()=>editPage(page.id);
 $('#reload-sections').onclick=()=>sectionAction(async()=>{await refresh();renderSections();});
 $('#add-section').onclick=()=>sectionDialog();
 $('#section-navigation').onchange=()=>sectionAction(async()=>{try{await saveSectionChange({action:'navigation',navigation:$('#section-navigation').checked});}catch(error){$('#section-navigation').checked=page.navigation;throw error;}});
 main.querySelectorAll('[data-section-edit]').forEach(button=>button.onclick=()=>sectionDialog(button.dataset.sectionEdit));
 main.querySelectorAll('[data-section-delete]').forEach(button=>button.onclick=()=>removeSectionDialog(button.dataset.sectionDelete));
 main.querySelectorAll('[data-section-move]').forEach(button=>button.onclick=()=>sectionAction(async()=>{
  const order=page.sections.map(section=>section.id),index=Number(button.dataset.sectionMove),next=index+Number(button.dataset.direction);
  [order[index],order[next]]=[order[next],order[index]];await saveSectionChange({action:'reorder',order});
 }));
}

function newPageDialog(preferred='detail'){
 showDialog('New page',`<label>Page kind<select id="new-page-kind">${options({detail:'Detail page — linked from a tile',main:'Main page — listed in the website menu'},preferred)}</select></label>
 <p class="hint">Both kinds use the same editor for writing, pictures, and videos.</p><div class="dialog-actions"><button id="continue-new-page">Continue</button></div>`,()=>{
  $('#continue-new-page').onclick=()=>{if($('#new-page-kind').value==='main')newMainPageDialog();else{dialog.close();editPage();}};
 });
}

function newMainPageDialog(){
 showDialog('Add a main page',`<p class="muted">Create a page in the website menu, with an initial section for its tiles.</p>
 <form id="main-page-form"><label>Page title<input name="title" maxlength="120" required></label>
 <label>Page address<input name="slug" pattern="[a-z0-9]+(-[a-z0-9]+)*" required placeholder="my-new-main-page"><span class="hint">Use lowercase English letters, numbers, and hyphens.</span></label>
 <label>Search description<textarea name="description" required></textarea></label>
 <label>First section title<input name="section_title" value="Pages" maxlength="120" required></label>
 <div class="dialog-actions"><button type="submit">Create main page</button></div></form>`,()=>{
  const form=$('#main-page-form');let customSlug=false;
  const suggestion=()=>({kind:'page',url:'new-main-page',context:form.elements.title.value+' '+form.elements.description.value+' '+form.elements.section_title.value});
  attachDescriptionSuggestion(form.elements.title,suggestion,'title');attachDescriptionSuggestion(form.elements.description,suggestion,'description');
  form.elements.slug.oninput=()=>customSlug=true;
  form.elements.title.oninput=()=>{if(!customSlug)form.elements.slug.value=slug(form.elements.title.value);};
  form.onsubmit=event=>{event.preventDefault();const values=Object.fromEntries(new FormData(form));sectionAction(async()=>{
   const result=await api('main-pages',{action:'create',revision:state.main_pages_revision,...values});
   dialog.close();await refresh();sectionPageId=result.id;activate('sections');message(result.message);
  });};
 });
}


function sectionDialog(id){
 const page=sectionPage(),section=page.sections.find(item=>item.id===id);
 showDialog(section?'Edit section':'Add section',`<p class="muted">Main page: ${esc(page.title)}</p>
 <form id="section-form"><label>Section title<input name="title" value="${esc(section?.title||'')}" maxlength="120" required placeholder="For example: Recent projects"></label>
 <label class="check-label"><input type="checkbox" name="show_heading" ${section?.show_heading!==false?'checked':''}>Show this heading above the tiles</label>
 <p class="hint">${section?'Renaming keeps the section’s existing links and tiles.':'New sections are placed first. You can move them with the arrows after saving.'}</p>
 <div class="dialog-actions"><button type="submit">${section?'Save section':'Add section'}</button></div></form>`,()=>{
  $('#section-form').onsubmit=event=>{event.preventDefault();const form=event.currentTarget;
   sectionAction(()=>saveSectionChange({action:section?'edit':'create',id:section?.id,title:form.elements.title.value,show_heading:form.elements.show_heading.checked},true));
  };
 });
}

function removeSectionDialog(id){
 const section=sectionPage().sections.find(item=>item.id===id);
 const destinations=Object.fromEntries(Object.entries(state.groups).filter(([key])=>key!==id));
 const canMove=Object.keys(destinations).length>0;
 showDialog('Remove section',`<p>Remove <strong>${esc(section.title)}</strong> from ${esc(sectionPage().title)}?</p>
 <p>The linked pages and their pictures will remain available. This change can be undone from Recent changes.</p>
 <form id="remove-section-form">${section.count?`<p>This section contains ${section.count} tile${section.count===1?'':'s'}.</p>
 <label>What should happen to its tiles?<select name="tile_action">${options({...canMove?{move:'Move tiles to another section'}:{},hide:'Remove these tiles from main pages; keep the linked pages'},canMove?'move':'hide')}</select></label>
 <label id="section-destination-label">Move tiles to<select name="destination">${options(destinations,'')}</select><span class="hint">Moved tiles are placed first in the destination, keeping their current order.</span></label>`:''}
 <div class="dialog-actions"><button class="danger" type="submit">Remove section</button></div></form>`,()=>{
  const form=$('#remove-section-form');
  if(section.count){const update=()=>$('#section-destination-label').hidden=form.elements.tile_action.value!=='move';form.elements.tile_action.onchange=update;update();}
  form.onsubmit=event=>{event.preventDefault();sectionAction(()=>saveSectionChange({action:'delete',id,tile_action:form.elements.tile_action?.value,destination:form.elements.destination?.value},true));};
 });
}
