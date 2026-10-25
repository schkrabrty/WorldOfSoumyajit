"use strict";
let descriptionInventoryRequest=null;
function descriptionInventory(){return descriptionInventoryRequest ||= api('descriptions').catch(error=>{descriptionInventoryRequest=null;throw error;});}

// Suggestions stay in their own fields until the author explicitly uses one.
function attachDescriptionSuggestion(target, getMedia, field="alt_text", onApply=null){
 if(!target)return;
 const panel=document.createElement('div');panel.className='description-suggestion';
 const generate=document.createElement('button');generate.type='button';generate.className='secondary';generate.textContent='Suggest with OpenAI';
 let suggestedURL='';
 const status=document.createElement('p');status.className='hint';status.setAttribute('role','status');
 const label=document.createElement('label');label.textContent='Editable suggestion';label.hidden=true;
 const draft=document.createElement('textarea');draft.rows=3;label.append(draft);
 const use=document.createElement('button');use.type='button';use.className='quiet';use.textContent='Use this suggestion';use.hidden=true;
 panel.append(generate,status,label,use);target.closest('label').after(panel);
 generate.onclick=async()=>{
  generate.disabled=true;status.textContent='Reading media and drafting a description…';
  try{
   const media=getMedia(),result=await api('describe-media',{...media,upload_id:pending.get(media.url),regenerate:!!draft.value||media.kind==='page'});
   if(!panel.isConnected||getMedia().url!==media.url)return;
   suggestedURL=media.url;
   draft.value=result[field]||result.description||result.title;label.hidden=false;use.hidden=false;
   status.textContent=result.basis+(result.notes?' '+result.notes:'')+' Review for accuracy before using.';
   generate.textContent='Generate another suggestion';
  }catch(error){status.textContent=error.message;}finally{generate.disabled=false;}
 };
 use.onclick=()=>{if(getMedia().url!==suggestedURL){status.textContent='The source changed. Generate a suggestion for the current source first.';return;}target.value=draft.value;target.dispatchEvent(new Event('input',{bubbles:true}));onApply?.(draft.value);status.textContent='Suggestion copied. Review your changes, then save the page.';};
 // Cached drafts may be reviewed without another API request.
 descriptionInventory().then(result=>{
  if(!panel.isConnected||draft.value)return;
  const media=getMedia(),item=result.items.find(item=>item.kind===media.kind&&(item.url===media.url||item.source_url===media.url)&&item.draft);
  if(item){suggestedURL=media.url;draft.value=item.draft[field]||item.draft.description||item.draft.title;label.hidden=false;use.hidden=false;status.textContent=item.draft.basis+' Cached draft; review before using.';}
 }).catch(()=>{});
}
