'use strict';
/* Capture the actual UI. --live triggers exactly the fixed COSM2 button,
 * validates the real session result, and records its original source/time/id.
 * No responses or business results are injected. --record lasts >=180 seconds.
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {performance} = require('node:perf_hooks');

function options(argv) {
  const result = {url: null, out: null, record: false, live: false};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--url' || argv[i] === '--out') {
      const key = argv[i].slice(2);
      if (!argv[i + 1] || argv[i + 1].startsWith('--')) throw new Error('missing ' + key);
      result[key] = argv[++i];
    } else if (argv[i] === '--record') result.record = true;
    else if (argv[i] === '--live') result.live = true;
    else throw new Error('unknown argument ' + argv[i]);
  }
  if (!result.url || !result.out) throw new Error('usage: --url http://127.0.0.1:PORT --out NEW_DIRECTORY [--record] [--live]');
  const url = new URL(result.url);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || url.pathname !== '/' || url.search || url.hash || url.username || url.password) throw new Error('use the owned loopback demo server root');
  return result;
}
function playwright() {
  if (process.env.AG_COSM2_PLAYWRIGHT_MODULE) return require(process.env.AG_COSM2_PLAYWRIGHT_MODULE);
  return require('playwright');
}
async function main() {
  const opts = options(process.argv.slice(2));
  const out = path.resolve(opts.out);
  fs.mkdirSync(out, {recursive: false});
  const began = new Date().toISOString();
  const captures = [], errors = [], posts = [];
  let browser, context, video, liveResult = null;
  const started = performance.now();
  const chrome = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  try {
    browser = await playwright().chromium.launch({headless: true, ...(chrome ? {executablePath: chrome} : {})});
    context = await browser.newContext({viewport: {width: 1366, height: 768}, timezoneId: 'Asia/Shanghai', reducedMotion: 'reduce', ...(opts.record ? {recordVideo: {dir: path.join(out, 'video'), size: {width: 1366, height: 768}}} : {})});
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => {if (r.method() === 'POST') posts.push(new URL(r.url()).pathname);});
    await page.goto(opts.url);
    await page.waitForFunction(() => document.querySelector('#conn-line')?.textContent.includes('已连接') || document.querySelector('#source-text'));
    // Connection polling is asynchronous. Wait for the session GET/state GET to finish,
    // without substituting any response or manufacturing a successful result.
    await page.waitForTimeout(2500);
    async function chapter(view) {
      await page.locator('[data-view="' + view + '"]').click();
      await page.waitForTimeout(350);
      await page.locator('#brief').evaluate(el => {el.scrollTop = 0;});
    }
    async function shot(name, note) {
      const file = name + '.png';
      await page.screenshot({path: path.join(out, file), animations: 'disabled'});
      const source = await page.locator('#source-text').innerText();
      const bytes = fs.readFileSync(path.join(out, file));
      captures.push({file, view: await page.evaluate(() => location.hash.slice(1)), source, note, captured_at: new Date().toISOString(), sha256: crypto.createHash('sha256').update(bytes).digest('hex')});
    }
    async function hold(seconds) {if (opts.record) await page.waitForTimeout(seconds * 1000);}
    await chapter('overview'); await shot('overview', 'System model; no execution claim'); await hold(8);
    for (const [view, scene] of [['s1', 'stolen-token'], ['s3', 'delegation-scope'], ['s6', 'revocation']]) {
      await chapter(view);
      const replay = page.locator('#proof button').filter({hasText: '读取记录'});
      let replayStatus = 'unavailable';
      if (await replay.count() && await replay.isEnabled()) {
        await replay.click();
        await page.waitForFunction(id => {
          const box = document.querySelector('#proof');
          return box && (box.textContent.includes('断言通过') || box.textContent.includes('断言失败') || box.textContent.includes('未成功'));
        }, scene, {timeout: 30000});
        replayStatus = 'read actual saved record; diagram source is recorded separately';
      }
      const buttons = page.locator('#count button.seg');
      const n = await buttons.count();
      if (n) await buttons.nth(n - 1).click();
      await page.waitForTimeout(350);
      await shot(view, replayStatus); await hold(8);
    }
    await chapter('cosign'); await shot('cosign-illustrative', 'Right A2/A5 diagram is illustrative; actual results are shown separately');
    await page.locator('#proof').scrollIntoViewIfNeeded();
    await shot('cosign-saved-result', 'Existing B7 summary retains its actual server session source label');
    const steps = await page.locator('#count button.seg').count();
    for (let i = 0; i < steps; i++) {await page.locator('#count button.seg').nth(i).click(); await hold(1);}
    await page.waitForTimeout(350); await shot('cosign-authz-refusal-illustrative', 'Illustrative AUTHZ_REVOKED; no actual COSM2 refusal recorded');
    if (opts.live) {
      await chapter('cosign');
      const runButton = page.locator('#proof button').filter({hasText: /现场运行|重新运行/});
      if (await runButton.count() !== 1 || !await runButton.isEnabled()) throw new Error('COSM2 live launcher is not ready');
      const previous = await page.evaluate(async () => (await fetch('/api/state')).json());
      await runButton.click();
      // Poll actual fetched values in Node. The bundled browser helper may
      // treat a Promise-returning waitForFunction predicate as immediately true.
      const deadline = performance.now() + 900000;
      let state;
      while (performance.now() < deadline) {
        state = await page.evaluate(async () => (await fetch('/api/state')).json());
        if (state.job?.id !== previous.job?.id && state.job?.action === 'cosm2-run' && state.job.status !== 'running') break;
        await page.waitForTimeout(300);
      }
      fs.writeFileSync(path.join(out, 'live-terminal-state.json'), JSON.stringify(state, null, 2) + '\n');
      if (state.job?.status !== 'success' || state.job.native_exit !== 0 || state.job.actual_wait !== true || state.cosign?.source !== 'current-run' || !state.cosign.passed || state.job.result?.run_id !== state.cosign.run_id) throw new Error('COSM2 live run failed; actual terminal state retained');
      liveResult = {run_id: state.cosign.run_id, completed_at: state.cosign.completed_at, source: state.cosign.source, source_label: state.cosign.source_label, timing_ms: state.cosign.timing_ms};
      await page.waitForFunction(id => document.querySelector('#proof')?.textContent.includes(id), liveResult.run_id);
      await page.locator('#proof').scrollIntoViewIfNeeded();
      await shot('cosign-live', 'Actual button-triggered six-case COSM2 run; right diagram remains illustrative'); await hold(20);
    }
    await chapter('evidence'); await shot('records', 'Actual saved records, with page source labels; no live-run action invoked');
    const details = page.locator('#records button.rec-more');
    if (await details.count()) {await details.first().click(); await page.waitForTimeout(350); await shot('records-detail', 'Saved record date/source and assertion evidence'); await hold(20);}
    const fullRun = page.locator('#records section').filter({has: page.locator('h3').filter({hasText: '完整采购流程'})});
    if (await fullRun.count()) {await fullRun.scrollIntoViewIfNeeded(); await page.waitForTimeout(350); await shot('records-full-procurement', 'Historical procurement run ID, not a COSM2 run');}
    if (opts.record) {
      if (liveResult) {await chapter('cosign'); await page.locator('#proof').scrollIntoViewIfNeeded();}
      const remaining = Math.max(0, 184000 - (performance.now() - started));
      if (remaining) await page.waitForTimeout(remaining);
      video = page.video();
    }
    if (errors.length) throw new Error('page errors: ' + errors.join('; '));
    if (posts.some(p => !/^\/api\/scenarios\/(stolen-token|delegation-scope|revocation)\/replay$/.test(p) && !(opts.live && p === '/api/cosm2/run'))) throw new Error('unexpected business action invoked');
    const report = {schema_version: 1, captured_at: began, completed_at: new Date().toISOString(), timezone: 'Asia/Shanghai', viewport: {width: 1366, height: 768}, kind: opts.live ? 'actual-cosm2-live-and-replay-tour' : opts.record ? 'historical-record-and-illustrative-ui-tour' : 'screenshots', cosign_live: liveResult ? {status: 'PASSED', ...liveResult} : {status: 'NOT_REQUESTED', reason: 'Use --live to trigger a real fixed run'}, captures, posts, page_errors: errors};
    await context.close(); context = null;
    if (video) {
      const original = await video.path();
      const target = path.join(out, opts.live ? 'cosm2-live-tour.webm' : 'replay-and-illustrative-tour.webm');
      fs.renameSync(original, target);
      report.video = {file: path.basename(target), description: opts.live ? 'Actual button-triggered COSM2 run, saved records and explicitly illustrative right diagram' : 'Actual browser recording of historical records and illustrative scenes; not a COSM2 live run', wall_elapsed_seconds: (performance.now() - started) / 1000, sha256: crypto.createHash('sha256').update(fs.readFileSync(target)).digest('hex')};
    }
    fs.writeFileSync(path.join(out, 'capture-manifest.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify({status: 'CAPTURED_AVAILABLE_VIEWS', screenshots: captures.length, recording: !!video, cosign_live: liveResult ? 'PASSED' : 'NOT_REQUESTED', manifest: path.join(out, 'capture-manifest.json')}));
  } finally {if (context) await context.close(); if (browser) await browser.close();}
}
main().catch(error => {console.error(error.message); process.exitCode = 1;});
