'use strict';
// 前端纯逻辑测试：node tests/test_teacher_demo_frontend_logic.cjs
// 覆盖事件仓库（去重、排序、缺口、跨运行拒绝）、场景示意数据与契约词表的一致性、格式化。
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const m = require(path.join(__dirname, '..', 'web', 'teacher-demo', 'app.js'));

const ev = (seq, extra = {}) => Object.assign({
  schema_version: 1, run_id: 'run-a', scenario_id: 'stolen-token', seq, event_id: 'e' + seq,
  source: 'live', status: 'passed', actor: 'gateway', target: null, event_type: 'check.passed', safe_payload: {},
}, extra);

// 1. 去重：同一 event_id 重复到达只记一次
{
  const s = new m.EventStore('run-a');
  assert.deepEqual(s.add([ev(1), ev(1), ev(2)]), {added: 2, duplicates: 1});
  assert.equal(s.ordered().length, 2);
}
// 2. 乱序到达：按 seq 排序；有缺口时只返回连续前缀，并报告缺口
{
  const s = new m.EventStore('run-a');
  s.add([ev(3), ev(1)]);
  assert.deepEqual(s.ordered().map(e => e.seq), [1]);
  assert.deepEqual(s.gaps(), [2]);
  assert.equal(s.nextAfterSeq(), 1);
  s.add([ev(2)]);
  assert.deepEqual(s.ordered().map(e => e.seq), [1, 2, 3]);
  assert.deepEqual(s.gaps(), []);
}
// 3. 其他运行的事件、字段不合格的事件一律拒收；同 seq 不同 id 记为冲突
{
  const s = new m.EventStore('run-a');
  s.add([ev(1, {run_id: 'run-b'}), ev(2, {source: 'guess'}), ev(3, {schema_version: 2}), ev(4, {actor: 'nobody'})]);
  assert.equal(s.ordered().length, 0);
  assert.equal(s.rejected.length, 4);
  s.add([ev(1), ev(1, {event_id: 'other'})]);
  assert.equal(s.conflicts.length, 1);
  assert.equal(s.ordered()[0].event_id, 'e1');
}
// 4. 场景示意数据：形状符合契约，来源全部标为 illustrative，seq 连续
for (const [id, sc] of Object.entries(m.SCENES)) {
  assert.ok(sc.events.length >= 5, id + ' 至少五步');
  sc.events.forEach((e, i) => {
    assert.deepEqual(m.eventProblems(e), [], `${id} 第 ${i + 1} 条事件形状`);
    assert.equal(e.source, 'illustrative', id + ' 示意数据必须标注为 illustrative');
    assert.equal(e.seq, i + 1);
    assert.ok(m.EVENT_TYPES.includes(e.event_type), id + ' 事件类型在词表内：' + e.event_type);
    const lane = k => sc.lanes.some(l => l.k === k);
    if (e.target) assert.ok(lane(e.target), `${id} target=${e.target} 必须有泳道`);
    if (e.actor && e.actor !== 'verifier') assert.ok(lane(e.actor) || (e.event_type === 'revocation.committed' && lane(e.target)), `${id} actor=${e.actor} 必须有泳道`);
    assert.ok(Array.isArray(sc.narrate(e, i, sc.events)), `${id} 第 ${i + 1} 步有讲解`);
    const text = JSON.stringify(e.safe_payload);
    assert.ok(!/eyJ[A-Za-z0-9_-]{8,}|-----BEGIN|PRIVATE KEY|postgres(ql)?:\/\//i.test(text), id + ' 示意数据不得含令牌、私钥或连接串');
  });
  if (id !== 's7') assert.ok(sc.events.some(e => e.status === 'rejected'), id + ' 必须有拒绝点');
  assert.ok(m.MODULES[sc.focus], id + ' 主角模块有说明');
  for (const l of sc.lanes) assert.ok(m.MODULES[l.k], `${id} 参与方 ${l.k} 有模块说明`);
}
// 5. 三个重点场景的拒绝位置：1 在网关，3 在 AS，6 在网关接受事务
assert.equal(m.SCENES.s1.events.find(e => e.status === 'rejected').actor, 'gateway');
assert.ok(m.SCENES.s3.events.filter(e => e.status === 'rejected').every(e => e.actor === 'as'));
assert.equal(m.SCENES.s6.events.find(e => e.status === 'rejected').safe_payload.check, 'ancestor_state');
// 场景 6：撤销提交必须排在被拒绝的接受之前，且拒绝事件的 cause_id 指向撤销
{
  const evs = m.SCENES.s6.events;
  const rev = evs.find(e => e.event_type === 'revocation.committed'), rej = evs.find(e => e.status === 'rejected');
  assert.ok(rev.seq < rej.seq);
  assert.equal(rej.cause_id, rev.event_id);
}
// 场景 7：恢复后只结算一次、只有一笔订单
{
  const rb = m.SCENES.s7.events.find(e => e.event_type === 'readback.state');
  const d = m.readbackDelta(rb.safe_payload);
  assert.equal(d.orders, 1);
  assert.equal(d.rootSettled, 70000);
}
// 门限面板：标为设计示意，没有对应的真实记录，必须出现"批准有效但撤销后仍拒绝"
assert.equal(m.SCENES.threshold.design, true);
assert.equal(m.SCENES.threshold.catalogId, null);
assert.ok(m.SCENES.threshold.events.some(e => e.event_type === 'accept.rejected' && e.safe_payload.check === 'ancestor_state'));
// "其余场景"四项各自对应目录里的真实用例
assert.deepEqual(m.MORE_SCENES.map(v => m.SCENES[v].catalogId), ['signed-parameters', 'shared-budget', 'replay-idempotency', 'recovery-evidence']);
// 场景 3 的金额沿用测试中的真实申请值 100001 分
assert.ok(m.SCENES.s3.events.some(e => e.safe_payload.observed === 100001));
// 6. 格式化与读回增量：缺字段时返回 null，不推算
assert.equal(m.fen(100001), '1,000.01 元');
assert.equal(m.fen(0), '0.00 元');
assert.equal(m.fen(undefined), '未采集');
assert.ok(Object.values(m.readbackDelta({})).every(v => v === null), '缺字段时全部为 null');
assert.equal(m.readbackDelta({orders_before: 1, orders_after: 1}).orders, 0);
// 7. 场景目录保持七项且 ID 不变
assert.deepEqual(m.CATALOG_FALLBACK.map(c => c.id), ['stolen-token', 'signed-parameters', 'delegation-scope', 'shared-budget', 'replay-idempotency', 'revocation', 'recovery-evidence']);
// 8. 静态页面符合服务端 CSP：没有内联脚本、内联样式或外部资源
{
  const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'teacher-demo', 'index.html'), 'utf8');
  assert.ok(!/<script(?![^>]*\bsrc=)[^>]*>/i.test(html), '不得有内联脚本');
  assert.ok(!/<style[\s>]/i.test(html), '不得有内联样式块');
  assert.ok(!/\sstyle=/i.test(html), '不得有 style 属性');
  assert.ok(!/(src|href)=["']https?:/i.test(html), '不得引用外部资源');
  const js = fs.readFileSync(path.join(__dirname, '..', 'web', 'teacher-demo', 'app.js'), 'utf8');
  assert.ok(!/innerHTML\s*=/.test(js), 'app.js 不使用 innerHTML 写入');
  assert.ok(!/localStorage|sessionStorage/.test(js), '不在浏览器存储任何数据');
}
console.log('teacher demo frontend logic: passed');

// B 的撤销锁等待必须保留连续游标，不能被前端拒收。
{
  const store = new m.EventStore('run-a');
  store.add([ev(1), ev(2, {event_type: 'lock.waiting', status: 'waiting'}), ev(3)]);
  assert.equal(store.rejected.length, 0);
  assert.equal(store.nextAfterSeq(), 3);
  assert.ok(m.SCENES.s1.narrate(ev(1, {event_type: 'accept.rejected'})));
}

// B7 saved summaries are never promoted to native jobs or live event frames.
{
  const js = fs.readFileSync(path.join(__dirname, '..', 'web', 'teacher-demo', 'app.js'), 'utf8');
  assert.ok(js.includes("title: '双域共签', action: 'cosm2-run'"));
  for (const name of ['cosign-valid-one-order', 'missing-approval', 'exec-domain-alone', 'tampered-amount', 'revoked-before-cosign', 'revoked-after-cosign']) assert.ok(js.includes("'" + name + "':"));
  assert.ok(js.includes("btn.disabled = !canAct() || (kind === 'cosign' && !ui.state?.cosign_ready)"));
  assert.ok(js.includes("start((kind === 'cosign' ? 'cosm2' : kind) + '/run')"));
  assert.ok(js.includes('单次运行，非统计结果'));
  assert.ok(js.includes('原 completed_at: ${demo.completed_at}'));
  assert.ok(js.includes("demo.source === 'current-run' ? '本次现场运行' : '保存结果回放'"));
  assert.ok(m.SCENES.cosign.events.every(e => e.source === 'illustrative'));
}
