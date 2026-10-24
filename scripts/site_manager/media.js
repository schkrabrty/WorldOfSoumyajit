"use strict";

function youtubeId(value){
 try{
  const url=new URL(value,location.origin),host=url.hostname.replace(/^www\./,"");let id="";
  if(host==="youtu.be")id=url.pathname.slice(1);
  else if(["youtube.com","m.youtube.com","youtube-nocookie.com"].includes(host))id=url.searchParams.get("v")||url.pathname.split("/").pop();
  return /^[A-Za-z0-9_-]{11}$/.test(id)?id:null;
 }catch{return null;}
}
function sourceURL(image){return image.dataset.sourceUrl||image.getAttribute("src")||"";}
function mediaChanged(){bodyDirty=true;contentDirty=true;}
function mediaURL(value){return /^https?:\/\//.test(value)||value.startsWith("/assets/");}

let mediaObserver=null;
function bindMediaControls(editor){
 if(mediaObserver)mediaObserver.disconnect();
 const update=()=>{
  const photos=editor.querySelectorAll('img').length,clips=editor.querySelectorAll('iframe').length;
  const count=$("#page-media-count");
  if(count)count.textContent=`This page contains ${photos} picture${photos===1?'':'s'} and ${clips} video${clips===1?'':'s'}.`;
 };
 mediaObserver=new MutationObserver(update);
 mediaObserver.observe(editor,{childList:true,subtree:true});update();
 editor.addEventListener('click',event=>{
  const image=event.target.closest?.('img');
  if(image&&editor.contains(image)){event.preventDefault();photoEditDialog(image);}
 });
}

function removePageMedia(item){
 if(item.tagName==='IMG'){
  const anchor=item.closest('a[data-lightbox]'),gallery=item.closest('.gallery');item.remove();
  if(anchor&&!anchor.children.length&&!anchor.textContent.trim())anchor.remove();
  if(gallery&&!gallery.querySelector('img')&&!gallery.textContent.trim())gallery.remove();
 }else{
  const wrapper=item.closest('.videoWrapper');item.remove();
  if(wrapper&&!wrapper.children.length&&!wrapper.textContent.trim())wrapper.remove();
 }
 mediaChanged();
}

function mediaDialog(){
 if(htmlMode)$("#html-toggle").click();
 const items=[...$("#editor").querySelectorAll("img,iframe")];
 showDialog("Manage pictures & videos",`<p class="muted">Replace a picture or video, update its details, or remove it from this page.</p>
 <div class="media-list">${items.map((item,i)=>{
  const photo=item.tagName==="IMG",id=photo?null:youtubeId(item.getAttribute("src"));
  const url=photo?sourceURL(item):item.getAttribute("src");
  const title=photo?(item.getAttribute("alt")||`Photo ${i+1}`):(item.getAttribute("title")||`Video ${i+1}`);
  const thumbnail=photo?item.getAttribute("src"):id?`https://img.youtube.com/vi/${id}/hqdefault.jpg`:"";
  return `<div class="media-row">${thumbnail?`<img class="media-thumb" src="${esc(thumbnail)}" alt="" loading="lazy">`:'<span class="media-thumb media-placeholder">Video</span>'}<div class="media-description"><strong>${esc(title)}</strong><small>${esc(url)}</small></div><div class="media-actions"><button class="secondary" data-replace-media="${i}" ${!photo&&!id?'disabled':''}>Replace / edit</button><button class="quiet" data-remove-media="${i}">Remove</button></div></div>`;
 }).join("")||'<p class="empty">There are no pictures or videos in the page content yet.</p>'}</div>
 <p class="hint">The picture on the index tile is controlled separately in the Page tile panel. These edits take effect when you save the page.</p>
 <div class="dialog-actions"><button id="media-done">Done</button></div>`,()=>{
  $("#media-done").onclick=()=>dialog.close();
  document.querySelectorAll("[data-replace-media]").forEach(button=>button.onclick=()=>{
   const item=items[Number(button.dataset.replaceMedia)];if(item.tagName==="IMG")photoEditDialog(item);else videoDialog(item);
  });
  document.querySelectorAll("[data-remove-media]").forEach(button=>button.onclick=()=>{
   const item=items[Number(button.dataset.removeMedia)];
   removePageMedia(item);mediaDialog();
  });
 });
}

function photoEditDialog(image){
 const anchor=image.closest("a[data-lightbox]"),figure=image.closest("figure"),figureCaption=figure?.querySelector("figcaption");
 const originalSource=sourceURL(image),originalFull=anchor?.getAttribute("href")||originalSource;
 const originalCaption=anchor?.getAttribute("data-title")||figureCaption?.textContent||image.getAttribute("title")||"";
 const form=$("#page-form"),matchingTile=[originalSource,originalFull].includes(form.elements.tile_image.value),matchingSharing=[originalSource,originalFull].includes(form.elements.image.value);
 showDialog("Replace or edit picture",`<p class="muted">Choose a new picture or update the current picture’s caption and description.</p>
 <label>Upload a replacement<input type="file" id="replacement-photo" accept="image/*"></label>
 <label>Full-size image URL<input id="replacement-url" value="${esc(originalFull)}"></label>
 <label>Small image URL (optional)<input id="replacement-thumbnail" value="${esc(originalSource===originalFull?'':originalSource)}"><span class="hint">Leave blank to display the same image in the gallery and image viewer.</span></label>
 <label>Caption<input id="replacement-caption" value="${esc(originalCaption)}"></label>
 <label>Image description<input id="replacement-alt" value="${esc(image.getAttribute("alt")||originalCaption)}"></label>
 <label class="check-label"><input type="checkbox" id="replacement-use-tile" ${matchingTile||matchingSharing?'checked':''}>Also use this picture for the page tile and sharing image</label>
 <div class="dialog-actions"><button class="secondary" id="replacement-back">Back</button><button class="quiet" id="remove-picture">Remove picture</button><button id="apply-photo">Update picture</button></div>`,()=>{
  attachS3Field($("#replacement-url"));attachS3Field($("#replacement-thumbnail"));
  $("#replacement-back").onclick=mediaDialog;
  $("#remove-picture").onclick=()=>{removePageMedia(image);mediaDialog();};
  $("#replacement-photo").onchange=async event=>{
   const button=$("#apply-photo");button.disabled=true;
   try{const file=event.target.files[0];if(!file)return;const item=await upload(file);$("#replacement-url").value=item.url;$("#replacement-thumbnail").value="";}
   catch(error){dialogError(error);}finally{button.disabled=false;}
  };
  $("#apply-photo").onclick=()=>{
   const full=$("#replacement-url").value.trim(),thumbnail=$("#replacement-thumbnail").value.trim()||full;
   const caption=$("#replacement-caption").value,alt=$("#replacement-alt").value||caption;
   if(!mediaURL(full)||!mediaURL(thumbnail))return dialogError("Use complete image URLs or upload a replacement picture.");
   image.setAttribute("src",pending.has(thumbnail)?"/__uploads/"+pending.get(thumbnail):thumbnail);
   if(pending.has(thumbnail))image.dataset.sourceUrl=thumbnail;else image.removeAttribute("data-source-url");
   image.setAttribute("alt",alt);
   if(anchor){anchor.setAttribute("href",full);anchor.setAttribute("data-title",caption);}
   else if(figureCaption)figureCaption.textContent=caption;
   else if(caption)image.setAttribute("title",caption);else image.removeAttribute("title");
   if($("#replacement-use-tile").checked){form.elements.tile_image.value=thumbnail;form.elements.tile_alt.value=alt;form.elements.image.value=full;}
   mediaChanged();mediaDialog();
  };
 });
}

function existingVideoSchema(iframe){
 let metadata=current.meta;try{metadata=JSON.parse($("#metadata").value);}catch{}
 const value=metadata.structured_data||[],schemas=Array.isArray(value)?value:[value];
 return [...videos,...schemas].find(schema=>schema["@type"]==="VideoObject"&&youtubeId(schema.embedUrl)===youtubeId(iframe.getAttribute("src")))||{};
}

function videoDialog(existing=null){
 let schema=null;
 const previous=existing?existingVideoSchema(existing):{},id=existing?youtubeId(existing.getAttribute("src")):null;
 const oldSource=existing?.getAttribute("src")||"",start=oldSource?new URL(oldSource,location.origin).searchParams.get("start")||0:0;
 showDialog(existing?"Replace or edit video":"Add a YouTube video",`<label>YouTube URL<input id="video-url" type="url" placeholder="https://www.youtube.com/watch?v=…" value="${id?'https://www.youtube.com/watch?v='+id:''}"></label>
 <button id="video-details" class="secondary">Get video details</button>
 <label style="margin-top:18px">Video title<input id="video-title" value="${esc(previous.name||existing?.getAttribute("title")||'')}"></label>
 <label>Description<textarea id="video-description">${esc(previous.description||'')}</textarea></label>
 <label>Actual upload date and time, including timezone<input id="video-date" placeholder="2026-03-11T20:05:04-07:00" value="${esc(previous.uploadDate||'')}"><span class="hint">We try to retrieve this from YouTube. If unavailable, enter the actual publication timestamp.</span></label>
 <label>Start at (seconds)<input id="video-start" type="number" min="0" value="${Number(start)||0}"></label>
 <div class="dialog-actions">${existing?'<button class="secondary" id="video-back">Back</button><button class="quiet" id="remove-video">Remove video</button>':''}<button id="insert-video">${existing?'Update video':'Insert video'}</button></div>`,()=>{
  if(existing){$("#video-back").onclick=mediaDialog;$("#remove-video").onclick=()=>{removePageMedia(existing);mediaDialog();};}
  $("#video-url").oninput=()=>{schema=null;$("#video-title").value="";$("#video-description").value="";$("#video-date").value="";$("#video-start").value=0;};
  const fetchDetails=async()=>{
   schema=await api("video",{url:$("#video-url").value,title:$("#video-title").value,description:$("#video-description").value,uploadDate:$("#video-date").value});
   $("#video-title").value=schema.name;$("#video-description").value=schema.description;$("#video-date").value=schema.uploadDate;
  };
  $("#video-details").onclick=event=>action(event.currentTarget,async()=>{try{await fetchDetails();}catch(error){dialogError(error);}});
  $("#insert-video").onclick=async event=>{
   const button=event.currentTarget;button.disabled=true;
   try{
    await fetchDetails();
    if(!/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(schema.uploadDate)||Number.isNaN(Date.parse(schema.uploadDate)))throw new Error("Enter the actual upload datetime, including its timezone.");
    const startAt=Number($("#video-start").value)||0;if(!Number.isInteger(startAt)||startAt<0)throw new Error("The starting time must be a whole number of seconds.");
    const source=schema.embedUrl+(startAt?'?start='+startAt:'');videos=videos.filter(item=>item.embedUrl!==schema.embedUrl);videos.push(schema);
    if(existing){
     const caption=existing.closest(".videoWrapper")?.nextElementSibling;
     existing.setAttribute("src",source);existing.setAttribute("title",schema.name);
     if(caption?.tagName==="P"&&previous.description&&caption.textContent.trim()===previous.description)caption.textContent=schema.description;
     mediaChanged();mediaDialog();
    }else insert(`<p align="center" class="videoWrapper"><iframe width="560" height="315" src="${source}" title="${esc(schema.name)}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen loading="lazy"></iframe></p><p>${esc(schema.description)}</p>`);
   }catch(error){dialogError(error);}finally{button.disabled=false;}
  };
 });
}
