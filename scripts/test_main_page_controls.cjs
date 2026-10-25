// End-to-end DOM/API checks in a disposable website; no browser or live-site writes.
// node --test scripts/test_main_page_controls.cjs
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const root = path.resolve(__dirname, '..');
const {JSDOM} = require(path.join(root, '.site-manager/ui-tests/node_modules/jsdom'));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check) {
  for (let i = 0; i < 500; i++) {if (check()) return;await pause(10);}
  throw new Error('Timed out waiting for manager controls');
}

test('Main-page controls create a menu page, delete it, undo deletion, and offer its category to detail pages', async t => {
  const python = `
from http.server import ThreadingHTTPServer
from pathlib import Path
import secrets, shutil, sys, tempfile
sys.path.insert(0, str(Path.cwd() / 'scripts'))
from manage_site import Handler, SiteManager
with tempfile.TemporaryDirectory(prefix='main-page-controls-') as directory:
 root = Path(directory)
 for item in (Path.cwd() / 'pages').glob('*.html'): shutil.copy2(item, root / item.name)
 for name in ['_config.yml', '.gitignore']: shutil.copy2(name, root / name)
 shutil.copytree('_data', root / '_data')
 server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
 origin = 'http://127.0.0.1:' + str(server.server_port)
 server.manager = SiteManager(root, origin)
 server.manager.start_build = lambda: None
 server.token = secrets.token_hex(32)
 print(origin, flush=True)
 try: server.serve_forever()
 except KeyboardInterrupt: pass
 finally: server.server_close()
`;
  const server = spawn('python3', ['-u', '-c', python], {cwd: root, stdio: ['ignore', 'pipe', 'pipe']});
  let output = '', errors = '';
  server.stdout.on('data', data => output += data);server.stderr.on('data', data => errors += data);
  t.after(async () => {server.kill('SIGINT');await new Promise(resolve => server.once('exit', resolve));});
  await until(() => output.includes('\n') || server.exitCode !== null);
  assert.equal(server.exitCode, null, errors);
  const origin = output.trim();
  const html = await (await fetch(origin + '/__manager/')).text();
  const dom = new JSDOM(html, {url: origin + '/__manager/', runScripts: 'outside-only', pretendToBeVisual: true});
  t.after(() => dom.window.close());
  const w = dom.window, d = w.document;
  w.scrollTo = () => {};
  w.HTMLDialogElement.prototype.showModal = function() {this.setAttribute('open', '');};
  w.HTMLDialogElement.prototype.close = function() {this.removeAttribute('open');};
  w.fetch = (url, options = {}) => fetch(new URL(url, origin), {...options, headers: {...options.headers, ...(options.method === 'POST' ? {Origin: origin} : {})}});
  for (const name of ['app.js', 'media.js', 'descriptions.js', 'storage.js', 'sections.js', 'help.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, 'site_manager', name), 'utf8'), dom.getInternalVMContext());
  }
  await until(() => d.querySelector('#new-page'));
  assert.equal(d.querySelector('#new-main-page'), null, 'One New page button serves both page kinds');
  for (const id of ['blog.html', 'my-creativity.html', 'about.html']) assert(d.querySelector('[data-select="'+id+'"]'));
  assert.equal(d.querySelector('[data-select="index.html"]'), null);
  d.querySelector('#new-page').click();
  d.querySelector('#new-page-kind').value='main';d.querySelector('#continue-new-page').click();
  const form = d.querySelector('#main-page-form');
  form.elements.title.value = 'UI Adventures';form.elements.title.dispatchEvent(new w.Event('input'));
  assert.equal(form.elements.slug.value, 'ui-adventures');
  form.elements.description.value = 'Memories from travels.';form.elements.section_title.value = 'Trip memories';
  form.dispatchEvent(new w.Event('submit', {bubbles: true, cancelable: true}));
  await until(() => d.querySelector('#section-page')?.value === 'ui-adventures.html');
  assert.equal(d.querySelector('#dialog').open, false);
  assert.equal(d.querySelector('#delete-main-page'), null, 'Use the shared Delete selected flow');
  const page = await w.api('page?id=ui-adventures.html');
  assert(page.main_page && page.protected);
  d.querySelector('[data-view="pages"]').click();
  d.querySelector('[data-edit="ui-adventures.html"]').click();
  await until(() => d.querySelector('#page-form'));
  assert.equal(d.querySelector('#page-form').elements.title.value, 'UI Adventures');
  d.querySelector('#cancel-edit').click();
  const checkbox = d.querySelector('[data-select="ui-adventures.html"]');
  checkbox.checked = true;checkbox.dispatchEvent(new w.Event('change'));
  const detailCheckbox = d.querySelector('[data-select="deepaboli-2025.html"]');
  detailCheckbox.checked = true;detailCheckbox.dispatchEvent(new w.Event('change'));
  d.querySelector('#delete-selected').click();
  await until(() => d.querySelector('#delete-pages-form'));
  const deletion = d.querySelector('#delete-pages-form');
  assert(![...deletion.querySelector('[data-replacement]').options].some(option => option.value === '/ui-adventures.html'));
  assert.equal(deletion.querySelector('[data-delete-tiles]').value, 'move');
  assert.equal(deletion.querySelectorAll('[data-delete-tiles]').length, 1, 'Only the main page needs a section disposition');
  assert.equal(deletion.querySelectorAll('[data-replacement]').length, 2);
  deletion.querySelector('[data-replacement="1"]').value = '/deepaboli-2024.html';
  deletion.dispatchEvent(new w.Event('submit', {bubbles: true, cancelable: true}));
  await until(() => !d.querySelector('#dialog').open && d.querySelector('#new-page') && !d.querySelector('[data-select="ui-adventures.html"]'));
  assert(!d.querySelector('[data-select="ui-adventures.html"]'));
  assert(!d.querySelector('[data-select="deepaboli-2025.html"]'));
  assert(!d.querySelector('[data-select="index.html"]'), 'The homepage stays required');
  d.querySelector('[data-view="history"]').click();
  const undo = d.querySelector('[data-undo]'), undoId = undo.dataset.undo;undo.click();
  await until(() => d.querySelector('[data-undo]')?.dataset.undo !== undoId);
  const state = await w.api('state');
  assert(state.section_pages.some(page => page.id === 'ui-adventures.html'));
  assert(state.pages.some(page => page.id === 'deepaboli-2025.html'), 'One Undo restores both page kinds');
  d.querySelector('[data-view="pages"]').click();d.querySelector('#new-page').click();
  assert.equal(d.querySelector('#new-page-kind').value, 'detail');d.querySelector('#continue-new-page').click();
  await until(() => d.querySelector('#page-form'));
  assert([...d.querySelector('#page-form').elements.section.options].some(option => option.textContent === 'UI Adventures'));
  assert([...d.querySelector('#page-form').elements.tile_group.options].some(option => option.textContent.includes('UI Adventures / Trip memories')));
});
