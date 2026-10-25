// DOM regression tests, with no browser or live-site writes.
// npm install --prefix .site-manager/ui-tests jsdom
// node --test scripts/test_manager_media.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const root = path.resolve(__dirname, '..');
const {JSDOM} = require(path.join(root, '.site-manager/ui-tests/node_modules/jsdom'));
const directory = path.join(__dirname, 'site_manager');
const photo = id => `<a href="https://example.com/${id}.jpg" data-lightbox="mygallery" data-title="Caption ${id}"><img src="https://example.com/${id}-small.jpg" alt="Photo ${id}"></a>`;

async function fixture(existingBody) {
  const dom = new JSDOM(fs.readFileSync(path.join(directory, 'index.html'), 'utf8'), {
    url: 'http://localhost/__manager/', runScripts: 'outside-only', pretendToBeVisual: true
  });
  const w = dom.window;
  w.scrollTo = () => {};
  w.HTMLDialogElement.prototype.showModal = function() { this.setAttribute('open', ''); };
  w.HTMLDialogElement.prototype.close = function() { this.removeAttribute('open'); };
  w.fetch = async () => ({ok: true, json: async () => ({
    id: 'existing.html', body: existingBody, revision: 'fixture', heading: 'Existing page',
    meta: {title: 'Existing page', description: 'Test page', section: 'photography'}, protected: false
  })});
  const source = fs.readFileSync(path.join(directory, 'app.js'), 'utf8');
  vm.runInContext(source.slice(0, source.indexOf('(async()=>{try{await refresh();render();')), dom.getInternalVMContext());
  for (const name of ['media.js', 'descriptions.js', 'storage.js']) vm.runInContext(fs.readFileSync(path.join(directory, name), 'utf8'), dom.getInternalVMContext());
  w.eval(`state={groups:{photography:'Photography'},group_categories:{photography:'photography'},section_pages:[],people:{},storage:{}}`);
  await w.editPage(existingBody === undefined ? undefined : 'existing.html');
  assert(w.document.querySelector('#page-form'), w.document.querySelector('#notice').textContent);
  return {dom, w, d: w.document};
}

function drag(w, from, to, after = true) {
  const dataTransfer = {setData() {}};
  const start = new w.Event('dragstart', {bubbles: true, cancelable: true});
  Object.defineProperty(start, 'dataTransfer', {value: dataTransfer});
  from.dispatchEvent(start);
  const over = new w.Event('dragover', {bubbles: true, cancelable: true});
  Object.defineProperty(over, 'clientY', {value: after ? 1 : -1});
  Object.defineProperty(over, 'dataTransfer', {value: dataTransfer});
  to.dispatchEvent(over);
  assert(over.defaultPrevented, 'A mouse drag must allow dropping on the destination');
  assert(from.classList.contains('dragging'), 'Keep the dragged row visibly selected');
  if (from !== to) assert(to.classList.contains(after ? 'drop-after' : 'drop-before'), 'Show the insertion line at the mouse position');
  const drop = new w.Event('drop', {bubbles: true, cancelable: true});
  Object.defineProperty(drop, 'clientY', {value: after ? 1 : -1});
  to.dispatchEvent(drop);
  assert(drop.defaultPrevented, 'The editor must not perform a native HTML drop');
}

for (const editing of [false, true]) test(`Manage media reorders ${editing ? 'existing' : 'new'} page images and preserves their details`, async t => {
  const body = `<p>Keep this introduction.</p><section class="gallery">${photo('a')}${photo('b')}${photo('c')}</section>`;
  const {dom, w, d} = await fixture(editing ? body : undefined);t.after(() => dom.window.close());
  if (!editing) d.querySelector('#editor').innerHTML = body;
  w.mediaDialog();
  const rows = () => [...d.querySelectorAll('#page-media-list [data-order-index]')];
  drag(w, rows()[0], rows()[2]);
  assert.deepEqual([...d.querySelectorAll('#editor img')].map(img => img.alt), ['Photo b', 'Photo c', 'Photo a']);
  rows()[2].querySelector('[data-order-direction="-1"]').click();
  assert.deepEqual([...d.querySelectorAll('#editor img')].map(img => img.alt), ['Photo b', 'Photo a', 'Photo c']);
  drag(w, rows()[2], rows()[0], false);
  assert.deepEqual([...d.querySelectorAll('#editor img')].map(img => img.alt), ['Photo c', 'Photo b', 'Photo a']);
  const saved = w.serialize();
  for (const id of ['a', 'b', 'c']) assert(saved.includes(photo(id)), `Preserve ${id}'s complete picture link`);
  assert(saved.includes('<p>Keep this introduction.</p>'));
  assert.equal(w.eval('bodyDirty && contentDirty'), true);
  assert(d.querySelector('[data-order-index="0"] [data-order-direction="-1"]').disabled);
  d.querySelector('#media-done').click();
  d.querySelector('#html-toggle').click();
  assert.equal(d.querySelector('#html-editor').value, saved);
  w.mediaDialog();
  assert.equal(d.querySelector('#editor').hidden, false);
  assert.equal(rows()[0].querySelector('strong').textContent, 'Photo c');
});

test('Add photos retains edited captions and URL pairs when dragged before insertion', async t => {
  const {dom, w, d} = await fixture();t.after(() => dom.window.close());
  w.photosDialog();
  d.querySelector('#photo-urls').value = ['a', 'b', 'c'].map(id => `https://example.com/${id}.jpg | https://example.com/${id}-small.jpg | Caption ${id}`).join('\n');
  d.querySelector('#read-urls').click();
  const caption = d.querySelector('[data-photo="0"][data-key="caption"]');
  caption.value = 'Edited caption';caption.dispatchEvent(new w.Event('input', {bubbles: true}));
  drag(w, d.querySelector('[data-order-index="0"]'), d.querySelector('[data-order-index="2"]'));
  assert.equal(d.querySelector('[data-photo="2"][data-key="caption"]').value, 'Edited caption');
  await d.querySelector('#insert-photos').onclick();
  assert.deepEqual([...d.querySelectorAll('#editor img')].map(img => img.getAttribute('src')), ['b', 'c', 'a'].map(id => `https://example.com/${id}-small.jpg`));
  assert.equal(d.querySelector('#editor a:last-child').getAttribute('data-title'), 'Edited caption');
});

test('Adding a batch at a cursor inside a gallery creates a sibling gallery', async t => {
  const {dom, w, d} = await fixture(`<p>Introduction</p><section class="gallery">${photo('a')}</section><p>After</p>`);
  t.after(() => dom.window.close());
  const range = d.createRange();range.selectNodeContents(d.querySelector('#editor a'));range.collapse(false);
  w.getSelection().removeAllRanges();w.getSelection().addRange(range);w.rememberSelection();
  w.insert(`<section class="gallery">${photo('b')}</section><p><br></p>`);
  assert.equal(d.querySelectorAll('#editor .gallery').length, 2);
  assert.equal(d.querySelectorAll('#editor .gallery .gallery').length, 0);
  assert.equal(d.querySelectorAll('#editor a a').length, 0);
  assert.equal(d.querySelectorAll('#editor img').length, 2);
});

test('Removing a picture cleans its link even when the editor left a line break', async t => {
  const {dom, w, d} = await fixture(`<section class="gallery">${photo('a').replace('</a>', '<br></a>')}</section>`);
  t.after(() => dom.window.close());
  w.removePageMedia(d.querySelector('#editor img'));
  assert.equal(d.querySelectorAll('#editor a[data-lightbox],#editor .gallery').length, 0);
});

test('Saving cleans old blank photo links and preserves real links and uploaded sources', async t => {
  const {dom, w, d} = await fixture();t.after(() => dom.window.close());
  d.querySelector('#editor').innerHTML = `<a id="keep-anchor"></a><a href="https://example.com/text.jpg" data-lightbox="mygallery">View photo</a><section class="gallery"><a href="https://example.com/empty.jpg" data-lightbox="mygallery"><br>&nbsp;\u200b</a></section><section class="gallery">${photo('a')}</section>`;
  const image = d.querySelector('#editor img');image.dataset.sourceUrl = '/assets/uploads/a.jpg';image.src = '/__uploads/preview';
  const body = w.serialize();
  assert(!body.includes('empty.jpg'));
  assert(body.includes('keep-anchor'));
  assert(body.includes('>View photo</a>'));
  assert(body.includes('src="/assets/uploads/a.jpg"'));
  assert(!body.includes('data-source-url'));
});

test('Reordering moves figure captions and video wrappers without moving surrounding prose', async t => {
  const {dom, w, d} = await fixture(`<p>Introduction</p><figure>${photo('a')}<figcaption>Keep this caption</figcaption></figure><p>Middle text</p><div class="videoWrapper"><iframe src="https://www.youtube.com/embed/OKNmkjQb4D8"></iframe></div><section class="gallery">${photo('b')}</section>`);
  t.after(() => dom.window.close());
  w.mediaDialog();
  const rows = [...d.querySelectorAll('#page-media-list [data-order-index]')];
  drag(w, rows[0], rows[2]);
  assert.equal(d.querySelector('#editor figure figcaption').textContent, 'Keep this caption');
  assert.equal(d.querySelector('#editor figure img').alt, 'Photo a');
  assert.equal(d.querySelector('#editor .videoWrapper iframe').getAttribute('src'), 'https://www.youtube.com/embed/OKNmkjQb4D8');
  assert.deepEqual([...d.querySelectorAll('#editor p')].map(p => p.textContent), ['Introduction', 'Middle text']);
});

for (const adding of [false, true]) test(`${adding ? 'Add photos' : 'Manage media'} keeps scrolling while the mouse is held at an edge and stops on exit`, async t => {
  const {dom, w, d} = await fixture(`<section class="gallery">${Array.from({length: 12}, (_, i) => photo(String(i))).join('')}</section>`);
  t.after(() => dom.window.close());
  const frames = new Map();let frameId = 0;
  w.requestAnimationFrame = callback => {frames.set(++frameId, callback);return frameId;};
  w.cancelAnimationFrame = id => frames.delete(id);
  const step = time => {const callbacks = [...frames.values()];frames.clear();callbacks.forEach(callback => callback(time));};
  if (adding) {
    w.photosDialog();
    d.querySelector('#photo-urls').value = Array.from({length: 12}, (_, i) => `https://example.com/${i}.jpg | Photo ${i}`).join('\n');
    d.querySelector('#read-urls').click();
  } else w.mediaDialog();
  const list = d.querySelector(adding ? '#photo-rows' : '#page-media-list');
  list.getBoundingClientRect = () => ({top: 100, bottom: 400, left: 0, right: 500, height: 300});
  d.querySelector('#dialog').getBoundingClientRect = () => ({top: 0, bottom: 600});
  Object.defineProperties(list, {scrollHeight: {value: 1200}, clientHeight: {value: 300}});
  list.scrollTop = 200;
  const rows = [...list.querySelectorAll('[data-order-index]')];
  rows.forEach((row, index) => row.getBoundingClientRect = () => ({top: 100 + index * 100 - list.scrollTop, bottom: 200 + index * 100 - list.scrollTop, height: 100}));
  d.elementFromPoint = (x, y) => rows[Math.floor((y - 100 + list.scrollTop) / 100)];
  const event = (type, target, y) => {
    const e = new w.Event(type, {bubbles: true, cancelable: true});
    Object.defineProperties(e, {clientX: {value: 200}, clientY: {value: y}, dataTransfer: {value: {setData() {}}}});
    target.dispatchEvent(e);
  };
  event('dragstart', rows[2], 110);event('dragover', rows[4], 399);
  step(0);const first = list.scrollTop;step(16);step(32);
  assert(first > 200 && list.scrollTop > first, 'Continue down without another mouse movement');
  assert(list.querySelector('.drop-before,.drop-after'), 'Update the insertion indicator while the rows scroll');
  event('dragover', rows[3], 250);step(48);
  const middle = list.scrollTop;step(64);
  assert.equal(list.scrollTop, middle, 'Stop when the mouse moves away from the edges');
  event('dragover', rows[2], 101);step(80);step(96);
  assert(list.scrollTop < middle, 'Scroll up while the mouse remains at the top');
  event('dragleave', list, 90);
  assert.equal(frames.size, 0, 'Cancel scrolling when the mouse leaves the list');
  event('dragover', rows[4], 399);step(112);
  d.querySelector('#dialog').close();const closed = list.scrollTop;step(128);
  assert.equal(list.scrollTop, closed, 'Do not scroll after the dialog closes');
  assert.equal(frames.size, 0);
});
