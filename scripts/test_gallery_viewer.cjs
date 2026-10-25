// Run with: node --test scripts/test_gallery_viewer.cjs
// Uses the same ignored jsdom installation as test_manager_media.cjs.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const root = path.resolve(__dirname, '..');
const {JSDOM} = require(path.join(root, '.site-manager/ui-tests/node_modules/jsdom'));

async function fixture(t) {
  const page = fs.readFileSync(path.join(root, 'pages', 'great-smoky-mountains-mount-mitchell-and-percy-priest-lake-trip-july-2026.html'), 'utf8');
  const dom = new JSDOM(`<!doctype html><html><body>${page.replace(/^---[\s\S]*?---\s*/, '')}</body></html>`, {url: 'http://localhost/', runScripts: 'outside-only'});
  t.after(() => dom.window.close());
  const w = dom.window;
  const styles = w.document.createElement('style');
  styles.textContent = fs.readFileSync(path.join(root, 'assets/css/lightbox.min.css'), 'utf8') + fs.readFileSync(path.join(root, 'assets/css/blog_style.css'), 'utf8');
  w.document.head.append(styles);
  vm.runInContext(fs.readFileSync(path.join(root, 'assets/js/lightbox-plus-jquery.min.js'), 'utf8'), dom.getInternalVMContext());
  const head = fs.readFileSync(path.join(root, '_includes/head.html'), 'utf8');
  const configuration = head.match(/<script>(lightbox\.option\([\s\S]*?\);)<\/script>/);
  assert(configuration, 'Every shared page must apply the gallery options');
  vm.runInContext(configuration[1], dom.getInternalVMContext());
  await new Promise(resolve => w.jQuery(resolve));
  w.jQuery.fx.off = true;
  return {w, d: w.document, viewer: w.lightbox, $: w.jQuery};
}

test('The actual shipped viewer focuses without scrolling after differently sized photos', async t => {
  const {viewer} = await fixture(t);
  const focusOptions = [];
  viewer.$lightbox[0].focus = options => focusOptions.push(options);
  viewer.showImage = () => {};
  for (const [width, height] of [[300, 600], [800, 400], [400, 600]]) viewer.sizeContainer(width, height);
  assert.equal(focusOptions.length, 3);
  assert(focusOptions.every(options => options?.preventScroll === true), 'Every transition must avoid browser focus scrolling');
});

function imageRequests(w) {
  const requests = [];
  w.Image = function() {
    const image = w.document.createElement('img');
    let width = 0, height = 0;
    Object.defineProperties(image, {
      naturalWidth: {get: () => width}, naturalHeight: {get: () => height},
      src: {get: () => image.getAttribute('src'), set: url => {image.setAttribute('src', url);requests.push({image, url});}}
    });
    image.finish = () => {width = 1200;height = 800;image.onload();};
    return image;
  };
  return requests;
}

test('Previously viewed photos reuse the loaded DOM image with no new request or slow transition', async t => {
  const {w, d, viewer, $} = await fixture(t);
  const requests = imageRequests(w), anchors = d.querySelectorAll('a[data-lightbox]');
  viewer.options.fitImagesInViewport = false;
  viewer.start($(anchors[0]));
  assert.equal(requests.length, 1, 'Do not preload unvisited neighbors');
  requests[0].image.finish();
  assert.equal(viewer.$image[0], requests[0].image);
  viewer.changeImage(1);requests[1].image.finish();
  const originalSize = viewer.sizeContainer, instant = [];
  viewer.sizeContainer = function(width, height, cached) {instant.push(cached);return originalSize.call(this, width, height, cached);};
  viewer.changeImage(0);
  assert.equal(requests.length, 2, 'Returning must not assign the URL to another image');
  assert.equal(viewer.$image[0], requests[0].image);
  assert.equal(instant.at(-1), true, 'Skip the loading and resize animation for cache hits');
  viewer.end();viewer.start($(anchors[0]));
  assert.equal(requests.length, 2, 'Keep loaded photos when closing and reopening the viewer');
  assert.equal(viewer.$image[0], requests[0].image);
});

test('Loading is deduplicated and stale photo completions cannot replace the current photo or reopen a closed viewer', async t => {
  const {w, d, viewer, $} = await fixture(t);
  const requests = imageRequests(w);
  viewer.options.fitImagesInViewport = false;
  viewer.start($(d.querySelector('a[data-lightbox]')));
  viewer.changeImage(0);
  assert.equal(requests.length, 1, 'Reuse an in-flight request for the same URL');
  viewer.changeImage(1);requests[0].image.finish();
  assert.notEqual(viewer.$image[0], requests[0].image, 'Ignore a photo superseded by navigation');
  requests[1].image.finish();assert.equal(viewer.$image[0], requests[1].image);
  viewer.changeImage(2);viewer.end();requests[2].image.finish();
  assert.equal(viewer.$image[0], requests[1].image);
  assert.equal(viewer.$lightbox.css('display'), 'none');
});

test('Failed image loads can be retried and the visited-photo cache has a fixed bound', async t => {
  const {w, d, viewer, $} = await fixture(t);
  const requests = imageRequests(w);
  viewer.options.fitImagesInViewport = false;viewer.options.imageCacheSize = 2;
  viewer.start($(d.querySelector('a[data-lightbox]')));
  requests[0].image.onerror();
  assert.equal(viewer.imageCache.size, 0);
  viewer.changeImage(0);requests[1].image.finish();
  viewer.changeImage(1);requests[2].image.finish();
  viewer.changeImage(2);requests[3].image.finish();
  assert.equal(viewer.imageCache.size, 2);
  viewer.changeImage(1);assert.equal(requests.length, 4, 'A recent cached photo is reused');
  viewer.changeImage(0);assert.equal(requests.length, 5, 'An evicted photo is loaded normally');
});

test('Arrow hints appear briefly and the close control is accessible in the top image corner', async t => {
  const {w, d, viewer, $} = await fixture(t);
  const requests = imageRequests(w), close = d.querySelector('#lightbox .lb-close');
  assert.equal(close.tagName, 'BUTTON');assert.equal(close.getAttribute('aria-label'), 'Close image');
  assert(close.closest('.lb-container'));
  assert.equal(w.getComputedStyle(close).position, 'absolute');
  assert.equal(w.getComputedStyle(close).right, '10px');
  assert.equal(d.querySelectorAll('#lightbox .lb-close').length, 1);
  const timers = [], originalTimer = w.setTimeout;
  w.setTimeout = (callback, duration, ...args) => {if(duration === viewer.options.navigationHintDuration)timers.push(callback);return originalTimer(callback, duration, ...args);};
  viewer.options.fitImagesInViewport = false;
  viewer.start($(d.querySelector('a[data-lightbox]')));requests[0].image.finish();
  assert(viewer.$lightbox.hasClass('lb-show-navigation'));
  timers[0]();assert(!viewer.$lightbox.hasClass('lb-show-navigation'));
  for (const filename of ['prev.png', 'next.png', 'close.png', 'loading.gif']) assert(fs.existsSync(path.join(root, 'assets/images', filename)));
  close.click();assert.equal(viewer.$lightbox.css('display'), 'none');
  assert(!d.body.classList.contains('lb-disable-scrolling'));
});

test('Keyboard and mouse navigation work while background scrolling stays disabled', async t => {
  const {w, d, viewer, $} = await fixture(t);
  const changed = [];
  viewer.changeImage = index => {changed.push(index);viewer.currentImageIndex = index;};
  viewer.start($(d.querySelector('a[data-lightbox]')));
  assert(viewer.album.length > 1, 'Use the real trip gallery');
  assert(d.body.classList.contains('lb-disable-scrolling'));
  viewer.enableKeyboardNav();
  const keydown = new w.KeyboardEvent('keydown', {key: 'ArrowRight', keyCode: 39, bubbles: true, cancelable: true});
  viewer.$overlay[0].dispatchEvent(keydown);
  assert(keydown.defaultPrevented, 'Do not also run the browser arrow-key action');
  viewer.$overlay.trigger($.Event('keyup', {keyCode: 39}));
  assert.equal(viewer.currentImageIndex, 1);
  viewer.$lightbox.find('.lb-next').trigger('click');
  assert.equal(viewer.currentImageIndex, 2);
  viewer.$overlay.trigger($.Event('keyup', {keyCode: 37}));
  assert.equal(viewer.currentImageIndex, 1);
  assert(d.body.classList.contains('lb-disable-scrolling'));
  viewer.$overlay.trigger($.Event('keyup', {keyCode: 27}));
  assert(!d.body.classList.contains('lb-disable-scrolling'), 'Restore normal scrolling on close');
  assert.deepEqual(changed, [0, 1, 2, 1]);
});

test('Loading remains centered and image controls share hide/reveal behavior', async t => {
  const {w,d,viewer,$}=await fixture(t);imageRequests(w);
  viewer.start($(d.querySelector('a[data-lightbox]')));
  const loader=d.querySelector('.lb-loader'),style=w.getComputedStyle(loader);
  assert(loader.parentElement.classList.contains('lb-outerContainer'));
  assert.equal(style.top,'50%');assert.equal(style.left,'50%');assert.equal(style.transform.replace(/\s/g,''),'translate(-50%,-50%)');
  assert.notEqual(style.display,'none');
  assert.equal(loader.getAttribute('role'),'status');
  const css=fs.readFileSync(path.join(root,'assets/css/blog_style.css'),'utf8');
  assert.match(css,/#lightbox \.lb-nav a,\s*#lightbox \.lb-close\s*\{/);
  assert.match(css,/#lightbox\.lb-show-navigation \.lb-close/);
  assert.match(css,/#lightbox \.lb-outerContainer:focus-within \.lb-close/);
});

test('The modal isolates background content, contains keyboard focus and restores the triggering link', async t => {
 const {w,d,viewer,$}=await fixture(t);const requests=imageRequests(w),anchor=d.querySelector('a[data-lightbox]');
 anchor.focus();viewer.options.fitImagesInViewport=false;viewer.start($(anchor));
 assert.equal(viewer.$lightbox.attr('role'),'dialog');assert.equal(viewer.$lightbox.attr('aria-modal'),'true');
 assert.equal(viewer.$lightbox.attr('aria-hidden'),'false');assert.equal(d.activeElement,viewer.$lightbox[0]);
 assert(anchor.closest('[inert]'));
 const event=new w.KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true});viewer.$lightbox[0].dispatchEvent(event);
 assert(event.defaultPrevented);assert(viewer.$lightbox[0].contains(d.activeElement));
 const escape=new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true});viewer.$lightbox[0].dispatchEvent(escape);
 assert.equal(viewer.$lightbox.attr('aria-hidden'),'true');assert.equal(d.activeElement,anchor);assert(!anchor.closest('[inert]'));
 requests[0].image.finish();assert.equal(viewer.$lightbox.css('display'),'none');
});
