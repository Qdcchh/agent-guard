'use strict';
const $ = id => document.getElementById(id);
let token = '', lastVerification = null, liveResult = null, busy = false;
let scenarioActionError = '';
let catalog = [], scenarioResults = {}, catalogKey = '', scenarioKey = '', latestJob = null;
let summaryKey, verificationKey, actionError = '', connectionError = '', connected = false;
const renderError = () => { $('error').textContent = actionError || connectionError; };
const text = (tag, content, className) => { const el = document.createElement(tag); el.textContent = content; if (className) el.className = className; return el; };
function renderSummary(result, live) {
  const key = JSON.stringify([result, live]);
  if (key === summaryKey) return;
  summaryKey = key;
  $('result-title').textContent = live ? '最近成功的现场运行' : '正常流程 · 运行记录回放';
  $('source-tag').textContent = live ? '现场运行' : '历史回放';
  const box = $('summary'); box.replaceChildren();
  if (!result) { $('run-id').textContent = '当前没有可读取的成功记录'; box.append(text('p', '请先启动一次真实演示；这里不会显示预设成功结果。', 'empty')); return; }
  $('run-id').textContent = '运行 ID · ' + result.run_id;
  const metrics = text('div', '', 'metrics');
  for (const [value, name] of [[result.counters[0][4] / 100 + ' 元', '根预算已结算'], [result.orders + ' 单', '模拟订单'], [result.notifications + ' 条', '固定模板通知']]) { const card = text('div', '', 'metric'); card.append(text('strong', value), text('span', name)); metrics.append(card); }
  box.append(metrics);
  const tools = text('div', '', 'tools');
  ['读取申请', '读取报价', '创建模拟订单', '发送模拟通知'].forEach((label, i) => { const row = text('div', '', 'tool'); row.append(text('span', (i + 1) + ' · ' + label), text('b', result.receipts[i])); tools.append(row); }); box.append(tools);
  result.counters.forEach((r, i) => { const row = text('div', '', 'budget-row'); row.append(text('span', ['统筹代理', '选品代理', '执行代理'][i] + ' · 额度 ' + r[1] / 100 + ' 元'), text('span', '结算 ' + r[4] / 100 + ' 元 · 预留 ' + r[3] / 100 + ' 元 · 调用 ' + r[6] + '/' + r[2])); box.append(row); });
  box.append(text('p', '本轮资源剩余 ' + result.resources_remaining + ' · 三代理独立身份 · 四次调用均已计账', 'resource'));
}
function renderVerification(result) {
  const key = JSON.stringify(result);
  if (key === verificationKey) return;
  verificationKey = key;
  const box = $('verification');
  const wasOpen = box.querySelector('details')?.open || false;
  box.replaceChildren();
  box.append(text('p', '最近一次现场验证 · ' + (result.run_id || '运行记录') + (result.verified_at ? ' · ' + new Date(result.verified_at * 1000).toLocaleTimeString('zh-CN') : ''), 'muted'));
  const row = text('div', '', 'verify-results');
  for (const [label, detail] of [[result.original.exit === 0 ? '原件通过' : '原件未通过', '真实退出码 ' + result.original.exit], [Number.isInteger(result.tampered.exit) ? (result.tampered.exit === 2 ? '篡改已拒绝' : result.tampered.exit === 0 ? '篡改未被拒绝' : '篡改验证执行异常') : '篡改结果未采集', '真实退出码 ' + result.tampered.exit]]) { const card = text('div', ''); card.append(text('strong', label), text('span', detail)); row.append(card); } box.append(row);
  const details = text('details', '', 'verify-boundaries'); details.open = wasOpen; details.append(text('summary', '查看本次证据验证边界'));
  const names = {cryptographic_consistency:'密码一致性',current_auth:'当前授权',downstream_truth:'下游真实性',freshness:'新鲜度来源',history_boundary:'历史边界',anchored_prefix:'已锚定前缀',cutoff_sequence:'截止序号',tail:'未锚定尾部'};
  for (const [k,v] of Object.entries(result.boundaries || {})) details.append(text('div', (names[k] || k) + '：' + v));
  details.append(text('p', '一致性通过只证明所提供证据与信任材料相符；当前授权仍未知，下游效果依赖见证，历史可能存在缺口。')); box.append(details);
}
async function refresh() {
  try {
    const response = await fetch('/api/state'); if (!response.ok) throw new Error('读取本机状态失败');
    const state = await response.json(), job = state.job;
    connectionError = ''; connected = true; renderError();
    if (job?.status === 'success' && job.action === 'run') liveResult = job.result;
    if (job?.status === 'success' && job.action === 'verify') lastVerification = job.result;
    // The server also keeps completed run results when a later verification starts.
    if (state.live) liveResult = state.live;
    if (state.verification) lastVerification = state.verification;
    renderSummary(liveResult || state.history, Boolean(liveResult));
    updateScenarios(state);
    latestJob = job; renderScenarioJob(job);
    busy = job?.status === 'running'; $('run').disabled = busy || !token; $('verify').disabled = busy || !token || !(liveResult || state.history);
    updateScenarioButtons();
    if (job) { const box = $('job'); box.replaceChildren(text('span', job.action === 'run' ? '现场运行' : job.action === 'verify' ? '现场离线验证' : job.action === 'scenario-run' ? '安全场景现场运行' : '安全场景记录回放', 'job-label')); box.append(text('p', job.stage, busy ? 'running' : '')); box.append(text('span', '已用 ' + Math.floor(job.elapsed / 60) + ' 分 ' + job.elapsed % 60 + ' 秒' + (busy ? ' · 页面刷新后可继续查看' : ''), 'elapsed')); if (busy && job.action === 'run') box.append(text('p', '完成后将自动显示新结果；收尾可能等待短期授权到期。', 'help')); }
    if (lastVerification) renderVerification(lastVerification);
  } catch (error) { connected = false; $('run').disabled = $('verify').disabled = $('scenario-run').disabled = $('scenario-replay').disabled = true; $('scenario-job').textContent = '连接已中断，无法获取当前场景进度；请恢复本机服务连接。'; connectionError = '无法连接本机服务；动作已暂停，现有内容仅为最后读取记录。'; renderError(); }
}
async function start(action) {
  if (busy || !connected || !token) return; busy = true; $('run').disabled = $('verify').disabled = $('scenario-run').disabled = $('scenario-replay').disabled = true; actionError = ''; scenarioActionError = ''; connectionError = ''; renderError();
  try { const response = await fetch('/api/' + action, {method:'POST', headers:{'Content-Type':'application/json','X-Demo-Token':token}, body:'{}'}); if (!response.ok) throw new Error(response.status === 409 ? '已有任务正在进行，或没有可验证的成功记录。' : '本次动作未获允许，请刷新页面后重试。'); }
  catch (error) { actionError = error.message; renderError(); if (action.startsWith('scenarios/')) scenarioActionError = error.message; }
  await refresh();
}
function renderScenarioJob(job) {
  const box = $('scenario-job');
  if (scenarioActionError) { box.textContent = '场景动作未启动：' + scenarioActionError; return; }
  if (!job?.scenario_id) { box.textContent = '尚未启动本次场景任务。'; return; }
  if (job.scenario_id !== $('scenario-select').value && job.status !== 'running') { box.className = 'scenario-progress'; box.textContent = scenarioResults[$('scenario-select').value] ? '当前所选场景的验证记录见下方；切换场景不会重新运行测试。' : '当前所选场景尚无读取结果。'; return; }
  const title = catalog.find(item => item.id === job.scenario_id)?.title || job.scenario_id;
  const status = {running:'正在进行',success:'已完成',failed:'执行失败',error:'执行异常'}[job.status] || '状态未确认';
  const elapsed = Number.isFinite(job.elapsed) ? Math.floor(job.elapsed / 60) + ' 分 ' + Math.floor(job.elapsed % 60) + ' 秒' : '未采集';
  box.className = 'scenario-progress' + (['failed', 'error'].includes(job.status) ? ' status-failed' : '');
  box.replaceChildren(text('strong', title + ' · ' + (job.action === 'scenario-replay' ? '记录回放' : '现场执行') + ' · ' + status), text('p', (job.stage || '进度未采集') + ' · 已用 ' + elapsed));
  if (job.status === 'failed' || job.status === 'error') box.append(text('p', '本次任务未成功。退出码：' + (job.native_exit ?? '未采集') + '；保留已有证据，不将其标为本次成功结果。'));
}
function updateScenarioButtons() {
  const item = catalog.find(x => x.id === $('scenario-select').value);
  $('scenario-run').disabled = busy || !connected || !token || !item?.run_available;
  $('scenario-replay').disabled = busy || !connected || !token || !item?.history_available;
}
function updateScenarios(state) {
  const next = state.catalog || [];
  const key = JSON.stringify(next);
  if (key !== catalogKey) {
    catalogKey = key; catalog = next;
    const selected = $('scenario-select').value;
    $('scenario-select').replaceChildren();
    for (const item of catalog) { const option = text('option', item.title); option.value = item.id; $('scenario-select').append(option); }
    if (catalog.some(x => x.id === selected)) $('scenario-select').value = selected;
    $('scenario-select').disabled = !catalog.length;
    if (!catalog.length) $('scenario-select').append(text('option', '场景目录尚未提供'));
  }
  scenarioResults = state.scenario_results || {};
  renderScenario();
}
function renderScenario() {
  const item = catalog.find(x => x.id === $('scenario-select').value);
  const result = item && scenarioResults[item.id];
  const key = JSON.stringify([item, result]);
  if (key === scenarioKey) return;
  scenarioKey = key;
  $('scenario-description').textContent = item ? '确定性安全请求实验。' + (item.run_available ? '可选择现场运行，或读取已保存证据。' : '此场景当前不提供现场运行；可用记录单独标示来源。') : '场景目录尚未提供。';
  $('scenario-source').textContent = result ? (result.mode === 'current_run' ? '现场执行结果' : result.mode === 'history_replay' ? '记录回放' : '来源未确认') : '尚未验证';
  const box = $('scenario-result'); box.replaceChildren();
  if (!item) { box.append(text('p', '尚无可读取的场景。', 'waiting')); return; }
  const grid = text('div', '', 'scenario-grid');
  const field = (title, value, wide = false) => { const el = text('section', '', 'scenario-field' + (wide ? ' wide' : '')); el.append(text('h3', title), text('p', value ?? '未采集')); grid.append(el); };
  field('请求 / 攻击条件', item.request);
  field('可信防线', item.defense);
  field('预期约束（不是本次观测）', item.expected);
  field('实际观测', result?.observed || '尚未验证；请运行场景或读取已有证据。');
  field('预算与业务效果', result?.budget == null ? '预算数值未采集。测试断言记录与现场预算读数分别展示，不推算业务效果。' : typeof result.budget === 'string' ? result.budget : JSON.stringify(result.budget));
  if (result) {
    const counts = ['passed', 'failed', 'skipped'].map(k => ({passed:'通过',failed:'失败',skipped:'跳过'}[k]) + ' ' + (Number.isInteger(result[k]) ? result[k] : '未采集')).join(' · ');
    field('执行断言记录', ({passed:'本组断言通过',failed:'本组存在失败',skipped:'本组已跳过'}[result.status] || '本组状态未确认') + '\n' + counts + '\n' + (result.checks || []).map(c => ({passed:'通过',failed:'失败',skipped:'跳过'}[c.status] || '状态未确认') + ' · ' + c.name).join('\n'), true);
    const evidence = result.evidence || {};
    field('证据来源', (result.source_label || '来源未采集') + '\n执行退出码：' + (evidence.native_exit ?? '未采集') + '\n证据摘要：' + (evidence.xml_sha256 || '未采集') + '\n快照校验：' + (evidence.snapshot_verified === true ? '已核验' : evidence.snapshot_verified === false ? '未通过' : '未采集'), true);
    box.append(text('p', '记录完成时间：' + (result.completed_at ? (typeof result.completed_at === 'number' ? new Date(result.completed_at * 1000) : new Date(result.completed_at)).toLocaleString('zh-CN') : '未采集') + '（' + (result.completed_at_basis || '记录时间') + '）。断言通过只适用于列出的用例与运行条件。', 'scenario-meta'));
  }
  box.append(grid);
}
async function startScenario(mode) {
  const item = catalog.find(x => x.id === $('scenario-select').value);
  if (!item || busy || !connected || !token) return;
  if (mode === 'run' ? !item.run_available : !item.history_available) return;
  await start('scenarios/' + encodeURIComponent(item.id) + '/' + mode);
}
$('scenario-select').addEventListener('change', () => { renderScenario(); renderScenarioJob(latestJob); updateScenarioButtons(); });
$('scenario-run').addEventListener('click', () => startScenario('run'));
$('scenario-replay').addEventListener('click', () => startScenario('replay'));
$('run').addEventListener('click', () => start('run')); $('verify').addEventListener('click', () => start('verify'));
fetch('/api/session').then(r => r.json()).then(s => { token = s.token; return refresh(); }).catch(() => { connectionError = '无法连接本机服务。'; renderError(); });
setInterval(refresh, 2000);
