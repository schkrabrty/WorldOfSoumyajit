"use strict";

const fieldHelp={
 title:'The page title appears in the browser tab and is used by default for search results and shared links.',
 heading:'The main heading (H1) shown inside the page. Use the text-style menu for smaller headings in your writing.',
 slug:'The last part of this page’s web address. Renaming an existing page creates a redirect from its old address.',
 description:'A short summary used in search results and shared links.',
 type:'Choose the kind of page you are creating. This suggests a page category and tile section.',
 section:'The page category controls its back link and how it is grouped in the manager.',
 image:'The full-size picture used when this page is shared. The tile can use a smaller version.',
 tile_enabled:'Show a clickable tile linking to this page in a main-page section.',
 tile_group:'Choose the main page and section where this page’s tile should appear. Manage the available sections in Sections.',
 tile_title:'The title displayed on the clickable tile. It can be shorter than the page title.',
 tile_caption:'A short description displayed with the tile’s title.',
 tile_image:'The picture shown on the tile. S3 originals get a smaller thumbnail automatically.',
 tile_alt:'Describe the picture for people who cannot see it.',
 tile_position:'Position 1 places this tile first in its section. New pages default to position 1.',
 show_heading:'Display the section’s name as a heading above its tiles. It remains available in the manager when hidden.',
 tile_action:'Move the section’s tiles elsewhere, or remove the tiles from main pages while keeping their linked pages.',
 destination:'Moved tiles appear first in this section, in their current order.',
 bucket:'The S3 bucket that stores your website’s pictures and files.',
 region:'The AWS region where your S3 bucket is hosted.',
 prefix:'The folder inside S3 that contains the website’s files.',
 profile:'The local AWS profile used to sign in. Passwords and access keys do not belong in this field.',
 profile_image:'The shared profile photo, favicon, and default sharing picture.',
 email:'The contact email address used throughout the website.',
 two_page:'The web address of your two-page CV PDF.',full:'The web address of your full CV PDF.',
 aliases:'Other versions of this person’s name that should use the same profile link.'
};
const idHelp={
 'heading-level':'Choose Paragraph, Section heading (H2), Subsection heading (H3), or Subsubsection heading (H4). The main heading (H1) is set above in Heading on the page.',
 'html-toggle':'Switch between the visual editor and the page’s HTML. Heading tags and embedded content are preserved.',
 'save-page':'Save this page and its tile locally, then build the preview. Publish separately when you are ready.',
 'cancel-edit':'Return to the page list. Unsaved changes can be discarded.',
 'new-page':'Create a new page. Its tile starts at position 1 in the section you choose.',
 'section-page':'Choose the main page whose sections you want to manage.',
 'section-navigation':'Show a row of links that jump to each section on this main page.',
 'add-section':'Create a section on the selected main page. New sections are placed first.',
 'reload-sections':'Reload the latest sections and tile counts, including changes made in another window.',
 'arrange-group':'Choose a section, move its tiles with the arrows, then save the tile order.',
 'save-order':'Save the order of tiles inside this section and rebuild the preview.',
 'storage-connect':'Open AWS sign-in. Complete passwords and MFA on AWS’s page.',
 's3-connect':'Open AWS sign-in. After signing in, refresh the S3 file list.',
 'storage-browse':'Browse existing S3 files. Browsing alone does not create thumbnails.',
 'storage-kind':'Show only files of the selected kind.',
 's3-search':'Filter the files currently loaded in this S3 folder.',
 's3-refresh':'Reload the current S3 folder.',
 's3-up':'Open the parent folder.',
 's3-home':'Open the configured website folder in S3.',
 's3-more':'Load the next group of files in this folder.',
 's3-choose':'Use the selected files. Pictures get missing thumbnails before they are added to the page.',
 'photo-files':'Upload pictures from this computer into the website project.',
 'photos-s3':'Choose original pictures already stored in S3. Missing thumbnails are created and uploaded automatically.',
 'photo-urls':'Paste one picture per line: full-size URL | optional thumbnail URL | caption.',
 'read-urls':'Add the pasted picture URLs to the gallery list below.',
 'insert-photos':'Prepare S3 thumbnails and insert these pictures as a gallery. Clicking a picture opens its original.',
 'replacement-photo':'Upload a new picture from this computer to replace this one.',
 'replacement-url':'The original picture opened by the image viewer.',
 'replacement-thumbnail':'The smaller picture displayed in the gallery. Leave blank to generate one for an S3 original.',
 'replacement-caption':'Text displayed with the picture in the image viewer.',
 'replacement-alt':'Describe the picture for people who cannot see it.',
 'replacement-use-tile':'Use this picture’s thumbnail for the page tile and its original for sharing.',
 'apply-photo':'Apply the picture and caption changes to the editor. Save the page afterward.',
 'remove-picture':'Remove this picture from the page content. The original file is kept.',
 'video-url':'Paste a YouTube watch, share, or embed URL.',
 'video-details':'Retrieve the video’s title, description, and publication time from YouTube.',
 'video-title':'A descriptive title for this video and its search metadata.',
 'video-description':'A summary of the video, also displayed below a newly inserted video.',
 'video-date':'The video’s actual publication date and time, including its time zone.',
 'video-start':'Start playback this many seconds into the video.',
 'insert-video':'Add or update the video in the editor. Save the page afterward.',
 'remove-video':'Remove the video embed from this page.',
 'pdf-s3':'Choose an existing PDF stored in S3.',
 'pdf-file':'Choose a PDF from this computer to add to the website project.',
 'pdf-title':'The clickable text that opens the PDF.',
 'review-changes':'Build and validate the complete website update, then review the changed files.',
 'publish-now':'Commit the reviewed changes and push them to GitHub to deploy the website.',
 'commit-message':'A short description of the update recorded in Git history.',
 rebuild:'Rebuild the local preview using the current website files.',
 search:'Find a page by its title or web address.',filter:'Show pages in a selected category.',
 'dialog-close':'Close this dialog.', 's3-close':'Close the S3 picker.'
};
const viewHelp={pages:'Create and edit pages.',sections:'Add, edit, reorder, and remove sections on main pages.',arrange:'Reorder tiles within a section.',people:'Maintain shared names and profile links.',storage:'Browse S3 files and manage your AWS connection.',settings:'Edit shared contact details, photos, CVs, and social links.',history:'Review saved changes and undo the latest operation.',publish:'Validate and publish local website changes.'};
const toolHelp={photos:'Insert pictures or a gallery into your writing.',video:'Add a YouTube video.',media:'Edit, replace, or remove pictures and videos already in this page.',link:'Insert a clickable link.',person:'Insert a person’s name with their shared profile link.',document:'Insert a link to a PDF.'};

function controlHelp(control){
 if(control.matches('#section-form [name="title"]'))return 'The name of this tile section. Renaming it keeps its existing links and tiles.';
 if(control.matches('[data-section-move]'))return 'Move this whole section earlier or later on its main page. The change saves immediately.';
 if(control.matches('[data-section-edit]'))return 'Rename this section or change whether its heading is shown.';
 if(control.matches('[data-section-delete]'))return 'Remove this section and choose what happens to its tiles. The linked pages are kept.';
 if(control.matches('[data-move]'))return 'Move this tile earlier or later. Choose Save tile order to apply the changes.';
 if(control.matches('[data-undo]'))return 'Undo the latest saved operation using its local backup.';
 if(control.matches('[data-replace-media]'))return 'Edit this picture or video, or choose a replacement.';
 if(control.matches('[data-remove-media]'))return 'Remove this item from the page content. Its original file is kept.';
 if(control.matches('.s3-field-button'))return 'Choose an existing file from S3 for this field.';
 if(control.matches('#section-form button[type="submit"]'))return 'Save this section and update the local preview.';
 if(control.matches('#remove-section-form button[type="submit"]'))return 'Remove this section using the tile option you selected. The linked pages are kept.';
 if(control.dataset.view)return viewHelp[control.dataset.view];
 if(control.dataset.tool)return toolHelp[control.dataset.tool];
 if(control.dataset.format)return 'Apply '+({bold:'bold text',italic:'italic text',insertUnorderedList:'a bulleted list'}[control.dataset.format]||'formatting')+' to the selected text.';
 if(control.dataset.key==='url')return 'The full-size picture opened by the image viewer.';
 if(control.dataset.key==='thumbnail')return 'The smaller gallery picture. S3 originals get one automatically when blank.';
 if(control.dataset.key==='caption')return 'The picture’s caption and image description.';
 return idHelp[control.id]||fieldHelp[control.name];
}

const managerTooltip=document.createElement('div');
managerTooltip.id='manager-tooltip';managerTooltip.setAttribute('role','tooltip');managerTooltip.hidden=true;document.body.append(managerTooltip);
let helpTarget=null,helpTimer=null;
function hideHelp(){
 clearTimeout(helpTimer);
 if(helpTarget){const descriptions=(helpTarget.getAttribute('aria-describedby')||'').split(/\s+/).filter(id=>id&&id!==managerTooltip.id);if(descriptions.length)helpTarget.setAttribute('aria-describedby',descriptions.join(' '));else helpTarget.removeAttribute('aria-describedby');}
 helpTarget=null;managerTooltip.hidden=true;
}
function showHelp(target){
 hideHelp();if(!target?.dataset.help||!target.isConnected)return;
 const container=target.closest('dialog')||document.body;
 if(managerTooltip.parentElement!==container)container.append(managerTooltip);
 helpTarget=target;managerTooltip.textContent=target.dataset.help;managerTooltip.hidden=false;
 const descriptions=(target.getAttribute('aria-describedby')||'').split(/\s+/).filter(Boolean);target.setAttribute('aria-describedby',[...new Set([...descriptions,managerTooltip.id])].join(' '));
 const rect=target.getBoundingClientRect(),tip=managerTooltip.getBoundingClientRect();
 managerTooltip.style.left=Math.max(8,Math.min(rect.left,window.innerWidth-tip.width-8))+'px';
 managerTooltip.style.top=(rect.bottom+tip.height+12<window.innerHeight?rect.bottom+8:Math.max(8,rect.top-tip.height-8))+'px';
}
function applyHelp(){
 document.querySelectorAll('input,select,textarea,button').forEach(control=>{const text=controlHelp(control);if(text){control.dataset.help=text;if(control.id==='heading-level')control.removeAttribute('title');}});
 if(helpTarget&&!helpTarget.isConnected)hideHelp();
}
document.addEventListener('mouseover',event=>{const target=event.target.closest('[data-help]');if(target&&!target.contains(event.relatedTarget)){clearTimeout(helpTimer);helpTimer=setTimeout(()=>showHelp(target),350);}});
document.addEventListener('mouseout',event=>{const target=event.target.closest('[data-help]');if(target&&!target.contains(event.relatedTarget))hideHelp();});
document.addEventListener('focusin',event=>showHelp(event.target.closest('[data-help]')));
document.addEventListener('focusout',hideHelp);
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!managerTooltip.hidden){event.preventDefault();hideHelp();}});
document.addEventListener('scroll',hideHelp,true);
new MutationObserver(applyHelp).observe(document.body,{childList:true,subtree:true});
applyHelp();
