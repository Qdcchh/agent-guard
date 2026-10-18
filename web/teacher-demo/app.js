'use strict';
/*
 * Agent Guard 演示页
 *
 * 第一部分是纯逻辑（事件仓库、场景数据、格式化），不依赖浏览器，可在 node 中测试。
 * 第二部分是界面：系统总览、场景时序图、门限面板、真实记录，以及与本机服务的交互。
 *
 * 诚实性约定：
 * - 场景时序图默认使用"示意推演"事件，形状与 DemoEvent v1 一致，页面醒目标注来源；
 *   本机服务提供某次运行的事件流后，同一渲染器直接改用真实事件，并标为现场或回放。
 * - 真实运行结果只来自本机服务；不根据计时器生成任何成功或拒绝。
 * - 浏览器不持有令牌、私钥或任何可用凭据。
 */

/* ======================================================================
 * 第一部分：纯逻辑
 * ==================================================================== */

const SCHEMA_VERSION = 1;
const ACTORS = ['user', 'planner', 'selector', 'executor', 'executor-2', 'attacker', 'as', 'gateway',
  'ledger', 'downstream', 'audit', 'verifier', 'worker', 'recovery', 'coordinator',
  'exec-domain', 'authz-domain', 'signer-1', 'signer-2', 'signer-3', 'x402', 'model', 'resource', 'chain'];
const EVENT_TYPES = ['fixture.setup', 'token.issued', 'delegation.requested', 'delegation.issued',
  'delegation.rejected', 'request.sent', 'check.passed', 'check.rejected', 'lock.waiting',
  'revocation.committed', 'accept.committed', 'accept.rejected', 'process.crashed',
  'operation.reconciled', 'receipt.published', 'readback.state', 'run.terminal', 'run.error',
  'threshold.share_signed', 'threshold.aggregated', 'threshold.verified', 'intent.proposed',
  'cosign.round1', 'cosign.checked', 'cosign.refused', 'cosign.partial', 'cosign.combined'];
const STATUSES = ['pending', 'in_progress', 'waiting', 'passed', 'rejected', 'failed', 'unknown', 'skipped'];
const SOURCES = ['live', 'replay', 'illustrative'];
const NOT_DRAWN = new Set(['run.terminal']);

/** 检查一条事件是否满足前端需要的最小形状；返回问题列表，空数组表示可用。 */
function eventProblems(ev) {
  const p = [];
  if (!ev || typeof ev !== 'object') return ['不是对象'];
  if (ev.schema_version !== SCHEMA_VERSION) p.push('schema_version');
  if (typeof ev.run_id !== 'string' || !ev.run_id) p.push('run_id');
  if (!Number.isInteger(ev.seq) || ev.seq < 1) p.push('seq');
  if (typeof ev.event_id !== 'string' || !ev.event_id) p.push('event_id');
  if (!SOURCES.includes(ev.source)) p.push('source');
  if (!STATUSES.includes(ev.status)) p.push('status');
  if (ev.actor != null && !ACTORS.includes(ev.actor)) p.push('actor');
  if (ev.target != null && !ACTORS.includes(ev.target)) p.push('target');
  return p;
}

/**
 * 事件仓库：只按 seq 排序、按 event_id 去重；不信任到达顺序与时间戳。
 * ordered() 只返回从 seq=1 开始连续的部分，遇到缺口就停，等待补拉。
 */
class EventStore {
  constructor(runId) {
    this.runId = runId;
    this.byId = new Map();
    this.bySeq = new Map();
    this.maxSeq = 0;
    this.conflicts = [];
    this.rejected = [];
  }
  add(events) {
    let added = 0, duplicates = 0;
    for (const ev of events || []) {
      const problems = eventProblems(ev);
      if (problems.length || ev.run_id !== this.runId) { this.rejected.push({ev, problems}); continue; }
      if (this.byId.has(ev.event_id)) { duplicates++; continue; }
      const other = this.bySeq.get(ev.seq);
      if (other) { this.conflicts.push({seq: ev.seq, kept: other.event_id, dropped: ev.event_id}); continue; }
      this.byId.set(ev.event_id, ev);
      this.bySeq.set(ev.seq, ev);
      this.maxSeq = Math.max(this.maxSeq, ev.seq);
      added++;
    }
    return {added, duplicates};
  }
  ordered() {
    const out = [];
    for (let s = 1; this.bySeq.has(s); s++) out.push(this.bySeq.get(s));
    return out;
  }
  gaps() {
    const missing = [];
    for (let s = 1; s <= this.maxSeq; s++) if (!this.bySeq.has(s)) missing.push(s);
    return missing;
  }
  nextAfterSeq() { return this.ordered().length; }
}

/** 整数分 → "1,000.00 元" */
function fen(n) {
  if (!Number.isInteger(n)) return '未采集';
  const sign = n < 0 ? '-' : '';
  const a = Math.abs(n), yuan = Math.floor(a / 100), cents = String(a % 100).padStart(2, '0');
  return sign + yuan.toLocaleString('en-US') + '.' + cents + ' 元';
}

/** 读回前后的增量；字段缺失时返回 null，绝不推算。 */
function readbackDelta(p) {
  const sum = (arr, k) => Array.isArray(arr) && arr.every(r => r && Number.isInteger(r[k]))
    ? arr.reduce((s, r) => s + r[k], 0) : null;
  const diff = (a, b) => (a == null || b == null) ? null : b - a;
  const int = v => Number.isInteger(v) ? v : null;
  const root = (arr, k) => Array.isArray(arr) && arr[0] && Number.isInteger(arr[0][k]) ? arr[0][k] : null;
  return {
    reserved: diff(sum(p.budget_before, 'reserved_fen'), sum(p.budget_after, 'reserved_fen')),
    settled: diff(sum(p.budget_before, 'settled_fen'), sum(p.budget_after, 'settled_fen')),
    rootReserved: diff(root(p.budget_before, 'reserved_fen'), root(p.budget_after, 'reserved_fen')),
    rootSettled: diff(root(p.budget_before, 'settled_fen'), root(p.budget_after, 'settled_fen')),
    orders: diff(int(p.orders_before), int(p.orders_after)),
    grants: diff(int(p.grants_before), int(p.grants_after)),
  };
}

/* ---------------- 场景数据（示意推演，形状与 DemoEvent v1 一致） ---------------- */

const TOOLS = ['procurement.order.create', 'notification.template.send'];
const levels = (reserved, settled) => [0, 0, 0].map(() => ({reserved_fen: reserved, settled_fen: settled, calls: 0}));

function illustrative(scene, list) {
  return list.map((e, i) => Object.assign({
    schema_version: SCHEMA_VERSION,
    run_id: 'illustrative-' + scene,
    scenario_id: scene,
    seq: i + 1,
    event_id: scene + '-e' + (i + 1),
    cause_id: null,
    source: 'illustrative',
    actor: null,
    target: null,
    stage: null,
    status: 'passed',
    reason_code: null,
    observed_at: null,
    monotonic_ms: null,
    safe_payload: {},
    evidence_ref: null,
  }, e));
}

const INVOKE = 'POST /v1/invocations';

const SCENES = {
  s1: {
    catalogId: 'stolen-token', short: '持有者绑定',
    title: '盗取令牌，却没有私钥',
    lede: '冒用方复制了执行代理的访问令牌，但签名私钥仍在执行代理手里。它能用这张令牌下单吗？',
    stack: [
      ['授权框架', 'OAuth 2.0；逐级委托用 Token Exchange ', 'RFC 8693'],
      ['持有证明', 'AGPoP，参照 DPoP ', 'RFC 9449', ' 的发送者约束思路'],
      ['密码算法', 'SM2 签名，SM3 摘要，配置名 ', 'GM-MVP-1'],
    ],
    delta: [
      ['Bearer', '谁拿到令牌谁就能用。令牌一旦被复制，冒用请求会被接受。'],
      ['DPoP', '令牌绑定客户端密钥，但默认不签请求体，摘要固定为 SHA-256。'],
      ['AGPoP', '令牌用 ag_cnf 绑定持有者公钥；每次请求另附 AG-Proof，用持有者私钥签名，并以 SM3 绑定令牌与完整请求体。', true],
    ],
    honest: '发送者约束是已有标准方向，本项目不声称首创，也不与标准 DPoP 互通；增量在于把它和委托收窄、接受时动态检查放进同一条执行路径。',
    band: [300, 770], focus: 'gateway',
    lanes: [
      {k: 'executor', x: 76, name: '执行代理', id: 'executor#key-1', tone: 'teal'},
      {k: 'attacker', x: 218, name: '冒用方', id: '持 planner#key-1', tone: 'violet'},
      {k: 'as', x: 370, name: '授权服务器', id: 'AS'},
      {k: 'gateway', x: 540, name: '执行网关', id: '/v1/invocations'},
      {k: 'ledger', x: 700, name: '授权与预算库', id: '接受事务'},
      {k: 'downstream', x: 840, name: '模拟订单', id: '下游服务'},
    ],
    checkNote: {token_signature: '只验 Bearer 令牌时，请求到这里已被接受'},
    readbackSkip: ['gateway', 'downstream', '未进入接受事务，未转发下游'],
    events: illustrative('s1', [
      {event_type: 'token.issued', actor: 'as', target: 'executor',
        safe_payload: {grant_alias: 'leaf', parent_alias: 'mid', holder: 'executor', holder_kid: 'executor#key-1', limits: {amount_fen: 70000, calls: 8}, scope: TOOLS}},
      {event_type: 'fixture.setup', actor: 'executor', target: 'attacker', safe_payload: {kind: 'copy-token', token_holder: 'executor'}},
      {event_type: 'request.sent', actor: 'attacker', target: 'gateway',
        safe_payload: {endpoint: INVOKE, token_holder: 'executor', proof_signer_kid: 'planner#key-1', tool_id: TOOLS[0]}},
      {event_type: 'check.passed', actor: 'gateway', safe_payload: {check: 'token_signature'}},
      {event_type: 'check.rejected', actor: 'gateway', status: 'rejected', reason_code: 'HOLDER_MISMATCH',
        safe_payload: {check: 'holder_binding', expected: 'executor#key-1', observed: 'planner#key-1', http_status: 401}},
      {event_type: 'readback.state', actor: 'verifier',
        safe_payload: {budget_before: levels(0, 0), budget_after: levels(0, 0), orders_before: 0, orders_after: 0}},
    ]),
    narrate(ev) {
      switch (ev.event_type) {
        case 'token.issued': return ['AS 签发令牌', '令牌写明持有者是执行代理，并用 ag_cnf 绑定它的公钥。'];
        case 'fixture.setup': return ['令牌副本被窃取', '令牌是一串数据，可以被复制；私钥没有随它离开执行代理。'];
        case 'request.sent': return ['冒用方发起工具调用', '令牌是真的，证明却只能用冒用方手里的 planner 私钥来签。'];
        case 'check.passed': return ['令牌本身验签通过', 'AS 的 SM2 签名有效。只验 Bearer 令牌的系统，到这里已经放行。'];
        case 'accept.rejected': return ['网关拒绝冒用请求', `真实请求返回 ${ev.safe_payload.http_status ?? '未采集'}；原因：${ev.reason_code || '未采集'}。`];
        case 'check.rejected': return ['持有者对不上，网关驳回', 'ag_cnf 指向 executor#key-1，AG-Proof 却由 planner#key-1 签出。拿到令牌，不等于拿到权限。'];
        case 'readback.state': return ['业务没有任何变化', '请求没有进入接受事务，预算没有新预留，下游没有新订单。'];
      }
      return null;
    },
  },

  s2: {
    catalogId: 'signed-parameters', short: '参数篡改',
    title: '签名之后，参数被改了',
    lede: '执行代理签好了请求，途中有人把收货地址改掉。签名者是真的，令牌也是真的，网关会接受吗？',
    stack: [
      ['持有证明', 'AG-Proof 绑定 htm、htu、token_sm3 与 body_sm3'],
      ['规范编码', '请求体按 ', 'RFC 8785', ' 规范化后取 SM3 摘要'],
      ['密码算法', 'SM2 签名，SM3 摘要，配置名 ', 'GM-MVP-1'],
    ],
    delta: [
      ['DPoP', '证明绑定 HTTP 方法、URL 与令牌哈希，默认不覆盖请求体。'],
      ['只签路径', '同一路径下改数量、改地址、改幂等键，签名依然成立。'],
      ['AGPoP', '工具、版本、全部参数、任务 ID 与幂等键都在被签名的请求体里，改动任何一处，摘要就对不上。', true],
    ],
    honest: '签名只证明请求没有被改过，不证明参数本身合理；参数是否在授权范围内由后续检查负责。同一组测试还覆盖了篡改幂等键。',
    band: [300, 770], focus: 'gateway',
    lanes: [
      {k: 'executor', x: 76, name: '执行代理', id: 'executor#key-1', tone: 'teal'},
      {k: 'attacker', x: 218, name: '中途篡改', id: '测试注入', tone: 'violet'},
      {k: 'gateway', x: 450, name: '执行网关', id: '/v1/invocations'},
      {k: 'ledger', x: 650, name: '授权与预算库', id: '接受事务'},
      {k: 'downstream', x: 830, name: '模拟订单', id: '下游服务'},
    ],
    checkNote: {holder_binding: '签名者是真的，但请求已经不是签名时那一份'},
    readbackSkip: ['gateway', 'downstream', '未进入接受事务，未转发下游'],
    events: illustrative('s2', [
      {event_type: 'fixture.setup', actor: 'executor', target: 'attacker',
        safe_payload: {kind: 'signed-request', field: 'params.delivery_id', value: 'office-001'}},
      {event_type: 'request.sent', actor: 'attacker', target: 'gateway',
        safe_payload: {endpoint: INVOKE, token_holder: 'executor', proof_signer_kid: 'executor#key-1', tool_id: TOOLS[0], tampered: 'params.delivery_id: office-001 → changed'}},
      {event_type: 'check.passed', actor: 'gateway', safe_payload: {check: 'holder_binding'}},
      {event_type: 'check.rejected', actor: 'gateway', status: 'rejected', reason_code: 'INVALID_SIGNATURE',
        safe_payload: {check: 'request_binding', expected: 'delivery_id = office-001', observed: 'delivery_id = changed', http_status: 401}},
      {event_type: 'readback.state', actor: 'verifier',
        safe_payload: {budget_before: levels(0, 0), budget_after: levels(0, 0), orders_before: 0, orders_after: 0}},
    ]),
    narrate(ev) {
      switch (ev.event_type) {
        case 'fixture.setup': return ['执行代理签好请求', 'AG-Proof 里的 body_sm3 是对整份请求体的摘要，收货地址是 office-001。'];
        case 'request.sent': return ['请求在途中被改', '收货地址被改成 changed，令牌和证明原样转发。'];
        case 'check.passed': return ['签名者和持有者都对得上', '令牌与证明确实来自执行代理，单看身份挑不出问题。'];
        case 'check.rejected': return ['摘要对不上，网关驳回', '网关按收到的请求体重新计算 body_sm3，与证明里签过的值不一致。'];
        case 'readback.state': return ['业务没有任何变化', '被改过的请求没有进入接受事务，也没有到达下游。'];
      }
      return null;
    },
  },

  s3: {
    catalogId: 'delegation-scope', short: '委托收窄',
    title: '委托不得扩权',
    lede: '统筹代理给选品代理申请子授权时，多要了一点：金额多 0.01 元，或者多一个工具。授权服务器会签吗？',
    stack: [
      ['委托协议', 'OAuth 2.0 Token Exchange ', 'RFC 8693'],
      ['委托申请', '父持有者用 AG-Proof 签名，purpose=delegate'],
      ['签发者', '各级令牌统一由 AS 签发，SM2 签名'],
    ],
    delta: [
      ['RFC 8693', '规定了怎样用一张令牌换另一张，但不自动保证权限收窄，也不管祖先撤销与共享预算。'],
      ['父代理自签', '早期草案由父代理直接签子凭证，系统难以统一检查。'],
      ['本项目', 'AS 逐维检查金额、次数、期限、深度、工具、受众、接收方与资源，子授权必须包含于父授权，任一维超出即拒绝。', true],
    ],
    honest: 'Token Exchange 是标准协议；收窄规则和持久授权树是本项目在应用层补充的约束。示意把 amount 与 scope 两个测试用例放在同一条时间线上。',
    band: [392, 890], focus: 'as',
    lanes: [
      {k: 'planner', x: 90, name: '统筹代理', id: 'planner#key-1', tone: 'violet'},
      {k: 'selector', x: 250, name: '选品代理', id: 'selector#key-1', tone: 'teal'},
      {k: 'as', x: 500, name: '授权服务器', id: 'POST /oauth/token'},
      {k: 'gateway', x: 680, name: '执行网关', id: '/v1/invocations'},
      {k: 'ledger', x: 830, name: '授权注册表', id: '授权树'},
    ],
    checkNote: {},
    readbackExtra: [['gateway', '未收到任何请求', 'lab mute']],
    events: illustrative('s3', [
      {event_type: 'delegation.requested', actor: 'planner', target: 'as',
        safe_payload: {target_holder: 'selector', parent_alias: 'root', parent_limits: {amount_fen: 100000}, requested_limits: {amount_fen: 80000}, parent_scope: TOOLS, requested_scope: TOOLS}},
      {event_type: 'delegation.issued', actor: 'as', target: 'selector',
        safe_payload: {grant_alias: 'mid', parent_alias: 'root', holder: 'selector', holder_kid: 'selector#key-1', limits: {amount_fen: 80000}}},
      {event_type: 'delegation.requested', actor: 'planner', target: 'as',
        safe_payload: {target_holder: 'selector', parent_alias: 'root', parent_limits: {amount_fen: 100000}, requested_limits: {amount_fen: 100001}, parent_scope: TOOLS, requested_scope: TOOLS}},
      {event_type: 'delegation.rejected', actor: 'as', status: 'rejected', reason_code: 'DELEGATION_EXPANSION',
        safe_payload: {check: 'delegation_narrowing', dimension: 'amount', expected: 100000, observed: 100001, http_status: 400}},
      {event_type: 'delegation.requested', actor: 'planner', target: 'as',
        safe_payload: {target_holder: 'selector', parent_alias: 'root', parent_limits: {amount_fen: 100000}, requested_limits: {amount_fen: 80000}, parent_scope: TOOLS, requested_scope: TOOLS.concat('unauthorized.tool')}},
      {event_type: 'delegation.rejected', actor: 'as', status: 'rejected', reason_code: 'DELEGATION_EXPANSION',
        safe_payload: {check: 'delegation_narrowing', dimension: 'scope', expected: TOOLS, observed: TOOLS.concat('unauthorized.tool'), http_status: 400}},
      {event_type: 'readback.state', actor: 'verifier', safe_payload: {grants_before: 2, grants_after: 2, orders_before: 0, orders_after: 0}},
    ]),
    narrate(ev) {
      const p = ev.safe_payload || {};
      switch (ev.event_type) {
        case 'delegation.requested': {
          const rq = p.requested_limits || {}, pr = p.parent_limits || {};
          if ((p.requested_scope || []).length > (p.parent_scope || []).length) return ['多申请一个工具', '申请的工具集合里多了 unauthorized.tool，父授权里没有它。'];
          if (rq.amount_fen > pr.amount_fen) return ['多申请 0.01 元', '父授权上限 ' + fen(pr.amount_fen) + '，这次申请 ' + fen(rq.amount_fen) + '。'];
          return ['合法的委托申请', '统筹代理为选品代理申请 ' + fen(rq.amount_fen) + '，在父授权 ' + fen(pr.amount_fen) + ' 之内。'];
        }
        case 'delegation.issued': return ['AS 签发子令牌', '子令牌的持有者是选品代理，父授权指向 root。签发不等于花钱，子额度和父额度共享同一笔预算。'];
        case 'delegation.rejected':
          return p.dimension === 'scope'
            ? ['工具超出父授权，AS 拒绝', '集合必须包含于父授权；多出的工具不会被签进任何令牌。']
            : ['金额超出父授权，AS 拒绝', '哪怕只多 0.01 元也不签发。拒绝发生在 AS，网关根本没有收到请求。'];
        case 'readback.state': return ['扩权请求被拒绝后的状态读回', '本用例包含合法委托签发；扩权请求被拒绝，预算、订单与通知读回用于检查业务是否变化。'];
      }
      return null;
    },
  },

  s4: {
    catalogId: 'shared-budget', short: '共享预算',
    title: '两条分支，同一笔预算',
    lede: '根授权 1,000 元下有两条委托链，各自的子额度都是 700 元。两边同时下单 700 元，会不会一共花掉 1,400 元？',
    stack: [
      ['预算模型', '根与全部祖先共享额度，子额度不是独立钱包'],
      ['接受方式', 'PostgreSQL 接受事务内按固定锁序检查并原子预留'],
      ['证明', '两支请求各自带合法的 AGPoP 令牌与 AG-Proof'],
    ],
    delta: [
      ['只看本级', '每支只检查自己的 700 元子额度，两支都会通过，合计超出根预算。'],
      ['先查后扣', '先读余额再扣减，两个并发请求可能读到同一个余额。'],
      ['本项目', '在同一个事务里检查根及全部祖先的已预留与已结算，并原子预留；两支只会接受一支。', true],
    ],
    honest: '测试只断言恰好一支被接受，哪一支先拿到锁并不固定；示意里画成分支 A 先到。预算不足的拒绝码以实际返回为准。',
    band: [340, 740], focus: 'gateway',
    lanes: [
      {k: 'executor', x: 76, name: '分支 A', id: 'executor 令牌', tone: 'teal'},
      {k: 'executor-2', x: 210, name: '分支 B', id: '另一条委托链', tone: 'teal'},
      {k: 'gateway', x: 430, name: '执行网关', id: '/v1/invocations'},
      {k: 'ledger', x: 640, name: '授权与预算库', id: '根预算 1,000.00 元'},
      {k: 'downstream', x: 830, name: '模拟订单', id: '下游服务'},
    ],
    checkNote: {},
    events: illustrative('s4', [
      {event_type: 'fixture.setup', actor: 'ledger', safe_payload: {kind: 'budget-setup', root_limit_fen: 100000, branch_limit_fen: 70000}},
      {event_type: 'request.sent', actor: 'executor', target: 'gateway',
        safe_payload: {endpoint: INVOKE, token_holder: 'executor', proof_signer_kid: 'executor#key-1', amount_fen: 70000, branch: 'A'}},
      {event_type: 'request.sent', actor: 'executor-2', target: 'gateway',
        safe_payload: {endpoint: INVOKE, token_holder: 'executor', proof_signer_kid: 'executor#key-1', amount_fen: 70000, branch: 'B'}},
      {event_type: 'accept.committed', actor: 'gateway', target: 'ledger', safe_payload: {branch: 'A', reserved_fen: 70000}},
      {event_type: 'accept.rejected', actor: 'gateway', status: 'rejected', reason_code: 'BUDGET_EXCEEDED',
        safe_payload: {check: 'budget', branch: 'B', limit_fen: 100000, reserved_fen: 70000, requested_fen: 70000, http_status: 422}},
      {event_type: 'readback.state', actor: 'verifier',
        safe_payload: {budget_before: levels(0, 0), budget_after: [{reserved_fen: 70000, settled_fen: 0, calls: 1}], orders_before: 0, orders_after: 0}},
    ]),
    narrate(ev) {
      const p = ev.safe_payload || {};
      switch (ev.event_type) {
        case 'fixture.setup': return ['两条委托链共享根预算', '根授权上限 1,000.00 元；两条子链各自的子额度都是 700.00 元。'];
        case 'request.sent': return [p.branch === 'B' ? '分支 B 同时下单' : '分支 A 下单 700 元', p.branch === 'B' ? '两支请求同时到达，各自的子额度都够用。' : '分支 A 的令牌和证明都合法，子额度够用。'];
        case 'accept.committed': return ['分支 A 被接受', '接受事务锁住根授权，预留 700.00 元。'];
        case 'accept.rejected': return ['分支 B 预算不足，被拒绝', '根预算已预留 700.00 元，再加 700.00 元就超出 1,000.00 元上限。'];
        case 'readback.state': return ['只接受了一笔', '根授权预留 700.00 元，调用 1 次；两支合计没有超出根预算。'];
      }
      return null;
    },
  },

  s5: {
    catalogId: 'replay-idempotency', short: '重放幂等',
    title: '重放被拒，重试不重复',
    lede: '把同一个请求证明原样再发一次，会不会下两单？换一个新证明重试同一笔业务，又会怎样？',
    stack: [
      ['新鲜性', 'AG-Proof 的 jti、iat、exp；防重放记录唯一键 (kid, purpose, htu, jti)'],
      ['业务幂等', '请求体里的 idempotency_key 绑定同一个业务意图'],
      ['下游', '独立服务按同一意图幂等执行'],
    ],
    delta: [
      ['只靠时间窗', '有效期内原样重放的请求仍会被接受。'],
      ['只靠幂等键', '幂等键不能证明请求是新鲜的，旧证明可被反复使用。'],
      ['本项目', '两道检查分开：旧证明一律拒绝；新证明配同一幂等键，返回原来的操作，不产生第二份效果。', true],
    ],
    honest: '重放的拒绝码以实际返回为准（测试断言 401 或 409）。同键但改了意图的请求会被拒绝；重试不能复活已撤销的授权。',
    band: [300, 740], focus: 'gateway',
    lanes: [
      {k: 'executor', x: 90, name: '执行代理', id: 'executor#key-1', tone: 'teal'},
      {k: 'gateway', x: 420, name: '执行网关', id: '/v1/invocations'},
      {k: 'ledger', x: 630, name: '授权与预算库', id: '防重放记录'},
      {k: 'downstream', x: 830, name: '模拟订单', id: '下游服务'},
    ],
    checkNote: {freshness: '换了新的 jti，但幂等键 k1 没变'},
    events: illustrative('s5', [
      {event_type: 'request.sent', actor: 'executor', target: 'gateway',
        safe_payload: {endpoint: INVOKE, token_holder: 'executor', proof_signer_kid: 'executor#key-1', jti: 'jti-1', idempotency_key: 'k1'}},
      {event_type: 'accept.committed', actor: 'gateway', target: 'ledger', safe_payload: {operation: 'op-1', reserved_fen: 70000}},
      {event_type: 'request.sent', actor: 'executor', target: 'gateway',
        safe_payload: {endpoint: INVOKE, token_holder: 'executor', proof_signer_kid: 'executor#key-1', jti: 'jti-1', idempotency_key: 'k1', replay: true}},
      {event_type: 'check.rejected', actor: 'gateway', status: 'rejected', reason_code: 'REPLAY',
        safe_payload: {check: 'freshness', expected: '已登记：jti-1', observed: '本次：jti-1', http_status: 409}},
      {event_type: 'request.sent', actor: 'executor', target: 'gateway',
        safe_payload: {endpoint: INVOKE, token_holder: 'executor', proof_signer_kid: 'executor#key-1', jti: 'jti-2', idempotency_key: 'k1'}},
      {event_type: 'check.passed', actor: 'gateway', safe_payload: {check: 'freshness'}},
      {event_type: 'accept.committed', actor: 'gateway', target: 'ledger', safe_payload: {operation: 'op-1', existing: true}},
      {event_type: 'readback.state', actor: 'verifier', safe_payload: {orders_before: 0, orders_after: 0, operations_before: 1, operations_after: 1}},
    ]),
    narrate(ev) {
      const p = ev.safe_payload || {};
      switch (ev.event_type) {
        case 'request.sent':
          if (p.replay) return ['原样重放同一个证明', '请求体、令牌和 AG-Proof 一字不改再发一次，jti 还是 jti-1。'];
          if (p.jti === 'jti-2') return ['用新证明重试同一笔业务', '新签一个 AG-Proof（jti-2），幂等键仍是 k1。'];
          return ['第一次下单', 'AG-Proof 的 jti 是 jti-1，业务幂等键是 k1。'];
        case 'accept.committed': return p.existing ? ['返回原来的操作', '同一幂等键、同一意图，网关返回已有的 op-1，不新建操作。'] : ['接受并预留', '网关接受请求，创建操作 op-1，并登记 jti-1。'];
        case 'check.rejected': return ['旧证明被拒绝', 'jti-1 已经用过，同一个证明不能用第二次。'];
        case 'check.passed': return ['新证明是新鲜的', 'jti-2 没有用过，新鲜性检查通过。'];
        case 'readback.state': return ['业务效果没有翻倍', '重放和重试之后，仍然只有一个操作，下游没有多出订单。'];
      }
      return null;
    },
  },

  s6: {
    catalogId: 'revocation', short: '动态撤销',
    title: '撤销之后，拒绝新请求',
    lede: '根授权被撤销，执行代理手里的旧令牌签名依然有效。它还能下单吗？',
    stack: [
      ['授权状态', '接受业务的数据库事务内，复核根与全部祖先'],
      ['请求证明', 'AGPoP，每次请求使用新的 jti'],
      ['撤销接口', '项目管理接口，撤销整棵子树；不是 ', 'RFC 7009'],
    ],
    delta: [
      ['只验签名', '自包含令牌在过期前一直能通过验签，撤销不会自动生效。'],
      ['先查后做', '先查询令牌状态再接受业务，两步之间若有空档，撤销可能恰好落在中间。'],
      ['本项目', '在接受业务的同一事务里检查撤销状态；撤销先提交，新的接受一定被拒绝。', true],
    ],
    honest: '已经接受的操作不会因为后来的撤销被回滚。本用例只覆盖"撤销先提交"这一种顺序；测试里撤销是直接提交撤销事务，不是用户点击撤销接口。',
    band: [372, 740], focus: 'gateway',
    lanes: [
      {k: 'user', x: 82, name: '撤销方', id: '测试直接提交'},
      {k: 'executor', x: 232, name: '执行代理', id: 'executor#key-1', tone: 'teal'},
      {k: 'gateway', x: 452, name: '执行网关', id: '/v1/invocations'},
      {k: 'ledger', x: 650, name: '授权与预算库', id: '接受事务'},
      {k: 'downstream', x: 830, name: '模拟订单', id: '下游服务'},
    ],
    checkNote: {holder_binding: '签名有效只说明令牌出自 AS，不说明它现在还有效'},
    readbackSkip: ['gateway', 'downstream', '未接受，未转发下游'],
    events: illustrative('s6', [
      {event_type: 'fixture.setup', actor: 'user', target: 'ledger', safe_payload: {kind: 'revoke-begin', grant_alias: 'root'}},
      {event_type: 'request.sent', actor: 'executor', target: 'gateway',
        safe_payload: {endpoint: INVOKE, token_holder: 'executor', proof_signer_kid: 'executor#key-1', tool_id: TOOLS[0]}},
      {event_type: 'check.passed', actor: 'gateway', safe_payload: {check: 'holder_binding'}},
      {event_type: 'lock.waiting', actor: 'gateway', target: 'ledger', status: 'in_progress', safe_payload: {waiting_on: 's6-e1', reason: 'lock'}},
      {event_type: 'revocation.committed', actor: 'user', target: 'ledger', safe_payload: {grant_alias: 'root', scope: 'SUBTREE'}},
      {event_type: 'accept.rejected', actor: 'gateway', status: 'rejected', reason_code: 'REVOKED', cause_id: 's6-e5',
        safe_payload: {check: 'ancestor_state', http_status: 403}},
      {event_type: 'readback.state', actor: 'verifier',
        safe_payload: {budget_before: levels(0, 0), budget_after: levels(0, 0), orders_before: 0, orders_after: 0}},
    ]),
    narrate(ev) {
      switch (ev.event_type) {
        case 'fixture.setup': return ['开始撤销根授权', '撤销事务已经开始，但还没有提交。'];
        case 'request.sent': return ['执行代理用旧令牌下单', '令牌是撤销前签发的，请求证明是新签的。'];
        case 'check.passed': return ['签名与持有者都没问题', '密码学检查全部通过；但"签名有效"不等于"现在仍有权限"。'];
        case 'lock.waiting': return ['接受事务在排队', '撤销事务持有锁，接受只能等它结束，先后顺序由数据库决定。'];
        case 'revocation.committed': return ['撤销提交', '根授权及其整棵子树被标记为已撤销。'];
        case 'accept.rejected': return ['新接受被拒绝', '接受事务复核祖先状态，发现根授权已撤销。签名有效也越不过撤销。'];
        case 'readback.state': return ['业务没有任何变化', '三级预算都没有新预留，下游没有新订单。'];
      }
      return null;
    },
  },

  s7: {
    catalogId: 'recovery-evidence', short: '故障恢复',
    title: '下单成功后进程崩溃',
    lede: '下游已经下单成功，执行进程却在回报结果前被强制终止。会不会少记一笔账，或者重新下一单？',
    stack: [
      ['执行意图', '接受时固定不可变意图与预留，恢复只能沿用原意图'],
      ['恢复', '租约过期后由新进程按 operation_id 对账'],
      ['证据', 'SM2 签名回执，SM3 检查点，可离线验证'],
    ],
    delta: [
      ['超时即失败', '把"没收到回复"当成失败，释放预算后重下一单，会多买一份。'],
      ['超时即成功', '不核对就结算，下游实际失败时会多记一笔账。'],
      ['本项目', '结果未知时保持预留；恢复进程向下游按同一操作对账，确认后结算一次、发布一份回执。', true],
    ],
    honest: '恢复依赖持久状态和下游幂等契约；本地证据一致性不等于独立审计，也不证明现实收货。',
    band: [16, 560], focus: 'ledger',
    lanes: [
      {k: 'gateway', x: 76, name: '执行网关', id: '接受'},
      {k: 'worker', x: 206, name: '执行进程', id: '原进程'},
      {k: 'recovery', x: 336, name: '恢复进程', id: '新进程'},
      {k: 'ledger', x: 480, name: '授权与预算库', id: '操作记录'},
      {k: 'downstream', x: 650, name: '模拟订单', id: '下游服务'},
      {k: 'audit', x: 820, name: '回执与审计', id: 'SM2 回执'},
    ],
    checkNote: {},
    events: illustrative('s7', [
      {event_type: 'accept.committed', actor: 'gateway', target: 'ledger', safe_payload: {operation: 'op-1', reserved_fen: 70000, levels: 3}},
      {event_type: 'request.sent', actor: 'worker', target: 'downstream', safe_payload: {endpoint: '按不可变意图下单', operation: 'op-1'}},
      {event_type: 'process.crashed', actor: 'worker', status: 'failed', safe_payload: {signal: 'SIGKILL', after: 'downstream_commit'}},
      {event_type: 'lock.waiting', actor: 'recovery', target: 'ledger', status: 'in_progress', safe_payload: {reason: 'lease'}},
      {event_type: 'request.sent', actor: 'recovery', target: 'downstream', safe_payload: {endpoint: '按 operation_id 对账', operation: 'op-1'}},
      {event_type: 'operation.reconciled', actor: 'recovery', target: 'ledger', safe_payload: {operation: 'op-1', settled_fen: 70000}},
      {event_type: 'receipt.published', actor: 'ledger', target: 'audit', safe_payload: {operation: 'op-1', outbox: 1}},
      {event_type: 'readback.state', actor: 'verifier',
        safe_payload: {budget_before: levels(0, 0), budget_after: levels(0, 70000), orders_before: 0, orders_after: 1}},
    ]),
    narrate(ev) {
      const p = ev.safe_payload || {};
      switch (ev.event_type) {
        case 'accept.committed': return ['接受并预留', '三级授权各预留 700.00 元，操作 op-1 的意图从此固定。'];
        case 'request.sent': return p.endpoint === '按 operation_id 对账' ? ['向下游对账', '恢复进程不重新下单，而是按同一个操作查询下游结果。'] : ['执行进程下单', '按接受时固定的意图向下游下单，下游提交成功。'];
        case 'process.crashed': return ['进程被强制终止', '下游已经成功，但结果还没写回；此时结果未知，预算保持预留。'];
        case 'lock.waiting': return ['等待原进程的租约过期', '确认原执行者不会再写入后，恢复进程才接手。'];
        case 'operation.reconciled': return ['确认成功，结算一次', '对账确认下游已成功，结算 700.00 元，释放预留。'];
        case 'receipt.published': return ['发布签名回执', '回执进入待发布队列，之后可以离线验证。'];
        case 'readback.state': return ['只有一笔订单', '下游订单 1 单，三级预算各结算 700.00 元，没有重复下单。'];
      }
      return null;
    },
  },

  cosign: {
    catalogId: null, short: '双域共签 SM2',
    title: '授权域点头，才能签出这一笔',
    lede: '基础防线都依赖网关把关；如果网关本身被攻破呢？执行凭据的私钥被拆成两份，分别在授权域和执行域。授权域自己查一遍委托链、撤销和预算，确认无误才交出它那一半；两半合成一个普通 SM2 签名。',
    stack: [
      ['批准 profile', 'AG-COSM2-APPROVAL-1 · sm2-2p'],
      ['签名对象', '双方由结构化行动独立重算消息与 SM3 摘要；授权域不信任执行域提供的摘要'],
      ['三轮协议', 'Q1 → 部分签名 → 合成并标准 SM2 验签；请求携带 ag-approval'],
    ],
    delta: [
      ['普通单钥', '网关被攻破就能任意签（凭据单钥在网关侧的部署）。'],
      ['旧版 FROST', '2-of-3 门限签名，但签名者不检查授权状态，且非国密。'],
      ['本项目', '授权域独立核验后才出份额，产出标准 SM2 签名；网关单方签不出，下单服务也独立验签并拒绝重复使用。', true],
    ],
    honest: '当前为两域协同（n=2），半诚实模型；两域部署在同一主机；向 t-of-n 的推广已有设计，尚未实现。网关被攻破时，至多能把授权域已核准的那一笔执行一次；签名之后才发生的撤销仍靠网关接受事务拦截。右侧为示意推演；左侧可运行固定六用例并显示原始结果来源、日期与单次耗时。不证明恶意安全或跨主机隔离。',
    band: [30, 900], focus: 'authz-domain',
    lanes: [
      {k: 'exec-domain', x: 115, name: '执行域', id: 'P1 · 网关侧'},
      {k: 'authz-domain', x: 310, name: '授权域', id: 'P2 · AS 侧'},
      {k: 'gateway', x: 510, name: '执行网关', id: '标准 SM2 验签'},
      {k: 'ledger', x: 700, name: '授权与预算库', id: '当前状态'},
      {k: 'downstream', x: 840, name: '模拟订单', id: '合成业务'},
    ],
    events: illustrative('cosign', [
      {event_type: 'fixture.setup', actor: 'exec-domain', safe_payload: {}, display: {top: '正常一笔：形成结构化行动', sub: '双方独立重算消息与摘要'}},
      {event_type: 'cosign.round1', actor: 'exec-domain', target: 'authz-domain', safe_payload: {}, display: {top: '第一轮：发出 Q1', sub: '附结构化行动，授权域自己重算'}},
      {event_type: 'cosign.checked', actor: 'authz-domain', target: 'ledger', safe_payload: {check: '委托链与权限'}, display: {top: '第二轮：独立核验委托链与权限'}},
      {event_type: 'cosign.checked', actor: 'authz-domain', target: 'ledger', safe_payload: {check: '撤销状态'}, display: {top: '独立核验当前撤销状态'}},
      {event_type: 'cosign.checked', actor: 'authz-domain', target: 'ledger', safe_payload: {check: '预算'}, display: {top: '独立核验预算'}},
      {event_type: 'cosign.partial', actor: 'authz-domain', target: 'exec-domain', safe_payload: {}, display: {top: '返回部分签名', sub: '仅示意协议消息，不展示秘密材料'}},
      {event_type: 'cosign.combined', actor: 'exec-domain', safe_payload: {}, display: {top: '第三轮：合成签名', sub: '标准 SM2 验签通过才输出'}},
      {event_type: 'request.sent', actor: 'exec-domain', target: 'gateway', safe_payload: {}, display: {top: '携 ag-approval 请求网关', sub: '标准 SM2 验签及行动匹配'}},
      {event_type: 'accept.committed', actor: 'gateway', target: 'ledger', safe_payload: {}, display: {top: '接受事务：再查撤销与预算', sub: '批准不替代接受时的当前验权'}},
      {event_type: 'request.sent', actor: 'gateway', target: 'downstream', safe_payload: {}, display: {top: '正常一笔：一单', sub: '示意效果，非真实运行结果'}},
      {event_type: 'revocation.committed', actor: 'ledger', target: 'ledger', safe_payload: {grant_alias: '另一笔根授权'}, display: {top: '另一笔：授权已撤销'}},
      {event_type: 'cosign.round1', actor: 'exec-domain', target: 'authz-domain', safe_payload: {}, display: {top: '撤销后，另一笔请求共签'}},
      {event_type: 'cosign.refused', actor: 'authz-domain', status: 'rejected', reason_code: 'AUTHZ_REVOKED', safe_payload: {}, display: {top: 'AUTHZ_REVOKED', sub: '授权域拒绝出份额'}},
    ]),
    narrate(ev) {
      const notes = {
        'fixture.setup': ['正常一笔：形成行动', '双方拿到结构化行动，各自重算消息和摘要。'],
        'cosign.round1': ['第一轮：执行域请求共签', '发送 Q1 与结构化行动，授权域不接收对方算好的摘要作为签名依据。'],
        'cosign.checked': ['第二轮：授权域独立核验' + (ev.safe_payload.check || ''), '授权域自己读取授权与预算库；还须核对有效期、路径、范围与策略版本，任一不满足即拒绝。'],
        'cosign.partial': ['授权域返回部分签名', '检查全部通过才返回 (r, s2, s3)；本图不展示数值或秘密材料。'],
        'cosign.combined': ['第三轮：合成并标准验签', '执行域合成普通 SM2 签名，用标准验签确认，通过才输出。'],
        'request.sent': ev.target === 'downstream' ? ['正常一笔：只下一单', '这是示意效果；尚未运行双域共签采购。'] : ['批准随请求送到网关', 'ag-approval 不替代令牌、请求证明与接受事务的当前验权。'],
        'accept.committed': ['接受事务再次检查', '撤销、预算与新鲜度仍在接受事务内复核。'],
        'revocation.committed': ['另一笔：授权已撤销', '下面是另一笔请求，前面的正常示意订单不受这次拒绝影响。'],
        'cosign.refused': ['授权域拒绝：AUTHZ_REVOKED', '拒绝发生在授权域，未返回部分签名；这一笔的网关请求与下游订单均未发生。'],
      };
      return notes[ev.event_type] || null;
    },
  },

  threshold: {
    catalogId: null, fixed: 'threshold', short: '对照：旧版 FROST', design: true,
    title: '为什么换掉旧版 FROST',
    lede: '这是上一版方案：三个签名域中任意两个，用 FROST 共同签出一份行动批准，网关在接受事务里核对。它已正确接入采购流程；本次保留它，用来说明为什么换成双域共签。',
    stack: [
      ['签名方案', '2-of-3 FROST-Ed25519 组签名，网关只持组公钥'],
      ['批准对象', 'V2 行动：授权路径、holder、工具、参数摘要、金额、策略版本、key epoch、有效期'],
      ['传递方式', '采购请求附 ag-approval 头，令牌与 AG-Proof 照常验证'],
    ],
    delta: [
      ['不查授权', '签名域只对行动摘要签名，不独立核验委托链、撤销与预算；授权状态仍完全依赖网关。'],
      ['非国密', '组签名是 Ed25519，网关需另外维护一套非 SM2 的验签。'],
      ['可信初始化', '组密钥由可信 dealer 一次性生成并分发份额。'],
      ['双域共签', '授权域独立核验后才出份额；产出标准 SM2 签名；完整私钥不重建。', true],
    ],
    honest: '不是说 FROST 方案有错：它是正确实现的门限签名，只是与授权主线结合得不够紧。右侧是流程示意，不是逐帧回放；真实结果以左栏的本机固定演示为准。演示中份额由同一宿主、同一 OS 用户管理，采用可信分发，不是生产部署。',
    band: [516, 900], focus: 'gateway',
    lanes: [
      {k: 'signer-1', x: 62, name: '签名域 S1', id: '份额 1'},
      {k: 'signer-2', x: 186, name: '签名域 S2', id: '份额 2'},
      {k: 'signer-3', x: 310, name: '签名域 S3', id: '份额 3'},
      {k: 'coordinator', x: 440, name: '协调器', id: '只持组公钥'},
      {k: 'gateway', x: 620, name: '执行网关', id: '验 ag-approval'},
      {k: 'ledger', x: 805, name: '授权与预算库', id: '接受事务'},
    ],
    checkNote: {threshold_signature: '路径、金额、参数摘要与实际订单一致'},
    events: illustrative('threshold', [
      {event_type: 'fixture.setup', actor: 'coordinator', safe_payload: {kind: 'action-digest'},
        display: {top: '规范化行动（V2，24 个字段）', sub: '授权路径、工具、参数摘要、金额、策略版本、有效期'}},
      {event_type: 'threshold.share_signed', actor: 'signer-1', target: 'coordinator', safe_payload: {share: 1}},
      {event_type: 'threshold.aggregated', actor: 'coordinator', status: 'pending', safe_payload: {shares: [1], threshold: 2, total: 3}},
      {event_type: 'threshold.share_signed', actor: 'signer-3', target: 'coordinator', safe_payload: {share: 3}},
      {event_type: 'threshold.aggregated', actor: 'coordinator', safe_payload: {shares: [1, 3], threshold: 2, total: 3}},
      {event_type: 'request.sent', actor: 'coordinator', target: 'gateway', safe_payload: {endpoint: INVOKE},
        display: {top: 'POST /v1/invocations', mono: true, sub: 'ag-approval: ‹组签名 + 行动›', sub2: 'Authorization: AGPoP ‹executor 的令牌›'}},
      {event_type: 'check.passed', actor: 'gateway', safe_payload: {check: 'threshold_signature'}},
      {event_type: 'accept.committed', actor: 'gateway', target: 'ledger', safe_payload: {},
        display: {top: '接受，并原子写入 action_id 绑定', sub: '只产生一单；同一批准不能换给别的操作'}},
      {event_type: 'revocation.committed', actor: 'user', target: 'ledger', safe_payload: {grant_alias: 'root', scope: 'SUBTREE'}},
      {event_type: 'accept.rejected', actor: 'gateway', status: 'rejected', reason_code: 'REVOKED',
        safe_payload: {check: 'ancestor_state', left: '门限批准有效', http_status: 403}},
    ]),
    narrate(ev) {
      const p = ev.safe_payload || {};
      switch (ev.event_type) {
        case 'fixture.setup': return ['形成行动摘要', '把这次下单的全部关键字段规范化，三个签名域只对这一份内容签名。'];
        case 'threshold.share_signed': return ['签名域 S' + p.share + ' 签出份额', '每个签名域只持有自己的一份私钥份额，只对本次行动签名。'];
        case 'threshold.aggregated': return (p.shares || []).length >= p.threshold
          ? ['两份到齐，聚合成组签名', '2 / 3 达到门限，聚合出一个可以用组公钥验证的 Ed25519 签名。']
          : ['只有一份，不足以批准', '1 / 3 未达到门限 2；单个签名域不能独自批准，重复同一份额也不算两票。'];
        case 'request.sent': return ['批准随请求送到网关', '采购请求同时带着 AGPoP 令牌、AG-Proof 和 ag-approval 批准头。'];
        case 'check.passed': return ['组签名有效，内容对得上', '网关用组公钥验签，并把批准里的行动和实际订单逐项比对。'];
        case 'accept.committed': return ['接受并绑定，只下一单', '接受事务内写入 action_id 与操作的绑定，失败会整体回滚，不消耗批准。'];
        case 'revocation.committed': return ['另一笔：授权已被撤销', '根授权及其子树被撤销，但手里的门限批准本身仍然有效。'];
        case 'accept.rejected': return ['批准有效，仍被拒绝', '执行时复核当前授权：集体批准也不能覆盖用户的撤销。'];
      }
      return null;
    },
  },

  x402: {
    catalogId: null, fixed: 'x402', short: 'x402 支付', design: true,
    title: '先报价，再按报价付款',
    lede: '付款不能代替授权：付款意图先经双域共签批准，批准里写死这笔付款的摘要。网关接受后才去付款——资源先返回 402 报价，适配器核对报价、签 EIP-3009 转账授权，资源服务器验证后在链上结算。',
    stack: [
      ['支付协议', 'HTTP 402 + x402 v2 exact/EVM，顺序 verify → resource → settle'],
      ['付款证明', 'EIP-3009 转账授权（EIP-712 签名），nonce 只能用一次'],
      ['与授权', '页面按钮使用双域共签（sm2-2p）批准，V3 批准内含支付意图摘要；独立资产预算，随祖先撤销一起受约束'],
    ],
    delta: [
      ['只看付款', '付款成功就放行，等于用付款代替了授权。'],
      ['超时重付', '响应丢失就重新签一笔，可能付两次钱。'],
      ['本项目', '支付意图在网关接受时绑定；签名与 nonce 先落盘再发送，结果未知时按同一 nonce 对账，不重签不重付。', true],
    ],
    honest: '右侧是流程示意，不是逐帧回放；真实结果以左栏的本机固定演示为准。付款意图的批准是双域 SM2 共签，但链上结算签名仍是 EIP-3009（secp256k1），不是 SM2；只用本机测试链与自建测试代币，没有真实资产或生产网络。',
    band: [10, 500], focus: 'x402',
    lanes: [
      {k: 'gateway', x: 80, name: '执行网关', id: '接受采购'},
      {k: 'ledger', x: 240, name: '授权与预算库', id: '独立资产预算'},
      {k: 'x402', x: 410, name: '支付适配器', id: '受控签名组件'},
      {k: 'resource', x: 620, name: '付费资源服务器', id: '返回 402'},
      {k: 'chain', x: 812, name: '本地测试链', id: 'Anvil · 测试代币'},
    ],
    checkNote: {'quote-match': '换收款方、网络、资产或金额都会被拒绝', 'payload-persisted': '响应丢失时按同一 nonce 对账，不重签、不重付'},
    readbackExtra: [['ledger', '支付状态 SETTLED', 'lab jade'], ['resource', '资源已交付', 'lab jade'], ['chain', '链上 +1 笔', 'lab jade']],
    events: illustrative('x402', [
      {event_type: 'accept.committed', actor: 'gateway', target: 'ledger', safe_payload: {},
        display: {top: '接受采购，登记支付意图', sub: '绑定授权路径、收款方、网络、资产与金额'}},
      {event_type: 'request.sent', actor: 'x402', target: 'resource', safe_payload: {},
        display: {top: '请求付费资源', sub: '只由已接受的操作驱动，不接受页面或模型传来的付款对象'}},
      {event_type: 'request.sent', actor: 'resource', target: 'x402', safe_payload: {},
        display: {top: 'HTTP 402 Payment Required', mono: true, sub: 'exact/EVM：收款方、资产、金额、有效期'}},
      {event_type: 'check.passed', actor: 'x402', safe_payload: {check: 'quote-match'}},
      {event_type: 'check.passed', actor: 'x402', safe_payload: {check: 'payload-persisted'}},
      {event_type: 'request.sent', actor: 'x402', target: 'resource', safe_payload: {},
        display: {top: '带支付证明重发请求', sub: 'EIP-3009 transferWithAuthorization 签名'}},
      {event_type: 'request.sent', actor: 'resource', target: 'chain', safe_payload: {},
        display: {top: 'verify → resource → settle', mono: true, sub: '链上执行授权转账，同一 nonce 只能用一次'}},
      {event_type: 'readback.state', actor: 'verifier', safe_payload: {}},
      {event_type: 'accept.rejected', actor: 'gateway', status: 'rejected', reason_code: 'PAYMENT_BUDGET_EXCEEDED',
        safe_payload: {http_status: 422},
        display: {cols: [['独立资产预算', '100.000000'], ['另一笔报价', '100.000001'], ['超出', '0.000001', 'seal']]}},
    ]),
    narrate(ev) {
      const p = ev.safe_payload || {};
      switch (ev.event_type) {
        case 'accept.committed': return ['网关接受采购，登记支付意图', '要付给谁、付多少、用哪条链和哪种资产，在接受时就固定下来。'];
        case 'request.sent':
          if ((ev.display || {}).top === 'HTTP 402 Payment Required') return ['资源返回 402 报价', '资源服务器说明要怎样付款：收款方、资产、金额和有效期。'];
          if (ev.target === 'chain') return ['验证后在链上结算', '资源服务器先验证签名，交付资源，再把转账授权提交上链。'];
          if ((ev.display || {}).top === '带支付证明重发请求') return ['带着支付证明再请求一次', '支付证明是一份 EIP-3009 转账授权签名，由受控签名组件生成。'];
          return ['请求付费资源', '支付适配器只为已经被网关接受的操作去付款。'];
        case 'check.passed': return p.check === 'payload-persisted'
          ? ['先落盘，再发送', '签名和 nonce 在发出前写入数据库；万一响应丢失，用同一个 nonce 对账。']
          : ['核对报价', '报价和接受时登记的支付意图逐字段比对，任何一项不同都拒绝。'];
        case 'readback.state': return ['只结算一次', '链上一笔转账，资源交付一次；重放同一个 nonce 不会再付一次。'];
        case 'accept.rejected': return ['另一笔：超出资产预算，被拒绝', '资产预算单独计量；报价超出上限时网关直接拒绝，事务回滚，不付款。'];
      }
      return null;
    },
  },
};
const MORE_SCENES = ['s2', 's4', 's5', 's7'];

/*
 * 汇报结构：五章递进。先讲系统，再讲基础防线，然后抛出"网关本身被攻破怎么办"引出双域共签，
 * 再讲付款扩展，最后用真实运行核对。章内分组决定左栏顶部的子导航。
 */
const CHAPTERS = [
  {k: 'overview', name: '总览', groups: [['', ['overview']]]},
  {k: 'defense', name: '基础防线', groups: [['三道防线', ['s1', 's3', 's6']], ['更多保障', MORE_SCENES]]},
  {k: 'core', name: '核心机制 · 双域共签', groups: [['', ['cosign', 'threshold']]]},
  {k: 'pay', name: '扩展 · x402 支付', groups: [['', ['x402']]]},
  {k: 'evidence', name: '运行证据', groups: [['', ['evidence']]]},
];
const chapterOf = view => CHAPTERS.find(c => c.groups.some(([, vs]) => vs.includes(view))) || null;

/* 模块说明：六项固定格式 */
const MODULES = {
  cosign: ['双域协同 SM2 签名', 'sm2-2p · AG-COSM2-APPROVAL-1', '网关被攻破时，单方也签不出可执行的批准。', '执行网关在接受采购前发起；授权域与 AS 同侧。', '结构化行动；执行域与授权域各持一份私钥份额。', '授权域独立核验委托链、撤销、有效期与预算，通过才返回部分签名；执行域合成后标准 SM2 验签。', '普通 SM2 签名的 ag-approval，网关与下单服务都用标准国密库验证。', '半诚实两方（n=2），两域在同一主机；签名之后发生的撤销仍靠网关接受事务拦截。'],
  'exec-domain': ['执行域 P1', '网关侧 · 示意模块', '与授权域共同产生这一笔行动的 SM2 签名。', '执行请求触发第一轮；智能体不持有份额。', '结构化行动和授权域返回的部分签名。', '自行重算消息，合成后用标准 SM2 验签，通过才输出。', '普通 SM2 签名与行动批准信封。', '只有自身一份秘密不能独自完成共签；当前 n=2、半诚实、同主机，核心尚未接入本页。'],
  'authz-domain': ['授权域 P2', 'AS 侧 · 示意模块', '独立决定当前授权是否允许签出这一笔。', '执行域发送结构化行动与第一轮公开消息。', '结构化行动及当前授权、撤销与预算状态。', '自己重算消息，核对委托链、有效期、撤销、范围、预算与策略版本。', '仅在检查通过后返回部分签名，否则返回拒绝码。', '不接受执行域算好的摘要作为依据；当前为半诚实模型，不提供恶意安全证明或跨主机隔离。'],
  user: ['用户 / 撤销方', 'OIDC 登录 / 用户同意', '任务必须源于用户明确批准的范围；用户也可以撤销自己批准的授权。', '用户通过登录客户端发起；场景 6 中由测试直接提交撤销事务。', '登录结果、任务与预算确认。', '身份、租户、任务对象与预算范围。', '用户授权，作为根授权的依据。', 'ID Token 只证明身份，不能用于下单；当前登录同意为自动流程，手动页面尚未提供。'],
  planner: ['统筹代理', 'planner#key-1', '把任务拆分并交给下级代理。', '用户批准任务后启动。', '根授权与任务说明。', '只能在自身授权内申请委托。', '向 AS 提交委托申请；不能自己签发可信令牌。', '当前是确定性代理，未接入真实大模型。'],
  selector: ['选品代理', 'selector#key-1', '读取报价并选择商品。', '统筹代理交接任务。', 'AS 签发的子令牌、报价文档。', '商品与报价是否在任务范围内。', '选品结果，以及给执行代理的委托申请。', '恶意报价可能影响判断，授权边界仍由系统执行。'],
  executor: ['执行代理', 'executor#key-1', '发出精确、可核对的工具调用。', '选品代理交接任务。', 'AS 签发的令牌、固定请求参数。', '用自己的 SM2 私钥签署 AG-Proof。', 'Authorization: AGPoP 令牌，加 AG-Proof。', '只持自身密钥，不持下游管理凭据。'],
  'executor-2': ['分支 B', '同一任务下的另一条委托链', '演示两条分支并发争用同一笔根预算。', '共享预算测试。', '另一条链上合法签发的令牌。', '用对应持有者私钥签署 AG-Proof。', '与分支 A 同时到达的下单请求。', '两条链各自合法，问题只在合计是否超出祖先预算。'],
  attacker: ['冒用方 / 中途篡改', '测试注入', '演示令牌被复制或请求被篡改后的情况。', '安全场景测试。', '窃取的令牌副本，或转发中的请求。', '无。', '冒用或被改过的请求。', '前提是执行代理私钥未泄露；私钥泄露不在这些场景的防护范围内。'],
  as: ['授权服务器 AS', 'authorization/exchange_service.py', '统一签发各级令牌，委托只能收窄。', '代理发起授权码交换与 Token Exchange。', '父令牌、父持有者签名的委托申请。', '身份、当前授权，金额、工具、期限、次数、深度等逐维包含。', 'SM2 签名的令牌，ag_cnf 写明持有者公钥；或带原因的拒绝。', '私有 GM-MVP-1 配置，不宣称与标准 OIDC、DPoP 互通。'],
  gateway: ['执行网关', 'POST /v1/invocations', '决定一次工具请求能否被接受。', '执行代理提交工具请求。', 'AGPoP 令牌、AG-Proof、完整请求体。', 'SM2 验签、ag_cnf 与证明签名者一致、token_sm3 与 body_sm3 绑定、jti 防重放，再查当前授权与预算。', '接受后固定的业务意图；或 401 HOLDER_MISMATCH 等拒绝码。', '接受不等于业务完成；不判断模型的选择是否合理。'],
  ledger: ['授权与预算库', 'PostgreSQL 接受事务', '并发与撤销下仍不超权。', '网关的接受事务、恢复流程。', '请求意图，根及全部祖先授权。', '撤销状态、期限、共享额度与次数、防重放。', '原子预留、结算与操作记录。', '子额度不是独立钱包；结果未知时不释放预算。'],
  downstream: ['模拟订单与通知', '下游服务，独立事务', '已接受的意图只产生一次效果。', '网关与恢复流程通过服务认证调用。', '不可变业务意图与幂等键。', '服务身份、同键意图一致。', '模拟订单或固定模板通知。', '合成业务，无真实付款。'],
  audit: ['回执与独立审计', 'SM2 回执 / SM3 检查点', '事后能独立核对发生了什么。', '网关与恢复流程。', '签名回执、执行记录、检查点。', '签名、摘要与关联关系。', '可离线验证的证据包。', '一致性通过不代表当前授权仍有效；未锚定尾部仍有局限。'],
  worker: ['执行进程', '执行与恢复服务', '按接受时固定的意图调用下游。', '网关接受后启动。', '操作 ID 与不可变意图。', '持有租约，独占执行。', '下游调用与结果写回。', '进程随时可能中断，结果可能未知。'],
  recovery: ['恢复进程', 'reconcile', '在原进程中断后完成未决操作。', '租约过期后由恢复流程启动。', '操作 ID。', '按同一操作向下游对账，不重新生成意图。', '结算与回执。', '依赖持久状态与下游幂等契约。'],
  coordinator: ['门限协调器', '独立原型', '收集签名份额并聚合。', '执行前的行动批准流程。', '行动摘要与签名份额。', '份额是否针对同一摘要、签名域是否重复。', '聚合后的组签名。', '只持组公钥与公开协议材料，不持任何完整私钥。已接入固定采购演示；份额暂由同一 OS 用户管理。'],
  'signer-1': ['签名域 S1', '独立原型', '独立批准高风险行动。', '协调器。', '规范化的行动摘要。', '认证后只对本次行动签名。', '一份签名份额。', '与采购代理是不同角色；已接入固定采购演示；份额暂由同一 OS 用户管理。'],
  'signer-2': ['签名域 S2', '独立原型', '独立批准高风险行动。', '协调器。', '规范化的行动摘要。', '认证后只对本次行动签名。', '一份签名份额。', '与采购代理是不同角色；已接入固定采购演示；份额暂由同一 OS 用户管理。'],
  'signer-3': ['签名域 S3', '独立原型', '独立批准高风险行动。', '协调器。', '规范化的行动摘要。', '认证后只对本次行动签名。', '一份签名份额。', '与采购代理是不同角色；已接入固定采购演示；份额暂由同一 OS 用户管理。'],
  threshold: ['门限签名', '2-of-3，本机固定演示', '高风险行动需要多个独立签名域共同批准。', '网关在接受事务内验证批准。', '规范化的行动摘要。', '门限签名验签，并与授权路径、策略版本绑定。', '行动批准凭据。', '本机固定演示已接入采购：有效批准只产生一单；不足/篡改/撤销会被拒绝。公网仍只读，份额暂由同一 OS 用户管理，非 SM2。'],
  x402: ['支付适配 x402', '本机固定演示', 'HTTP 资源的付费交互：先 402 报价，再带 EIP-3009 签名授权支付。', '网关在接受事务内绑定支付意图；资源服务器验证并结算。', '402 报价与支付要求。', '收款方、金额、网络与报价有效期。', '支付证明与结算结果。', '本机固定演示已接入，批准方案为双域 SM2 共签：有效支付恰好一单且链上仅一笔；伪造签名、不含支付摘要的批准、超预算、重放会被拒绝。链上结算签名仍是 EIP-3009；使用本机测试链与自建代币，无真实资产；公网页面仍只读；不替代 OAuth 授权。'],
  resource: ['资源服务器', '本机模拟服务', '演示用的付费资源服务：返回 402 报价，验证付款并结算。', '由本机演示脚本启动，只绑定回环端口。', '402 报价与支付要求。', '报价金额、网络、资产与收款方地址。', '支付证明验证与结算结果。', '本机模拟，不对外提供服务；资产是测试链上的自建代币。'],
  chain: ['本地 EVM 测试链', 'Anvil · chain 31337', '本机测试链，承载自建 USDC 合约（EIP-3009）。', '仅本机演示进程访问，不连公网。', 'EIP-3009 授权转账交易。', 'nonce、签名、金额与收款方。', '交易哈希与链上事件。', '测试链与自建代币，没有任何真实资产。'],
};

const CATALOG_FALLBACK = [
  ['stolen-token', '盗取令牌但没有私钥'], ['signed-parameters', '篡改签名后的参数'],
  ['delegation-scope', '委托不得扩权'], ['shared-budget', '并发分支共享预算'],
  ['replay-idempotency', '重放与业务幂等'], ['revocation', '撤销后拒绝新接受'],
  ['recovery-evidence', '故障恢复与证据'],
].map(([id, title]) => ({id, title, run_available: false, history_available: false}));

/* 供 node 测试读取 */
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {SCHEMA_VERSION, ACTORS, EVENT_TYPES, STATUSES, SOURCES, eventProblems, EventStore, fen, readbackDelta, SCENES, MORE_SCENES, CHAPTERS, chapterOf, MODULES, CATALOG_FALLBACK};
}

/* ======================================================================
 * 第二部分：界面
 * ==================================================================== */

if (typeof document !== 'undefined' && document.getElementById('app')) (function ui() {
  const NS = 'http://www.w3.org/2000/svg';
  const $ = id => document.getElementById(id);
  const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const svgEl = (tag, attrs, parent) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    if (parent) parent.append(n);
    return n;
  };
  const svgText = (parent, attrs, s) => { const t = svgEl('text', attrs, parent); t.textContent = s; return t; };
  const h = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };

  const VIEWS = CHAPTERS.flatMap(c => c.groups.flatMap(([, vs]) => vs));
  const ui = {
    view: 'overview', lastIn: {}, steps: {}, timer: null, follow: true,
    token: '', connected: false, state: null, posting: false, actionError: '',
    openRecords: new Set(), lastRecordsKey: '', lastProofKey: '', band: [0, 0], bandY: null,
    rows: [], seals: [], feed: null, feeds: new Map(), sceneKey: '',
  };

  /* ---------- 通用：测量文字宽度 ---------- */
  function measure(node, s, cjk, ascii) {
    try { const w = node.getComputedTextLength(); if (w > 0) return w; } catch (e) { /* 未渲染时回退估算 */ }
    return [...s].reduce((n, c) => n + (c.charCodeAt(0) > 255 ? cjk : ascii), 0);
  }
  function label(g, x, y, s, cls, absX) {
    const ax = absX == null ? x : absX;
    const onBand = ax > ui.band[0] && ax < ui.band[1] && (!ui.bandY || (y > ui.bandY[0] && y < ui.bandY[1]));
    return svgText(g, {x, y, class: cls + ' halo' + (onBand ? ' band-h' : '')}, s);
  }

  /* ---------- 参与方按钮 ---------- */
  function chip(parent, k, x, top, name, id, tone, planned) {
    const g = svgEl('g', {class: 'who' + (planned ? ' planned' : ''), tabindex: '0', role: 'button', 'aria-label': name + '，查看职责说明', 'data-k': k}, parent);
    const rect = svgEl('rect', {class: 'chip', y: top, height: 52, rx: 10}, g);
    const nm = svgText(g, {class: 'nm', x: x - 10, y: top + 23}, name);
    const idt = svgText(g, {class: 'id' + (tone ? ' ' + tone : ''), x, y: top + 41}, id);
    const nameW = measure(nm, name, 17, 9.5), idW = measure(idt, id, 11, 6.7);
    const info = svgEl('g', {class: 'info', transform: `translate(${x - 10 + nameW / 2 + 13} ${top + 17})`}, g);
    svgEl('circle', {r: 7}, info); svgText(info, {x: 0, y: 0.5}, 'i');
    const w = Math.max(nameW + 26, idW) + 20;
    rect.setAttribute('x', x - w / 2); rect.setAttribute('width', w);
    g.addEventListener('click', () => openModule(k));
    g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); openModule(k); } });
    return {x1: x - w / 2, x2: x + w / 2, top, bottom: top + 52, x, cy: top + 26, g};
  }

  /* ---------- 小图形 ---------- */
  function glyph(g, kind, x, y, ownProof) {
    const w = svgEl('g', {class: 'glyph', transform: `translate(${x} ${y})`}, g);
    const tok = dx => {
      const d = `M${dx - 13},-8.5 H${dx + 8} L${dx + 13},-4.2 L${dx + 8},0 L${dx + 13},4.2 L${dx + 8},8.5 H${dx - 13} Z`;
      svgEl('path', {class: 't', d}, w); svgEl('path', {class: 'ht', d}, w); svgText(w, {class: 'tt', x: dx - 2, y: 0}, '令');
    };
    const prf = dx => {
      svgEl('circle', {class: 'p' + (ownProof ? ' own' : ''), cx: dx, r: 9}, w);
      svgEl('circle', {class: 'ht', cx: dx, r: 9}, w);
      svgText(w, {class: 'pt' + (ownProof ? ' own' : ''), x: dx, y: 0}, '证');
    };
    if (kind === 'token') tok(0); else { tok(-11); prf(15); }
  }
  function arrow(g, x1, x2, y, kind) {
    const dir = x2 > x1 ? 1 : -1;
    const dashed = ['theft', 'setup', 'skip', 'wait'].includes(kind);
    const p = svgEl('path', {d: `M${x1 + dir * 6},${y} H${x2 - dir * 7}`, class: 'ln ' + kind + (dashed ? '' : ' solid draw')}, g);
    if (!dashed) p.setAttribute('pathLength', '1');
    const mk = {gold: 'a-gold', theft: 'a-seal', skip: 'a-mute', setup: 'a-mute', wait: null}[kind];
    if (mk !== null) p.setAttribute('marker-end', `url(#${mk || 'a-ink'})`);
  }
  function tick(g, x, y) {
    const t = svgEl('g', {class: 'tick', transform: `translate(${x} ${y})`}, g);
    svgEl('circle', {r: 8}, t); svgEl('path', {d: 'M-3.5,0.2 L-1,2.8 L3.8,-2.6'}, t);
  }
  function cross(g, x, y) {
    const t = svgEl('g', {class: 'tick', transform: `translate(${x} ${y})`}, g);
    svgEl('circle', {r: 8, fill: '#C63A2E'}, t); svgEl('path', {d: 'M-3,-3 L3,3 M3,-3 L-3,3'}, t);
  }
  function seal(g, x, y) {
    const s = svgEl('g', {transform: `translate(${x} ${y}) rotate(-6)`}, g);
    const k = svgEl('g', {class: 'seal-g', filter: 'url(#grain)'}, s);
    svgEl('rect', {class: 'ink', x: -33, y: -18, width: 66, height: 36, rx: 4}, k);
    svgEl('rect', {class: 'rim', x: -29, y: -14, width: 58, height: 28, rx: 3}, k);
    svgText(k, {x: 0, y: 1}, '驳回');
    return k;
  }

  /* ---------- 时序图：每类事件的画法 ---------- */
  const laneX = (sc, k) => { const l = sc.lanes.find(x => x.k === k); return l ? l.x : null; };

  function rowLayout(ev, firstReject) {
    switch (ev.event_type) {
      case 'cosign.refused': return [36, 64];
      case 'cosign.round1': case 'cosign.checked': case 'cosign.partial': case 'cosign.combined': return [28, 34];
      case 'request.sent': return [28, (ev.safe_payload && ev.safe_payload.token_holder) || (ev.display && ev.display.sub2) ? 54 : 26];
      case 'token.issued': case 'delegation.issued': return [28, 42];
      case 'delegation.requested': return [28, 26];
      case 'fixture.setup': return [28, 30];
      case 'check.passed': case 'threshold.verified': return [16, 36];
      case 'check.rejected': case 'delegation.rejected': case 'accept.rejected': return [72, firstReject ? 86 : 68];
      case 'accept.committed': case 'operation.reconciled': case 'receipt.published': return [28, 26];
      case 'lock.waiting': return [26, 26];
      case 'revocation.committed': case 'process.crashed': case 'run.error': return [18, 26];
      case 'threshold.share_signed': return [26, 12];
      case 'threshold.aggregated': return [22, 40];
      case 'readback.state': return [30, 26];
      default: return [18, 24];
    }
  }

  /* 公开 DID key ID 很长，图中只显示最后一段，如 planner#key-1 */
  const kid = v => (typeof v === 'string' && v.includes(':') ? v.slice(v.lastIndexOf(':') + 1) : v);
  /* 在本行之前找最近一条某类事件，用于从已观测的上下文画出拒绝原因 */
  const before = (all, i, type) => { for (let k = i - 1; k >= 0; k--) if (all[k].event_type === type) return all[k]; return null; };

  function drawRow(g, sc, ev, y, firstReject, all, idx) {
    const p = ev.safe_payload || {};
    const D = ev.display || null;
    all = all || []; idx = idx == null ? 0 : idx;
    const ax = laneX(sc, ev.actor), tx0 = laneX(sc, ev.target);
    const tx = ev.target === ev.actor ? null : tx0;
    const mid = (ax + tx) / 2;
    const illus = ev.source === 'illustrative';
    const needsPair = ['token.issued', 'delegation.issued', 'delegation.requested', 'request.sent', 'accept.committed', 'operation.reconciled', 'receipt.published', 'threshold.share_signed', 'lock.waiting'];
    if ((needsPair.includes(ev.event_type) && (ax == null || tx == null)) || (!needsPair.includes(ev.event_type) && !['readback.state', 'revocation.committed', 'run.error'].includes(ev.event_type) && ax == null && tx == null)) {
      label(g, 40, y + 4, `未识别的参与方：${ev.actor || '-'} → ${ev.target || '-'}（${ev.event_type}）`, 'lab mute left', 40);
      return;
    }
    switch (ev.event_type) {
      case 'cosign.round1': case 'cosign.checked': case 'cosign.partial': case 'cosign.combined': {
        const cx = tx == null ? ax + 20 : mid;
        if (tx != null) arrow(g, ax, tx, y, 'ink');
        if (ev.event_type === 'cosign.checked' || ev.event_type === 'cosign.combined') tick(g, ax, y);
        label(g, cx, y - 12, D.top, 'lab' + (tx == null ? ' left' : ''), cx);
        if (D.sub) label(g, cx, y + 22, D.sub, 'lab mute' + (tx == null ? ' left' : ''), cx);
        return;
      }
      case 'cosign.refused': {
        const mark = svgEl('g', {class: 'cosign-refusal'}, g);
        cross(mark, ax, y);
        label(g, ax + 20, y + 4, 'AUTHZ_REVOKED', 'lab mono left', ax + 20);
        label(g, ax + 20, y + 28, '授权域拒绝出份额', 'lab left', ax + 20);
        label(g, laneX(sc, 'gateway'), y + 54, '本笔：未发生', 'lab mute', laneX(sc, 'gateway'));
        label(g, laneX(sc, 'downstream'), y + 54, '本笔：未发生', 'lab mute', laneX(sc, 'downstream'));
        return;
      }
      case 'token.issued':
      case 'delegation.issued': {
        arrow(g, ax, tx, y, 'gold');
        label(g, mid, y - 10, ev.event_type === 'token.issued' ? 'Token Exchange 签发访问令牌' : '签发子令牌', 'lab', mid);
        const lim = p.limits && Number.isInteger(p.limits.amount_fen) ? '  额度 ' + fen(p.limits.amount_fen) : '';
        label(g, mid, y + 20, `act.sub=${p.holder}  ag_cnf.kid=${p.holder_kid}`, 'lab mono', mid);
        if (lim || p.parent_alias) label(g, mid, y + 36, `ag_parent_id=${p.parent_alias || '-'}${lim}`, 'lab mono', mid);
        glyph(g, 'token', tx + (ax > tx ? 28 : -28), y);
        return;
      }
      case 'delegation.requested': {
        arrow(g, ax, tx, y, 'ink');
        label(g, mid, y - 10, 'Token Exchange 委托申请' + (p.target_holder ? `，目标持有者 ${p.target_holder}` : ''), 'lab', mid);
        const rq = p.requested_limits || {}, pr = p.parent_limits || {};
        const extra = (p.requested_scope || []).filter(t => !(p.parent_scope || []).includes(t));
        const line = extra.length ? `scope += ${extra.join(' ')}` : `ag_amount_limit_fen=${rq.amount_fen}（父授权 ${pr.amount_fen}）`;
        label(g, mid, y + 20, line, 'lab mono' + (extra.length || rq.amount_fen > pr.amount_fen ? ' seal' : ''), mid);
        return;
      }
      case 'fixture.setup': {
        const kind = p.kind;
        if (tx == null) {
          const x = ax;
          if (!kind && p.token_holder) {
            // 实际事件：测试取得令牌副本（attacker → attacker）
            glyph(g, 'token', x + 24, y - 4);
            label(g, x + 44, y - 2, `取得 ${p.token_holder} 令牌的副本`, 'lab left seal', x + 44);
            label(g, x + 44, y + 17, `测试前置：证明将由 ${kid(p.proof_signer_kid) || '未采集'} 签名`, 'lab mute left', x + 44);
            return;
          }
          const text = (D && D.top) || {
            'budget-setup': `根授权上限 ${fen(p.root_limit_fen)}；两条子链各 ${fen(p.branch_limit_fen)}`,
            'action-digest': '规范化行动 → action_digest',
          }[kind] || '测试前置动作';
          label(g, x, y - 6, text, 'lab', x);
          label(g, x, y + 14, (D && D.sub) || (kind === 'action-digest' ? '绑定任务、授权路径、工具、参数、金额与策略版本' : '测试前置条件'), 'lab mute', x);
          return;
        }
        const copy = kind === 'copy-token';
        arrow(g, ax, tx, y, copy ? 'theft' : 'setup');
        const top = {
          'copy-token': '复制令牌',
          'revoke-begin': '撤销根授权的事务开始，尚未提交',
          'signed-request': '签好的请求：AG-Proof 覆盖 body_sm3',
        }[kind] || '测试前置动作';
        const sub = {
          'copy-token': '私钥不在其中',
          'revoke-begin': '测试前置动作：撤销事务持有锁',
          'signed-request': `签名时 ${p.field} = ${p.value}`,
        }[kind] || '';
        label(g, mid, y - 10, top, copy ? 'lab seal' : 'lab', mid);
        if (sub) label(g, mid, y + 20, sub, kind === 'signed-request' ? 'lab mono' : 'lab mute', mid);
        if (copy) glyph(g, 'token', tx - 24, y);
        return;
      }
      case 'request.sent': {
        arrow(g, ax, tx, y, 'ink');
        if (D) {
          label(g, mid, y - 10, D.top, D.mono ? 'lab mono' : 'lab', mid);
          if (D.sub2) {
            const left = Math.min(ax, tx) + 22;
            label(g, left, y + 22, D.sub, 'lab mono left', left);
            label(g, left, y + 40, D.sub2, 'lab mono left', left);
          } else if (D.sub) label(g, mid, y + 20, D.sub, 'lab mute', mid);
          return;
        }
        label(g, mid, y - 10, p.endpoint || '请求', p.token_holder ? 'lab mono' : 'lab', mid);
        if (p.proof_signer_kid) p.proof_signer_kid = kid(p.proof_signer_kid);
        if (p.token_holder) {
          const left = Math.min(ax, tx) + 22;
          if (p.tampered) {
            label(g, left, y + 22, p.tampered, 'lab mono left seal', left);
            label(g, left, y + 40, `AG-Proof: ‹${p.proof_signer_kid} 签名，未改›`, 'lab mono left', left);
          } else if (p.jti) {
            label(g, left, y + 22, `AG-Proof: jti=${p.jti}${p.replay ? '（原样重放）' : ''}`, 'lab mono left' + (p.replay ? ' seal' : ''), left);
            label(g, left, y + 40, `idempotency_key=${p.idempotency_key}`, 'lab mono left', left);
          } else if (Number.isInteger(p.amount_fen)) {
            label(g, left, y + 22, `分支 ${p.branch}：下单 ${fen(p.amount_fen)}`, 'lab mono left', left);
            label(g, left, y + 40, `AG-Proof: ‹${p.proof_signer_kid} 签名›`, 'lab mono left', left);
          } else {
            label(g, left, y + 22, `Authorization: AGPoP ‹${p.token_holder} 的令牌›`, 'lab mono left', left);
            label(g, left, y + 40, p.proof_signer_kid ? `AG-Proof: ‹${p.proof_signer_kid} 签名›` : 'AG-Proof: ‹签名者未在事件中公开›', 'lab mono left', left);
          }
          const own = (p.proof_signer_kid || '').startsWith(p.token_holder + '#');
          glyph(g, 'bundle', tx - (tx > ax ? 36 : -36), y, own);
        } else if (p.operation) {
          label(g, mid, y + 20, `operation_id=${p.operation}`, 'lab mono', mid);
        }
        return;
      }
      case 'check.passed':
      case 'threshold.verified': {
        if (ev.event_type === 'threshold.verified' && tx != null) arrow(g, ax, tx - 12, y, 'ink');
        const x = ev.event_type === 'threshold.verified' && tx != null ? tx : ax;
        tick(g, x, y);
        const text = {token_signature: 'SM2 验签：令牌由 AS 签发', holder_binding: '令牌签名有效，持有者一致', request_binding: '请求体与令牌绑定一致', freshness: 'jti 新鲜，未被使用过', threshold_signature: 'Ed25519 组签名有效，批准成立', 'quote-match': '报价与支付意图逐字段一致', 'payload-persisted': '签名授权与 nonce 先落盘，再发送'}[p.check] || p.check;
        label(g, x + 16, y + 5, text, 'lab left', x + 16);
        const note = sc.checkNote && sc.checkNote[p.check];
        if (note) label(g, x + 16, y + 25, note, 'lab mute left', x + 16);
        return;
      }
      case 'check.rejected':
      case 'delegation.rejected':
      case 'accept.rejected': {
        const s = seal(g, ax, y - 50);
        // 印章始终压在拒绝方的生命线上；说明文字在靠边的泳道时向内收，避免出画
        const rx = Math.min(Math.max(ax, 250), 650);
        if (p.check === 'holder_binding') tally(g, ax, y, p);
        else if (p.check === 'delegation_narrowing' && p.dimension === 'amount') columns(g, ax, y, [['父授权上限', fen(p.expected)], ['本次申请', fen(p.observed)], ['超出', Number.isInteger(p.observed) && Number.isInteger(p.expected) ? fen(p.observed - p.expected) : '未采集', 'seal']]);
        else if (p.check === 'delegation_narrowing') setCompare(g, ax, y, p);
        else if (p.check === 'ancestor_state') statePair(g, ax, y, p.left || '签名有效', '当前授权：根已撤销');
        else if (p.check === 'request_binding') columns(g, ax, y, [['签名时', p.expected], ['收到时', p.observed, 'seal']], 220);
        else if (p.check === 'freshness') columns(g, ax, y, [['防重放记录', p.expected], ['这次请求', p.observed, 'seal']], 170);
        else if (p.check === 'budget') {
          const over = [p.reserved_fen, p.requested_fen, p.limit_fen].every(Number.isInteger) ? p.reserved_fen + p.requested_fen - p.limit_fen : null;
          columns(g, ax, y, [['根预算上限', fen(p.limit_fen)], ['已被预留', fen(p.reserved_fen)], ['本次申请', fen(p.requested_fen)], ['超出', over == null ? '未采集' : fen(over), 'seal']], 118);
        } else if (D && D.cols) columns(g, rx, y, D.cols, 150);
        else derivedReject(g, sc, ev, ax, y, all, idx);
        label(g, rx, y + 60, `${p.http_status || ''} ${ev.reason_code || ''}`.trim() || '拒绝原因未采集', 'reason', rx);
        if (illus && firstReject) label(g, rx, y + 78, sc.fixed ? '与本机固定演示的实际返回码一致，见左栏' : '接口契约中的拒绝码；接入事件流后显示实际返回', 'lab mute', rx);
        else if (!illus && firstReject) label(g, rx, y + 78, '本次运行实际返回', 'lab mute', rx);
        return s;
      }
      case 'accept.committed': {
        arrow(g, ax, tx, y, 'ink');
        if (D) {
          label(g, mid, y - 10, D.top, 'lab', mid);
          if (D.sub) label(g, mid, y + 20, D.sub, 'lab mute', mid);
          return;
        }
        if (p.existing) {
          label(g, mid, y - 10, '同一幂等键，返回已有操作', 'lab', mid);
          label(g, mid, y + 20, `operation_id=${p.operation}，不新建`, 'lab mono', mid);
        } else {
          label(g, mid, y - 10, p.branch ? `接受分支 ${p.branch}，原子预留` : '接受并原子预留', 'lab', mid);
          label(g, mid, y + 20, (p.operation ? `operation_id=${p.operation}  ` : '') + (Number.isInteger(p.reserved_fen) ? `reserve ${fen(p.reserved_fen)}` + (p.levels ? ` × ${p.levels} 级` : '') : ''), 'lab mono', mid);
        }
        return;
      }
      case 'operation.reconciled': {
        arrow(g, ax, tx, y, 'ink');
        label(g, mid, y - 10, '确认下游已成功，结算一次', 'lab', mid);
        label(g, mid, y + 20, `settle ${fen(p.settled_fen)}，释放预留`, 'lab mono', mid);
        return;
      }
      case 'receipt.published': {
        arrow(g, ax, tx, y, 'gold');
        label(g, mid, y - 10, '签名回执进入待发布队列', 'lab', mid);
        label(g, mid, y + 20, 'SM2 回执，可离线验证', 'lab mute', mid);
        return;
      }
      case 'process.crashed': {
        const c = svgEl('g', {class: 'cut', transform: `translate(${ax} ${y})`}, g);
        svgEl('circle', {r: 9}, c);
        svgEl('line', {x1: -5, y1: -5, x2: 5, y2: 5}, c); svgEl('line', {x1: 5, y1: -5, x2: -5, y2: 5}, c);
        label(g, ax + 18, y + 5, '进程被强制终止（kill -9）', 'lab left strong', ax + 18);
        label(g, ax + 18, y + 24, '下游已提交，结果没有写回；结果未知，预算保持预留', 'lab mute left', ax + 18);
        return;
      }
      case 'lock.waiting': {
        arrow(g, ax, tx, y, 'wait');
        const hg = svgEl('g', {class: 'hourglass', transform: `translate(${mid} ${y})`}, g);
        svgEl('path', {d: 'M-6,-8 H6 L-6,8 H6 Z'}, hg);
        const lease = p.reason === 'lease';
        label(g, mid, y - 14, lease ? '等待原进程租约过期' : '接受事务等待锁', 'lab', mid);
        label(g, mid, y + 24, lease ? '确认原执行者不会再写入' : '撤销事务未提交，接受只能排队', 'lab mute', mid);
        return;
      }
      case 'revocation.committed': {
        // 撤销落在授权与预算库；实际事件是 ledger → gateway，示意事件是撤销方 → ledger
        const lx = laneX(sc, 'ledger');
        const cx = (ev.actor === 'ledger' || ev.target === 'ledger') && lx != null ? lx : (tx0 != null ? tx0 : ax);
        const c = svgEl('g', {class: 'cut', transform: `translate(${cx} ${y})`}, g);
        svgEl('circle', {r: 9}, c); svgEl('line', {x1: -6, y1: 6, x2: 6, y2: -6}, c);
        const toLeft = cx > 650;
        label(g, toLeft ? cx - 18 : cx + 18, y + 5, `撤销已提交：${p.grant_alias} 及其子树`, 'lab strong ' + (toLeft ? 'right' : 'left'), toLeft ? cx - 18 : cx + 18);
        if (ev.actor !== 'ledger' && ax != null && ax !== cx) arrow(g, ax, cx + (ax < cx ? -10 : 10), y, 'setup');
        return;
      }
      case 'run.error': {
        const x = 60;
        const c = svgEl('g', {class: 'cut', transform: `translate(${x} ${y})`}, g);
        svgEl('circle', {r: 9}, c);
        svgEl('line', {x1: -5, y1: -5, x2: 5, y2: 5}, c); svgEl('line', {x1: 5, y1: -5, x2: -5, y2: 5}, c);
        label(g, x + 18, y + 5, '运行失败：这不是一次安全拒绝' + (ev.reason_code ? `（${ev.reason_code}）` : ''), 'lab left strong', x + 18);
        label(g, x + 18, y + 24, '本轮轨迹不完整，结论以重新运行的结果为准', 'lab mute left', x + 18);
        return;
      }
      case 'threshold.share_signed': {
        arrow(g, ax, tx, y, 'ink');
        label(g, (ax + tx) / 2, y - 10, `签名份额 ${p.share}，对同一 action_digest`, 'lab', (ax + tx) / 2);
        return;
      }
      case 'threshold.aggregated': {
        const got = p.shares || [], need = p.threshold, total = p.total || 3, ok = got.length >= need;
        for (let i = 1; i <= total; i++) {
          const cx = ax - 40 + (i - 1) * 40;
          const c = svgEl('circle', {cx, cy: y, r: 11, fill: got.includes(i) ? (ok ? '#2C7A60' : '#18203A') : '#fff', stroke: '#18203A', 'stroke-width': 1.3, 'stroke-dasharray': got.includes(i) ? 'none' : '3 3'}, g);
          void c;
          svgText(g, {x: cx, y: y + 4, class: 'lab', fill: got.includes(i) ? '#fff' : '#8A91A3'}, 'S' + i);
        }
        label(g, ax, y + 32, `${got.length} / ${total}，${ok ? '达到门限 ' + need + '，聚合成组签名' : '未达门限 ' + need + '，不能形成批准'}`, ok ? 'lab jade' : 'lab', ax);
        return;
      }
      case 'readback.state': {
        const d = readbackDelta(p);
        if (sc.readbackSkip) {
          const [a, b, text] = sc.readbackSkip;
          const xa = laneX(sc, a), xb = laneX(sc, b);
          if (xa != null && xb != null) {
            arrow(g, xa, xb, y - 16, 'skip');
            label(g, (xa + xb) / 2, y - 24, text, 'lab mute', (xa + xb) / 2);
          }
        }
        const put = (k, text) => { const x = laneX(sc, k); if (x != null) label(g, x, y + 20, text, 'lab jade', x); };
        const plus = v => (v == null ? '未采集' : (v >= 0 ? '+' : '') + v);
        const money = v => (v == null ? '未采集' : (v >= 0 ? '+' : '-') + fen(Math.abs(v)));
        if (d.settled) put('ledger', '结算 ' + money(d.rootSettled != null ? d.rootSettled : d.settled) + (d.rootSettled != null ? '（每级）' : ''));
        else if (d.rootReserved != null && p.budget_after && p.budget_after.length === 1) put('ledger', '根预留 ' + money(d.rootReserved));
        else if (d.reserved != null) put('ledger', '预留 ' + money(d.reserved));
        else if (d.grants != null) put('ledger', '子授权 ' + plus(d.grants));
        else if (Number.isInteger(p.operations_before) && Number.isInteger(p.operations_after)) put('ledger', '操作数 ' + plus(p.operations_after - p.operations_before));
        if (d.orders != null) put('downstream', '订单 ' + plus(d.orders));
        // 场景里写死的补充说明只用于示意；真实事件只画读回到的数值
        if (ev.source === 'illustrative') for (const [k, text, cls] of sc.readbackExtra || []) { const x = laneX(sc, k); if (x != null) label(g, x, y + 20, text, cls, x); }
        const fx = laneX(sc, sc.focus === 'ledger' ? 'gateway' : sc.focus);
        if (fx != null) label(g, fx + 16, y + 20, '读回', 'lab mute left', fx + 16);
        return;
      }
      default:
        label(g, 40, y + 4, '未识别事件：' + ev.event_type, 'lab mute left', 40);
    }
  }

  function tally(g, cx, cy, p, leftKey, rightKey) {
    const t = svgEl('g', {transform: `translate(${cx} ${cy})`}, g);
    const k = 30;
    svgEl('path', {class: 'half tok', d: `M-150,${-k} H-10 L-2,${-k + 12} L-10,${-k + 24} L-2,${-k + 36} L-10,${-k + 48} L-2,${k} H-150 Z`}, t);
    svgEl('path', {class: 'half prf', d: `M150,${-k} H12 L4,${-k + 9} L14,${-k + 20} L4,${-k + 31} L14,${-k + 42} L4,${-k + 53} L10,${k} H150 Z`}, t);
    svgText(t, {class: 'h-k', x: -138, y: -7}, leftKey || '令牌 ag_cnf.kid');
    svgText(t, {class: 'h-v', x: -138, y: 14, fill: '#1E7896'}, p.expected || '');
    svgText(t, {class: 'h-k', x: 26, y: -7}, rightKey || 'AG-Proof 签名者');
    svgText(t, {class: 'h-v', x: 26, y: 14, fill: '#7A4C9C'}, p.observed || '');
  }
  function columns(g, cx, cy, cols, step) {
    const w = step || 130, n = cols.length;
    cols.forEach(([k, v, cls], i) => {
      const x = cx + (i - (n - 1) / 2) * w;
      label(g, x, cy - 6, k, 'lab mute', x);
      label(g, x, cy + 18, v == null ? '未采集' : String(v), 'lab strong' + (cls ? ' ' + cls : ''), x);
    });
  }
  function setCompare(g, cx, cy, p) {
    const parent = Array.isArray(p.expected) ? p.expected : [], asked = Array.isArray(p.observed) ? p.observed : [];
    if (parent.length > 3) {
      // 实际授权的工具集合较长：只画数量和多出来的部分
      const extra = asked.filter(t => !parent.includes(t));
      columns(g, cx, cy, [['父授权 scope', `${parent.length} 个工具`], ['申请多出', extra.length ? extra.map(t => '+ ' + t).join('  ') : '未采集', 'seal']], 220);
      return;
    }
    const col = (x, title, items, mark) => {
      label(g, x, cy - 12, title, 'lab mute left', x);
      items.forEach((it, i) => {
        const extra = mark && !parent.includes(it);
        label(g, x, cy + 7 + i * 16, (extra ? '+ ' : '  ') + it, 'set-item' + (extra ? ' extra' : ''), x);
      });
    };
    col(cx - 225, '父授权 scope', parent, false);
    col(cx + 15, '申请的 scope', asked, true);
  }
  /*
   * 实际事件里的拒绝没有单独的 check 字段，只有状态码与原因码。
   * 这里只用同一轮里已经观测到的事件画出对比，不补造未观测的内部检查。
   */
  function derivedReject(g, sc, ev, ax, y, all, idx) {
    const req = before(all, idx, 'request.sent');
    const rev = before(all, idx, 'revocation.committed');
    const drq = before(all, idx, 'delegation.requested');
    const rp = (req && req.safe_payload) || {};
    if (ev.event_type === 'delegation.rejected' && drq) {
      const q = drq.safe_payload || {}, pr = q.parent_limits || {}, rq = q.requested_limits || {};
      if (ev.safe_payload.dimension === 'scope') setCompare(g, ax, y, {expected: q.parent_scope, observed: q.requested_scope});
      else if (Number.isInteger(pr.amount_fen) && Number.isInteger(rq.amount_fen)) columns(g, ax, y, [['父授权上限', fen(pr.amount_fen)], ['本次申请', fen(rq.amount_fen)], ['超出', fen(rq.amount_fen - pr.amount_fen), 'seal']]);
      else label(g, ax, y + 4, '超出维度：' + (ev.safe_payload.dimension || '未采集'), 'lab', ax);
      return;
    }
    if (rev && rev.seq < ev.seq) { statePair(g, ax, y, `第 ${rev.seq} 步撤销已提交`, '新的接受被拒绝'); return; }
    if (rp.token_holder && rp.proof_signer_kid && !kid(rp.proof_signer_kid).startsWith(rp.token_holder + '#')) {
      tally(g, ax, y, {expected: rp.token_holder, observed: kid(rp.proof_signer_kid)}, '令牌持有者', 'AG-Proof 签名者');
      return;
    }
    label(g, ax, y + 4, '网关拒绝了这次请求', 'lab', ax);
  }

  function statePair(g, cx, cy, left, right) {
    // 左右两半以拒绝点为中心排开，按实际文字宽度放图标，长文字也不会压住
    const lt = label(g, cx - 16, cy + 1, left, 'lab right jade', cx - 16);
    tick(g, cx - 16 - measure(lt, left, 14, 8) - 14, cy - 4);
    cross(g, cx + 24, cy - 4);
    label(g, cx + 38, cy + 1, right, 'lab left seal strong', cx + 38);
  }

  /* ---------- 长时序图的镜头：固定画面高度，平滑移到当前步骤 ---------- */
  const VIEW_H = 640;
  function setCamera(y) {
    ui.camY = y;
    $('diagram').setAttribute('viewBox', `0 ${y.toFixed(1)} 900 ${VIEW_H}`);
    $('layer-heads').setAttribute('transform', `translate(0 ${y.toFixed(1)})`);
  }
  function moveCamera(target, animate) {
    if (ui.camAnim) cancelAnimationFrame(ui.camAnim);
    const from = ui.camY || 0;
    if (!animate || reduced || Math.abs(target - from) < 2 || typeof requestAnimationFrame !== 'function') { setCamera(target); return; }
    const t0 = performance.now(), dur = 420;
    const tick = now => {
      const t = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - t, 3);
      setCamera(from + (target - from) * e);
      if (t < 1) ui.camAnim = requestAnimationFrame(tick);
    };
    ui.camAnim = requestAnimationFrame(tick);
  }

  /* 场景没有专门讲解时的通用说法；只描述事件本身，不推测 */
  function fallbackNarration(ev) {
    const p = ev.safe_payload || {};
    const code = `${p.http_status || ''} ${ev.reason_code || ''}`.trim();
    switch (ev.event_type) {
      case 'run.error': return ['运行失败', '这是程序运行失败，不是一次安全拒绝；本轮轨迹不完整。'];
      case 'accept.rejected': case 'check.rejected': return ['网关拒绝', '本次实际返回 ' + (code || '未采集') + '。'];
      case 'delegation.rejected': return ['授权服务器拒绝', '本次实际返回 ' + (code || '未采集') + '。'];
      case 'readback.state': return ['读回业务状态', '运行后读回预算与下游状态，用来检查业务是否发生变化。'];
      case 'request.sent': return ['发出请求', (p.endpoint || '请求') + '。'];
    }
    return null;
  }

  /* ---------- 场景：事件来源（示意或真实事件流） ---------- */
  function sceneEvents(id) {
    const sc = SCENES[id];
    const f = ui.feeds.get(sc.catalogId);
    if (f && sc.catalogId && f.scenarioId === sc.catalogId && f.store.ordered().length) {
      return {events: f.store.ordered(), source: f.source || 'live', feed: f};
    }
    return {events: sc.events, source: 'illustrative', feed: null};
  }

  function buildScene(id) {
    const sc = SCENES[id];
    const back = $('layer-back'), heads = $('layer-heads'), rowsL = $('layer-rows');
    back.replaceChildren(); heads.replaceChildren(); rowsL.replaceChildren();
    ui.band = sc.band; ui.bandY = null;
    const src = sceneEvents(id);
    const events = src.events.filter(e => !NOT_DRAWN.has(e.event_type));
    ui.sceneKey = id + ':' + src.source + ':' + events.length;
    let cursor = 100;
    const firstRej = events.findIndex(e => e.status === 'rejected');
    const spans = [];
    const ys = events.map((ev, i) => { const [top, bottom] = rowLayout(ev, i === firstRej); const y = cursor + top; spans.push([cursor - 2, top + bottom + 14]); cursor = y + bottom + 10; return y; });
    const H = Math.max(640, cursor + 16);
    // 步骤多时不再整体缩小：画面高度固定，镜头跟着当前步骤上下移动，参与方一栏始终留在顶部
    ui.H = H; ui.tall = H > 720; ui.camY = 0;
    $('diagram').setAttribute('viewBox', `0 0 900 ${ui.tall ? VIEW_H : H}`);
    $('diagram').append(heads);
    heads.removeAttribute('transform');
    svgEl('rect', {class: 'band', x: sc.band[0], y: 0, width: sc.band[1] - sc.band[0], height: H}, back);
    if (ui.tall) {
      svgEl('rect', {class: 'heads-bg', x: -20, y: -20, width: 940, height: 110}, heads);
      svgEl('rect', {class: 'band', x: sc.band[0], y: -20, width: sc.band[1] - sc.band[0], height: 110}, heads);
      svgEl('line', {class: 'heads-rule', x1: 0, x2: 900, y1: 90, y2: 90}, heads);
    }
    svgText(heads, {class: 'band-label', x: sc.band[0] + 16, y: 20}, '可信授权执行边界');
    if (sc.band[0] > 150) svgText(heads, {class: 'tap-hint', x: 8, y: 20}, '点击参与方查看职责');
    for (const l of sc.lanes) svgEl('line', {class: 'life', 'data-k': l.k, x1: l.x, x2: l.x, y1: 84, y2: H - 10}, back);
    const f = laneX(sc, sc.focus);
    const firstIn = events.findIndex(e => e.target === sc.focus);
    let lastAt = -1; events.forEach((e, i) => { if (e.actor === sc.focus || e.target === sc.focus) lastAt = i; });
    if (f != null && firstIn >= 0 && lastAt >= firstIn) svgEl('rect', {class: 'act-bar', x: f - 4, y: ys[firstIn] - 6, width: 8, height: ys[lastAt] - ys[firstIn] + 30, rx: 2}, back);
    for (const l of sc.lanes) chip(heads, l.k, l.x, 30, l.name, l.id, l.tone);
    ui.rows = []; ui.seals = []; ui.ys = ys;
    events.forEach((ev, i) => {
      const g = svgEl('g', {class: 'row future'}, rowsL);
      svgEl('rect', {class: 'hl', x: 0, y: spans[i][0], width: 900, height: spans[i][1], rx: 8}, g);
      svgEl('circle', {class: 'seq-dot', cx: 14, cy: ys[i], r: 10}, g);
      svgText(g, {class: 'seq', x: 14, y: ys[i] + 4}, String(ev.seq));
      const s = drawRow(g, sc, ev, ys[i], i === firstRej, events, i);
      ui.rows.push({g, ev, reject: ev.status === 'rejected'});
      ui.seals.push(s || null);
    });
    $('diagram-title').textContent = sc.title + '：消息时序与拒绝位置';
    setSource(src.source === 'illustrative' ? (sc.design ? 'design' : 'illus') : src.source);
  }

  function showStep(i, animate) {
    const id = ui.view, sc = SCENES[id];
    const n = ui.rows.length;
    if (!n) return;
    i = Math.max(0, Math.min(n - 1, i));
    ui.steps[id] = i;
    ui.rows.forEach((r, k) => {
      const cls = k === i ? 'current' : k < i ? (r.reject ? 'keep' : 'past') : 'future';
      r.g.setAttribute('class', 'row ' + cls + (r.reject ? ' rej' : ''));
      if (k === i && animate && !reduced) r.g.querySelectorAll('.ln.draw').forEach(p => { p.style.animation = 'none'; void p.getBBox(); p.style.animation = ''; });
      const s = ui.seals[k];
      if (s) {
        s.classList.remove('stamp');
        s.classList.toggle('on', k <= i);
        if (k === i && animate && !reduced) { void s.getBBox(); s.classList.add('stamp'); }
      }
    });
    const ev = ui.rows[i].ev;
    const involved = new Set([ev.actor, ev.target].filter(Boolean));
    document.querySelectorAll('#layer-heads .who, #layer-back .life').forEach(n => n.classList.toggle('involved', involved.has(n.getAttribute('data-k'))));
    if (ui.tall) moveCamera(Math.max(0, Math.min(ui.H - VIEW_H, ui.ys[i] - VIEW_H * 0.45)), animate);
    const [title, say] = sc.narrate(ev, i) || fallbackNarration(ev) || ['第 ' + ev.seq + ' 步', ev.event_type + (ev.reason_code ? '：' + ev.reason_code : '')];
    renderStepper(i);
    placeNextHint(i);
    const parts = [h('strong', null, title), h('span', null, say)];
    const f = sceneEvents(id).feed;
    if (f) {
      const gaps = f.store.gaps();
      if (gaps.length) parts.push(h('span', 'warn', `　缺少第 ${gaps.slice(0, 3).join('、')} 条事件，等待补齐`));
      else if (!ui.connected) parts.push(h('span', 'warn', '　连接中断，画面停在最后收到的事件'));
      else if (!f.terminal) parts.push(h('span', 'live-note', '　现场运行中'));
      else if (f.complete === false) parts.push(h('span', 'warn', '　本轮轨迹不完整'));
    }
    $('cap').replaceChildren(...parts);
    $('prev').disabled = i === 0;
    $('next-label').textContent = i === n - 1 ? '从头再看' : '下一步';
  }

  /* 底部进度条：每一步一个可点的小段，被拒的那一步是红色 */
  function renderStepper(i) {
    const box = $('count'); box.replaceChildren();
    ui.rows.forEach((r, k) => {
      const b = h('button', 'seg' + (k < i ? ' done' : k === i ? ' cur' : '') + (r.reject ? ' rej' : ''));
      b.type = 'button';
      const t = (SCENES[ui.view].narrate(r.ev, k) || ['第 ' + (k + 1) + ' 步'])[0];
      b.title = `${k + 1}. ${t}`; b.setAttribute('aria-label', `第 ${k + 1} 步：${t}`);
      b.addEventListener('click', () => { stop(); ui.follow = false; showStep(k, k === i + 1); });
      box.append(b);
    });
    const c = h('span', 'cnt'); c.append(h('b', null, String(i + 1)), document.createTextNode(' / ' + ui.rows.length));
    box.append(c);
  }

  /* 图里下一步将出现的位置放一个提示：点它、点画面空白处或按 → 都能继续 */
  function placeNextHint(i) {
    const old = $('next-hint'); if (old) old.remove();
    if (i >= ui.rows.length - 1 || ui.timer) return;
    const nextEv = ui.rows[i + 1].ev, y = ui.ys[i + 1];
    const t = (SCENES[ui.view].narrate(nextEv, i + 1) || ['下一步'])[0];
    const g = svgEl('g', {id: 'next-hint', class: 'next-hint', role: 'button', tabindex: '0', 'aria-label': '下一步：' + t}, $('layer-rows'));
    const rect = svgEl('rect', {x: 34, y: y - 17, height: 34, rx: 17}, g);
    svgText(g, {class: 'nh-k', x: 52, y: y + 5}, '下一步');
    const title = svgText(g, {class: 'nh-t', x: 104, y: y + 5}, t);
    const tw = measure(title, t, 14, 8);
    const hint = svgText(g, {class: 'nh-hint', x: 104 + tw + 14, y: y + 5}, '点击或按 →');
    rect.setAttribute('width', 104 + tw + 14 + measure(hint, '点击或按 →', 12, 7) + 18 - 34);
    g.addEventListener('click', e => { e.stopPropagation(); step(1); });
    g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); step(1); } });
  }

  const PLAY = 'M4.5 2.5v11l9-5.5z', PAUSE = 'M4 2.5h2.8v11H4zM9.2 2.5H12v11H9.2z';
  function stop() {
    if (!ui.timer) return;
    clearInterval(ui.timer); ui.timer = null;
    $('play-ic').setAttribute('d', PLAY); $('play-label').textContent = '自动播放';
    if (SCENES[ui.view] && ui.rows.length) placeNextHint(ui.steps[ui.view] || 0);
  }
  function step(delta) {
    if (!SCENES[ui.view]) return;
    stop();
    const next = (ui.steps[ui.view] || 0) + delta;
    ui.follow = delta > 0 && next >= ui.rows.length - 1;
    showStep(next, delta > 0);
  }
  $('prev').addEventListener('click', () => step(-1));
  $('next').addEventListener('click', () => {
    if (SCENES[ui.view] && (ui.steps[ui.view] || 0) >= ui.rows.length - 1) { stop(); showStep(0, true); return; }
    step(1);
  });
  // 演示时点画面空白处也能前进；点参与方按钮仍然打开说明
  $('diagram').addEventListener('click', e => {
    if (!SCENES[ui.view] || (e.target.closest && e.target.closest('.who, .next-hint'))) return;
    if ((ui.steps[ui.view] || 0) < ui.rows.length - 1) step(1);
  });
  $('play').addEventListener('click', () => {
    if (!SCENES[ui.view]) return;
    if (ui.timer) { stop(); return; }
    if ((ui.steps[ui.view] || 0) >= ui.rows.length - 1) showStep(0, true);
    $('play-ic').setAttribute('d', PAUSE); $('play-label').textContent = '暂停';
    const old = $('next-hint'); if (old) old.remove();
    ui.timer = setInterval(() => { if (ui.steps[ui.view] < ui.rows.length - 1) showStep(ui.steps[ui.view] + 1, true); else stop(); }, 2600);
  });

  /* ---------- 系统总览：正交走线，标签只放在直线段旁 ---------- */
  function buildOverview() {
    const back = $('layer-back'), heads = $('layer-heads'), rowsL = $('layer-rows');
    back.replaceChildren(); heads.replaceChildren(); rowsL.replaceChildren();
    ui.band = [0, 900]; ui.bandY = [176, 444];
    ui.tall = false; heads.removeAttribute('transform');
    $('diagram').setAttribute('viewBox', '0 0 900 640');
    $('diagram-title').textContent = '系统模型：代理层、可信授权执行边界、业务与证据';
    svgEl('rect', {class: 'band', x: 0, y: 176, width: 900, height: 268, rx: 14}, back);
    svgText(back, {class: 'layer-name', x: 0, y: 22}, '代理层');
    svgText(back, {class: 'layer-note', x: 58, y: 22}, '只提出意图，横向箭头是任务交接');
    svgText(back, {class: 'tap-hint', x: 900, y: 22, 'text-anchor': 'end'}, '点击参与方查看职责');
    svgText(back, {class: 'layer-name', x: 16, y: 430}, '可信授权执行边界');
    svgText(back, {class: 'layer-note', x: 146, y: 430}, '在模型之外决定能否执行');
    svgText(back, {class: 'layer-name', x: 0, y: 610}, '业务与证据');
    svgText(back, {class: 'layer-note', x: 88, y: 610}, '合成业务，无真实付款');

    const C = {};
    C.user = chip(heads, 'user', 100, 44, '用户', 'OIDC 登录');
    C.planner = chip(heads, 'planner', 330, 44, '统筹代理', 'planner#key-1', 'violet');
    C.selector = chip(heads, 'selector', 570, 44, '选品代理', 'selector#key-1', 'teal');
    C.executor = chip(heads, 'executor', 810, 44, '执行代理', 'executor#key-1', 'teal');
    C.as = chip(heads, 'as', 120, 272, '授权服务器', 'AS / OIDC OP');
    C.gateway = chip(heads, 'gateway', 470, 272, '执行网关', 'GM-MVP-1 验权');
    C.ledger = chip(heads, 'ledger', 810, 272, '授权与预算库', 'PostgreSQL');
    C.cosign = chip(heads, 'cosign', 470, 368, '双域共签', '授权域 × 执行域 · SM2');
    C.x402 = chip(heads, 'x402', 110, 520, '支付适配 x402', '本机固定演示', null, false);
    C.downstream = chip(heads, 'downstream', 360, 520, '模拟订单与通知', '幂等执行');
    C.audit = chip(heads, 'audit', 810, 520, '回执与审计', 'SM2 回执 / 检查点');

    const path = (d, cls, mk) => { const p = svgEl('path', {d, class: 'edge ' + (cls || '')}, back); if (mk) p.setAttribute('marker-end', `url(#${mk})`); return p; };
    // 任务交接
    path(`M${C.user.x2 + 4},70 H${C.planner.x1 - 6}`, '', 'a-mute');
    path(`M${C.planner.x2 + 4},70 H${C.selector.x1 - 6}`, '', 'a-mute');
    path(`M${C.selector.x2 + 4},70 H${C.executor.x1 - 6}`, '', 'a-mute');
    // 用户 → AS：竖直下行
    path('M100,96 V266', '', 'a-mute');
    label(rowsL, 112, 206, 'OIDC 登录', 'lab left', 112);
    label(rowsL, 112, 224, '用户同意', 'lab left', 112);
    label(rowsL, 112, 242, '授权码 + PKCE', 'lab mono left', 112);
    // AS 签发：从 AS 右侧出发的总线，向三个代理各分一支
    const busX = 236, busY = 150;
    path(`M${C.as.x2},298 H${busX} V${busY} H790`, 'gold');
    for (const x of [330, 570, 790]) path(`M${x},${busY} V100`, 'gold', 'a-gold');
    label(rowsL, 450, busY - 8, 'AS 统一签发各级令牌', 'lab gold', 450);
    label(rowsL, 450, busY + 18, '授权码交换 + Token Exchange（RFC 8693）', 'lab mono', 450);
    // 执行代理 → 网关：L 形
    path(`M836,96 V226 H490 V266`, 'main', 'a-accent');
    label(rowsL, 660, 218, 'AGPoP 令牌 + AG-Proof', 'lab mono', 660);
    label(rowsL, 660, 244, 'SM2 签名，SM3 绑定请求体', 'lab mute', 660);
    // 网关 → 库
    path(`M${C.gateway.x2 + 4},298 H${C.ledger.x1 - 6}`, 'main', 'a-accent');
    for (const k of ['as', 'gateway', 'ledger', 'cosign']) C[k].g.classList.add('core');
    const gl = (C.gateway.x2 + C.ledger.x1) / 2;
    label(rowsL, gl, 290, '接受事务', 'lab', gl);
    label(rowsL, gl, 318, '撤销、预算、防重放', 'lab mute', gl);
    // 双域共签：授权域在 AS 侧独立核验后才出份额，合成的 SM2 批准随请求进入网关
    path('M470,368 V328', 'main', 'a-accent');
    path(`M120,${C.as.bottom} V${C.cosign.cy} H${C.cosign.x1 - 6}`, '', 'a-mute');
    label(rowsL, 132, C.cosign.cy - 8, '授权域核验后出份额', 'lab mute left', 132);
    // 网关 → 下游：先向左，再竖直下行
    path(`M${C.gateway.x1 - 4},298 H360 V514`, '', 'a-mute');
    label(rowsL, 372, 476, '不可变意图，幂等执行', 'lab mute left', 372);
    // 下游 → x402（本机固定演示，公网未部署）
    path(`M${C.downstream.x1 - 4},546 H${C.x402.x2 + 6}`, 'planned', 'a-mute');
    // 库 → 审计
    path('M810,326 V514', '', 'a-mute');
    label(rowsL, 798, 476, '签名回执与检查点', 'lab mute right', 798);
  }

  /* ---------- 左栏：每章说明 ---------- */
  function pairsList(rows, weak) {
    const dl = h('dl', 'pairs');
    for (const r of rows) {
      const ours = r[r.length - 1] === true;
      dl.append(h('dt', ours ? 'ours' : null, r[0]));
      const dd = h('dd', ours ? 'ours' : weak ? 'weak' : null);
      for (let i = 1; i < r.length; i++) {
        if (r[i] === true) continue;
        if (/^(RFC \d+|GM-MVP-1)$/.test(r[i])) dd.append(h('span', 'rfc', r[i]));
        else dd.append(document.createTextNode(r[i]));
      }
      dl.append(dd);
    }
    return dl;
  }

  /* 左栏小节：标题 + 内容，所有页面共用 */
  const section = (title, ...nodes) => { const d = h('div', 'sec'); d.append(h('h2', 'sub', title), ...nodes); return d; };
  function limits(text) {
    const d = h('div', 'limits');
    d.append(h('h2', 'sub', '局限与边界'), h('p', null, text));
    return d;
  }

  /* 总览：四种风险各对应一页，构成整场汇报的主线 */
  const RISKS = [
    ['令牌被复制', '持有者绑定：没有私钥，令牌用不了', 's1'],
    ['代理多要权限', '委托收窄：子授权只能更小', 's3'],
    ['用户中途撤销', '动态撤销：接受时复核当前状态', 's6'],
    ['网关本身被攻破', '双域共签：授权域核验后才出份额', 'cosign'],
  ];

  function briefFor(view) {
    const box = $('brief-main'); box.replaceChildren();
    const ch = chapterOf(view);
    const group = ch && (ch.groups.find(([, vs]) => vs.includes(view)) || [''])[0];
    const kicker = h('p', 'kicker', ch ? ch.name + (group ? ' · ' + group : '') : '');
    if (SCENES[view]) {
      const sc = SCENES[view];
      box.append(kicker, h('h1', null, sc.title), h('p', 'lede', sc.lede));
      box.append(section('用到的协议', pairsList(sc.stack)));
      box.append(section('与原有做法相比', pairsList(sc.delta, true)));
      box.append(limits(sc.honest));
      const proof = h('div', 'proof sec'); proof.id = 'proof'; box.append(proof);
      ui.lastProofKey = ''; renderProof();
    } else if (view === 'overview') {
      box.append(kicker, h('h1', null, '一笔采购，经过谁的手'),
        h('p', 'lede', '三个代理接力完成采购。它们只提出请求；能不能执行，由可信边界里的服务决定。'));
      const list = h('div', 'risks');
      for (const [risk, fix, v] of RISKS) {
        const b = h('button', 'risk-row'); b.type = 'button';
        b.title = '转到：' + chapterOf(v).name + ' · ' + SCENES[v].short;
        b.append(h('span', 'risk', risk), h('span', 'fix', fix), h('span', 'go', '→'));
        b.addEventListener('click', () => setView(v));
        list.append(b);
      }
      box.append(section('要防住的四种风险', list));
      box.append(section('每条连线用的协议', pairsList([
        ['用户↔AS', 'OIDC 登录与用户同意；授权码 + PKCE ', 'RFC 7636'],
        ['代理↔AS', 'Token Exchange ', 'RFC 8693', '，两级委托，AS 统一签发'],
        ['代理→网关', 'AGPoP 令牌 + AG-Proof；SM2 签名，SM3 摘要'],
        ['网关↔库', '接受事务内复核撤销、共享预算与防重放'],
        ['授权域↔网关', '双域协同 SM2 签名，授权域核验后才出份额'],
        ['网关→下游', '不可变意图、幂等执行、签名回执'],
      ])));
      box.append(limits('合成采购业务，无真实付款；代理为确定性实现，未接入真实大模型。双域共签为半诚实两方、同一主机；x402 只用本机测试链。各页逐项写明边界。'));
    } else {
      box.append(kicker, h('h1', null, '用真实运行核对'),
        h('p', 'lede', '前面各页的过程图是示意推演。这里只显示本机真实运行留下的结果，或者现场再跑一次。'));
      const toc = h('div', 'toc'); toc.id = 'evidence-toc';
      box.append(section('本页内容', toc));
      box.append(section('怎么读这些记录', pairsList([
        ['现场运行', '真实启动隔离环境执行测试；场景约 1–3 分钟，完整采购约 5–8 分钟'],
        ['记录回放', '读取之前真实运行保存的断言记录，并校验快照摘要'],
        ['失败', '运行失败如实显示，不会被当成成功'],
        ['前提', '本机服务已启动，Docker Desktop 正在运行'],
      ], true)));
      const conn = h('p', 'honest'); conn.id = 'conn-line'; box.append(conn);
      renderConn(); renderToc();
    }
  }

  /* 左栏顶部的章内导航：只有一页的章节不显示 */
  function renderSubnav(view) {
    const nav = $('subnav'), ch = chapterOf(view);
    nav.replaceChildren();
    const pages = ch ? ch.groups.flatMap(([, vs]) => vs) : [];
    nav.hidden = pages.length < 2;
    if (nav.hidden) return;
    for (const [name, vs] of ch.groups) {
      const row = h('div', 'subnav-row');
      if (name) row.append(h('span', 'subnav-k', name));
      for (const v of vs) {
        const b = h('button', null, SCENES[v].short); b.type = 'button';
        b.setAttribute('aria-current', String(v === view));
        b.addEventListener('click', () => setView(v));
        row.append(b);
      }
      nav.append(row);
    }
  }

  /* ---------- 章节切换 ---------- */
  function setView(view, push) {
    if (view === 'more') view = 's2'; // 旧链接兼容
    const asChapter = CHAPTERS.find(c => c.k === view);
    if (asChapter && !VIEWS.includes(view)) view = ui.lastIn[asChapter.k] || asChapter.groups[0][1][0];
    if (!VIEWS.includes(view)) view = 'overview';
    stop();
    ui.view = view;
    const ch = chapterOf(view);
    ui.lastIn[ch.k] = view;
    if (ui.steps[view] == null) ui.steps[view] = 0;
    ui.follow = false;
    closeModule(true);
    document.querySelectorAll('#chapters button').forEach(b => b.setAttribute('aria-current', String(b.dataset.chapter === ch.k)));
    const isScene = !!SCENES[view], isRec = view === 'evidence';
    // SVG 元素不支持 hidden 属性的 IDL 写法，必须用 attribute 切换
    $('diagram').toggleAttribute('hidden', isRec);
    $('records').hidden = !isRec;
    $('ctrl').hidden = !isScene;
    $('count').hidden = !isScene;
    renderSubnav(view);
    briefFor(view);
    $('brief').scrollTop = 0;
    if (isScene) { buildScene(view); showStep(ui.steps[view], false); }
    else if (view === 'overview') {
      buildOverview(); setSource('model');
      $('cap').replaceChildren(h('strong', null, '系统模型'), h('span', null, '代理只提出意图；令牌由 AS 统一签发，授权域与网关在接受前做确定性检查。'));
    } else {
      ui.lastRecordsKey = ''; renderRecords(); setSource('real');
      $('cap').replaceChildren(h('strong', null, '运行证据'), h('span', null, '这里的结果全部来自本机服务；没有读到的内容显示为未读取。'));
    }
    if (push !== false && location.hash !== '#' + view) { try { history.replaceState(null, '', '#' + view); } catch (e) { /* 预览环境可能不允许 */ } }
  }
  /* 右上角来源：三种来源始终并列，当前这一屏的来源点亮，旁边一句说明 */
  function setSource(kind) {
    const map = {
      real: [['live', 'replay'], '结果来自本机服务'],
      live: [['live'], '事件来自本机服务'],
      replay: [['replay'], '事件来自保存的运行'],
      model: [[], '架构图，不是运行结果'],
      design: [['illus'], '真实结果见左栏'],
      illus: [['illus'], '未连接事件流'],
    }[kind] || [['illus'], ''];
    $('source').className = 'source src-' + kind;
    $('source').querySelectorAll('.src-pill').forEach(p => p.classList.toggle('on', map[0].includes(p.dataset.src)));
    $('source-text').textContent = map[1];
  }
  document.querySelectorAll('#chapters button').forEach(b => b.addEventListener('click', () => setView(b.dataset.chapter)));

  /* ---------- 模块说明 ---------- */
  function openModule(k) {
    const m = MODULES[k]; if (!m) return;
    ['m-name', 'm-id', 'm-problem', 'm-caller', 'm-input', 'm-check', 'm-output', 'm-limit'].forEach((id, i) => { $(id).textContent = m[i]; });
    $('brief-main').hidden = true; $('module').hidden = false;
    document.querySelectorAll('.who').forEach(w => w.classList.toggle('selected', w.dataset.k === k));
    $('back').focus({preventScroll: true});
  }
  function closeModule(silent) {
    $('brief-main').hidden = false; $('module').hidden = true;
    document.querySelectorAll('.who').forEach(w => w.classList.remove('selected'));
    if (!silent) $('brief').scrollTop = 0;
  }
  $('back').addEventListener('click', () => closeModule());

  // 数字键 1–5 切换章节，[ ] 在章内翻页
  const KEYS = Object.fromEntries(CHAPTERS.map((c, i) => [String(i + 1), c.k]));
  function pageStep(d) {
    const pages = chapterOf(ui.view).groups.flatMap(([, vs]) => vs);
    const i = pages.indexOf(ui.view) + d;
    if (i >= 0 && i < pages.length) setView(pages[i]);
  }
  document.addEventListener('keydown', e => {
    const onCtl = e.target.closest && e.target.closest('button,[role=button]');
    if (e.key === 'Escape' && !$('module').hidden) { closeModule(); return; }
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 'ArrowRight') step(1);
    else if (e.key === 'ArrowLeft') step(-1);
    else if (e.key === ' ' && !onCtl && SCENES[ui.view]) { e.preventDefault(); $('play').click(); }
    else if (e.key === '[' || e.key === ']') pageStep(e.key === ']' ? 1 : -1);
    else if (KEYS[e.key]) setView(KEYS[e.key]);
  });

  /* ======================================================================
   * 本机服务：只读状态 + 固定动作 + 事件流
   * ==================================================================== */
  const job = () => (ui.state && ui.state.job) || null;
  const busy = () => ui.posting || (job() && job().status === 'running');
  const canAct = () => ui.connected && !!ui.token && !busy();
  const catalog = () => (ui.state && Array.isArray(ui.state.catalog) && ui.state.catalog.length) ? ui.state.catalog : CATALOG_FALLBACK;
  const results = () => (ui.state && ui.state.scenario_results) || {};

  function banner(text) { const b = $('banner'); b.textContent = text; b.hidden = !text; }

  async function refresh() {
    try {
      const r = await fetch('/api/state', {cache: 'no-store'});
      if (!r.ok) throw new Error('state');
      ui.state = await r.json();
      ui.connected = true;
    } catch (e) {
      ui.connected = false;
    }
    await pollFeed();
    renderProof(); renderRecords(); renderConn(); renderToc();
  }

  /*
   * 事件流：job 里出现 run_id 后，按 after_seq 增量拉取 /api/runs/{run_id}/events。
   * 接口未实现（404）时安静降级为示意，不报错；断线时画面停在最后收到的事件。
   */
  async function pollFeed() {
    const j = job();
    if (j && j.run_id && j.scenario_id && (!ui.feed || ui.feed.runId !== j.run_id)) {
      ui.feed = {runId: j.run_id, scenarioId: j.scenario_id, store: new EventStore(j.run_id), status: 'polling', source: null, terminal: false, complete: true};
      ui.feeds.set(j.scenario_id, ui.feed);
    }
    for (const f of ui.feeds.values()) {
      if (f.status !== 'polling' || !ui.connected) continue;
      try {
        const r = await fetch(`/api/runs/${encodeURIComponent(f.runId)}/events?after_seq=${f.store.nextAfterSeq()}&limit=200`, {cache: 'no-store'});
        if (r.status === 404) { f.status = 'unsupported'; continue; }
        if (!r.ok) throw new Error('events');
        const data = await r.json();
        f.store.add(data.events || []);
        if (SOURCES.includes(data.source)) f.source = data.source;
        f.terminal = data.terminal === true;
        f.complete = data.complete !== false;
        if (f.terminal && !f.store.gaps().length) f.status = 'done';
      } catch (e) {
        /* 保留已收到的事件，下一轮再试 */
      }
    }
    maybeRebuild();
  }
  function maybeRebuild() {
    const sc = SCENES[ui.view];
    if (!sc) return;
    const src = sceneEvents(ui.view);
    const key = ui.view + ':' + src.source + ':' + src.events.filter(e => !NOT_DRAWN.has(e.event_type)).length;
    if (key === ui.sceneKey) { if (src.feed) showStep(ui.steps[ui.view] || 0, false); return; }
    const wasAtEnd = (ui.steps[ui.view] || 0) >= ui.rows.length - 1;
    buildScene(ui.view);
    const follow = src.feed && (ui.follow || wasAtEnd);
    showStep(follow ? ui.rows.length - 1 : (ui.steps[ui.view] || 0), follow);
  }

  async function start(path) {
    if (!canAct()) return;
    ui.posting = true; ui.actionError = ''; banner('');
    renderProof(); renderRecords();
    try {
      const r = await fetch('/api/' + path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Demo-Token': ui.token}, body: '{}'});
      if (!r.ok) throw new Error(r.status === 409 ? '已有任务正在进行，或没有可验证的成功记录。' : '这次动作没有被本机服务接受，请刷新页面后重试。');
      ui.follow = true;
    } catch (e) {
      ui.actionError = e.message || '无法连接本机服务。';
      banner(ui.actionError);
    }
    ui.posting = false;
    await refresh();
  }

  function jobText(j) {
    if (!j) return '';
    const what = {run: '完整采购演示', verify: '离线验证', 'scenario-run': '场景现场运行', 'scenario-replay': '场景记录回放', 'threshold-run': '门限采购固定演示', 'x402-run': 'x402 采购固定演示', 'cosm2-run': '双域共签采购固定演示'}[j.action] || '任务';
    const st = {running: '进行中', success: '已完成', failed: '未成功'}[j.status] || '状态未确认';
    const el = Number.isFinite(j.elapsed) ? `，已用 ${Math.floor(j.elapsed / 60)} 分 ${j.elapsed % 60} 秒` : '';
    const sc = j.scenario_id ? '（' + ((catalog().find(c => c.id === j.scenario_id) || {}).title || j.scenario_id) + '）' : '';
    const exit = j.status === 'failed' ? `；退出码 ${j.native_exit == null ? '未采集' : j.native_exit}` : '';
    return `${what}${sc}${st}：${j.stage || ''}${el}${exit}`;
  }
  function resultLine(res) {
    if (!res) return ['none', '尚未读取'];
    if (res.status === 'passed') return ['ok', '断言通过'];
    if (res.status === 'failed') return ['bad', '断言失败'];
    if (res.status === 'skipped') return ['none', '已跳过'];
    return ['none', '状态未确认'];
  }
  const modeText = res => !res ? '' : res.mode === 'current_run' ? '本次现场运行' : res.mode === 'history_replay' ? '记录回放' : '来源未确认';
  const timeText = v => {
    if (v == null) return '未采集';
    const d = typeof v === 'number' ? new Date(v * 1000) : new Date(v);
    return isNaN(d) ? '未采集' : d.toLocaleString('zh-CN', {hour12: false});
  };

  function actionButtons(item, compact) {
    const wrap = h('div', compact ? 'btns' : 'actions');
    const rep = h('button', 'btn', '读取记录'); rep.type = 'button';
    rep.disabled = !canAct() || !item.history_available;
    rep.addEventListener('click', () => start(`scenarios/${encodeURIComponent(item.id)}/replay`));
    const run = h('button', 'btn primary', '现场运行'); run.type = 'button';
    run.disabled = !canAct() || !item.run_available;
    run.addEventListener('click', () => start(`scenarios/${encodeURIComponent(item.id)}/run`));
    wrap.append(rep, run);
    return wrap;
  }

  /* 门限与 x402 的本机固定演示：场景页左栏和"真实记录"页共用同一套呈现 */
  const FIXED_DEMOS = {
    cosign: {
      title: '双域共签', action: 'cosm2-run',
      idle: '现场运行使用真实 AS 授权链和双域共签，固定六用例；需要 Docker Desktop 与固定运行镜像。右侧为示意推演。',
      summary: d => `订单 ${d.orders}，批准 ${d.approvals}，操作 ${d.operations}；残留资源 ${d.resources_remaining}`,
      names: {
        'cosign-valid-one-order': '有效共签，只下一单', 'missing-approval': '缺少共签批准',
        'exec-domain-alone': '只有执行域，签不出有效签名', 'tampered-amount': '共签后篡改金额',
        'revoked-before-cosign': '已撤销，授权域拒绝出份额', 'revoked-after-cosign': '共签后撤销，接受事务拒绝',
      },
    },
    threshold: {
      title: '对照：旧版 FROST', action: 'threshold-run',
      idle: '有效批准只下一单；缺批准、份额不足、伪造、篡改、撤销都会被拒绝。需要 Docker Desktop，临时数据库会自动准备和清理。',
      summary: d => `订单 ${d.orders}，批准绑定 ${d.approvals}，操作 ${d.operations}；残留资源 ${d.resources_remaining}`,
      names: {
        'missing-approval': '缺少批准', 'insufficient-and-duplicate': '只有一份或重复份额', 'fake-signature': '伪造组签名',
        'valid-approval-one-order': '有效批准，只下一单', 'tampered-amount': '批准后篡改金额', 'revoked-ancestor': '批准有效但祖先已撤销',
        'expired-approval': '批准已过期',
      },
    },
    x402: {
      title: 'x402 支付', action: 'x402-run',
      idle: '正常付款只结算一次；重放不重复付款；旧版批准、超预算、篡改支付都会被拒绝。首次运行要构建隔离镜像，可能需要几分钟。',
      summary: d => `订单 ${d.orders}，支付 ${d.payments}，链上交易 ${d.transactions}，操作 ${d.operations}；残留资源 ${d.resources_remaining}`,
      names: {
        'paid-flow-settles-once': '正常付款，只结算一次', 'replay-does-not-pay-twice': '重放不重复付款',
        'v2-approval-refused': '不含支付摘要的旧版批准被拒绝', 'over-budget-refused': '超出资产预算被拒绝',
        'unknown-recovery-same-nonce': '结果未知后用同一 nonce 恢复', 'forged-payment-refused': '篡改的支付证明不能结算',
      },
    },
  };
  const ms = v => (Number.isFinite(v) ? v.toFixed(2) + ' ms' : '未采集');
  function fixedBlock(kind) {
    const F = FIXED_DEMOS[kind], demo = (ui.state && ui.state[kind]) || null, tj = job();
    const out = [];
    const line = h('p', 'proof-line');
    if (!ui.connected) {
      line.append(h('span', 'none', '本机服务未连接'), h('small', null, '过程图仍可讲解；运行固定演示需要启动本机服务。'));
      return [line];
    }
    if (demo) {
      line.append(h('span', demo.passed ? 'ok' : 'bad', demo.passed ? '全部符合预期' : '有用例不符合预期'),
        h('small', null, `${kind === 'cosign' ? (demo.source === 'current-run' ? '本次现场运行' : '保存结果回放') : '本次现场运行'}，${timeText(demo.completed_at)}；${F.summary(demo)}`));
    } else {
      line.append(h('span', 'none', '尚未运行'), h('small', null, F.idle));
    }
    const actions = h('div', 'actions');
    const btn = h('button', 'btn primary', demo ? '重新运行' : '现场运行'); btn.type = 'button';
    btn.disabled = !canAct() || (kind === 'cosign' && !ui.state?.cosign_ready);
    if (kind === 'cosign' && !ui.state?.cosign_ready) btn.textContent = '执行入口未就绪（缺少本机依赖）';
    btn.addEventListener('click', () => { start((kind === 'cosign' ? 'cosm2' : kind) + '/run'); });
    actions.append(btn);
    out.push(line, actions);
    if (kind === 'cosign') {
      out.push(h('p', 'honest', (ui.state && ui.state.cosign_status) || F.idle));
      if (demo) {
        out.push(h('p', 'code', `run_id: ${demo.run_id}`),
          h('p', 'honest', `来源：${demo.source_label}；原 completed_at: ${demo.completed_at}。右侧始终为示意推演。`),
          h('p', 'honest', `本次三轮耗时（单次运行，非统计结果）：第一轮 ${ms(demo.timing_ms.round1)}；含检查第二轮 ${ms(demo.timing_ms.round2_with_checks)}；含验签第三轮 ${ms(demo.timing_ms.round3_with_verify)}`));
      }
    }
    if (demo && Array.isArray(demo.cases)) {
      const ul = h('ul', 'case-list');
      for (const c of demo.cases) {
        const li = h('li');
        li.append(h('span', 'cn', F.names[c.name] || c.name),
          h('span', 'pill ' + (c.passed ? 'ok' : 'bad'), c.passed ? '符合预期' : '不符合预期'),
          h('span', 'code', [c.http_status, c.code].filter(v => v != null && v !== '').join(' ') || '—'));
        ul.append(li);
      }
      out.push(ul);
    }
    if (tj && (tj.action === F.action)) out.push(h('p', 'job' + (tj.status === 'failed' ? ' failed' : ''), jobText(tj)));
    return out;
  }

  /* 场景页左栏的"真实记录"小节 */
  function renderProof() {
    const box = $('proof'); if (!box || !SCENES[ui.view]) return;
    const sc = SCENES[ui.view];
    if (ui.view === 'cosign') {
      box.replaceChildren(h('h2', 'sub', '运行证据'), ...fixedBlock('cosign'));
      return;
    }
    if (!sc.catalogId) {
      const st = ui.state || {}, tj = job();
      const key = JSON.stringify([ui.view, ui.connected, !!ui.token, ui.posting, st[sc.fixed], tj && [tj.status, tj.stage, tj.elapsed, tj.action]]);
      if (key === ui.lastProofKey) return;
      ui.lastProofKey = key;
      box.replaceChildren(h('h2', 'sub', '运行证据'), ...fixedBlock(sc.fixed));
      return;
    }
    const id = sc.catalogId;
    const item = catalog().find(c => c.id === id) || {id, title: id};
    const res = results()[id];
    const j = job();
    const key = JSON.stringify([ui.connected, !!ui.token, ui.posting, item, res, j && [j.status, j.stage, j.elapsed, j.scenario_id]]);
    if (key === ui.lastProofKey) return;
    ui.lastProofKey = key;
    box.replaceChildren(h('h2', 'sub', '运行证据'));
    const line = h('p', 'proof-line');
    if (!ui.connected) {
      line.append(h('span', 'none', '本机服务未连接'), h('small', null, '过程图仍可讲解；真实记录需要启动本机服务。'));
    } else {
      const [cls, txt] = resultLine(res);
      line.append(h('span', cls, txt));
      if (res) line.append(h('small', null, `${modeText(res)}，${timeText(res.completed_at)}；通过 ${res.passed ?? '未采集'} / ${res.total ?? '未采集'}`));
    }
    box.append(line, actionButtons(item));
    if (j && (j.scenario_id === id || j.status === 'running')) box.append(h('p', 'job' + (j.status === 'failed' ? ' failed' : ''), jobText(j)));
  }

  function renderConn() {
    const c = $('conn-line'); if (!c) return;
    if (ui.connected && ui.state && ui.state.read_only) {
      c.textContent = '公网只读展示：可浏览页面和真实记录；现场任务由演示者在本机启动，结果会自动更新。';
      return;
    }
    c.textContent = ui.connected ? '本机服务：已连接。' : '本机服务：未连接。请在仓库根目录运行 python3 tools/teacher_demo_server.py，然后打开 http://127.0.0.1:8765/';
  }

  /* "运行证据"视图：分节顺序与顶栏章节一致 */
  const REC_SECTIONS = [
    ['rec-flow', '总览', '完整采购流程'],
    ['rec-scenes', '基础防线', '安全场景'],
    ['rec-cosign', '核心机制', '双域共签'],
    ['rec-threshold', '核心机制', '对照：旧版 FROST'],
    ['rec-x402', '扩展', 'x402 支付'],
  ];
  const recHead = (sec, id) => {
    const [, tag, title] = REC_SECTIONS.find(r => r[0] === id);
    sec.id = id;
    const h3 = h('h3'); h3.append(h('span', 'tag', tag), document.createTextNode(title));
    return h3;
  };
  /* 按章内分组排列场景；目录里出现未知用例时归入"其他"，不丢弃 */
  function sceneGroups() {
    const byCatalog = new Map(Object.values(SCENES).filter(sc => sc.catalogId).map(sc => [sc.catalogId, sc]));
    const defense = CHAPTERS.find(c => c.k === 'defense');
    const items = catalog(), used = new Set();
    const groups = defense.groups.map(([name, vs]) => [name, vs.map(v => items.find(it => it.id === SCENES[v].catalogId)).filter(Boolean)]);
    groups.forEach(([, its]) => its.forEach(it => used.add(it.id)));
    const rest = items.filter(it => !used.has(it.id));
    if (rest.length) groups.push(['其他', rest]);
    return groups.map(([name, its]) => [name, its.map(it => [it, byCatalog.get(it.id)])]);
  }

  function renderRecords() {
    const box = $('records'); if (!box || ui.view !== 'evidence') return;
    const st = ui.state || {};
    const key = JSON.stringify([ui.connected, !!ui.token, ui.posting, st.catalog, st.scenario_results, st.job, st.history, st.live, st.verification, st.threshold, st.x402, st.cosign, st.cosign_status, st.cosign_ready, [...ui.openRecords]]);
    if (key === ui.lastRecordsKey) return;
    ui.lastRecordsKey = key;
    const keepScroll = box.scrollTop;
    box.replaceChildren();
    const j = job();

    /* 1. 完整采购流程与离线验证 */
    const s2 = h('section');
    const result = st.live || st.history;
    s2.append(recHead(s2, 'rec-flow'), h('p', 'hint', result ? (st.live ? '最近一次现场运行。' : '历史记录回放，不是本次运行。') + '运行编号 ' + result.run_id : '还没有可读取的成功记录；这里不会显示预设结果。'));
    if (result) {
      const facts = h('div', 'facts');
      const root = result.counters && result.counters[0];
      const fact = (v, t) => { const s = h('span'); s.append(h('b', null, v), document.createTextNode(t)); facts.append(s); };
      fact(root ? fen(root[4]).replace(' 元', '') : '未采集', ' 元已结算（根预算）');
      fact(String(result.orders), ' 单模拟订单');
      fact(String(result.notifications), ' 条固定模板通知');
      s2.append(facts);
      const table = h('table', 'chain-table');
      const head = h('tr'); ['授权层级', '额度上限', '已结算', '预留', '调用次数'].forEach(t => head.append(h('th', null, t)));
      table.append(head);
      (result.counters || []).forEach((r, i) => {
        const tr = h('tr');
        tr.append(h('td', null, ['统筹代理（根授权）', '选品代理（第一层委托）', '执行代理（第二层委托）'][i] || '第 ' + (i + 1) + ' 层'),
          h('td', 'num', fen(r[1])), h('td', 'num', fen(r[4])), h('td', 'num', fen(r[3])), h('td', 'num', `${r[6]} / ${r[2]}`));
        table.append(tr);
      });
      s2.append(table, h('p', 'hint', '三层共同约束同一笔支出，不是三个独立钱包。四项工具回执：' + ['读取申请', '读取报价', '创建模拟订单', '发送模拟通知'].map((t, i) => t + ' ' + ((result.receipts || [])[i] || '未采集')).join('，') + '。'));
    }
    const acts = h('div', 'actions');
    const run = h('button', 'btn primary', '启动一次真实演示'); run.type = 'button'; run.disabled = !canAct();
    run.addEventListener('click', () => start('run'));
    const ver = h('button', 'btn', '验证原件与篡改副本'); ver.type = 'button'; ver.disabled = !canAct() || !result;
    ver.addEventListener('click', () => start('verify'));
    acts.append(run, ver);
    s2.append(acts);
    if (j && ['run', 'verify'].includes(j.action)) s2.append(h('p', 'job' + (j.status === 'failed' ? ' failed' : ''), jobText(j)));
    const v = st.verification;
    if (v) {
      const line = h('p', 'verify-line');
      line.append(document.createTextNode(`最近一次离线验证（${v.run_id || '运行记录'}${v.verified_at ? '，' + timeText(v.verified_at) : ''}）：`),
        h('span', v.original && v.original.exit === 0 ? 'ok' : 'bad', v.original && v.original.exit === 0 ? '原件通过' : '原件未通过'),
        document.createTextNode('，'),
        h('span', v.tampered && v.tampered.exit === 2 ? 'ok' : 'bad', v.tampered && v.tampered.exit === 2 ? '篡改副本被拒绝' : '篡改副本未被拒绝'));
      s2.append(line);
      const names = {cryptographic_consistency: '密码一致性', current_auth: '当前授权', downstream_truth: '下游真实性', freshness: '新鲜度来源', history_boundary: '历史边界', anchored_prefix: '已锚定前缀', cutoff_sequence: '截止序号', tail: '未锚定尾部'};
      const dl = h('dl', 'rec-detail');
      for (const [k, val] of Object.entries(v.boundaries || {})) dl.append(h('dt', null, names[k] || k), h('dd', 'code', String(val)));
      s2.append(dl, h('p', 'hint', '一致性通过只说明证据与信任材料相符；当前授权仍未知，下游效果依赖见证，历史可能存在缺口。'));
    }

    /* 2. 安全场景，按"三道防线 / 更多保障"分组 */
    const s1 = h('section');
    s1.append(recHead(s1, 'rec-scenes'), h('p', 'hint', '每一项对应一组真实的集成测试。"读取记录"回放之前保存的结果，"现场运行"重新执行一次；"看过程"打开对应讲解页。'));
    if (j && ['scenario-run', 'scenario-replay'].includes(j.action)) s1.append(h('p', 'job' + (j.status === 'failed' ? ' failed' : ''), jobText(j)));
    for (const [gname, rows] of sceneGroups()) {
      s1.append(h('h4', 'rec-group', gname));
      const ul = h('ul', 'rec-list');
      for (const [item, sc] of rows) {
        const li = h('li'); const row = h('div', 'rec-row');
        const res = results()[item.id];
        const [cls, txt] = ui.connected ? resultLine(res) : ['none', '未连接'];
        const t = h('div', 't', sc ? sc.short : item.title); t.append(h('small', null, item.defense || item.title || ''));
        const src = h('div', 'src');
        if (res) src.append(h('i', 'sw ' + (res.mode === 'current_run' ? 'live' : 'replay')), document.createTextNode(modeText(res)));
        const btns = actionButtons(item, true);
        if (sc) {
          const view = Object.keys(SCENES).find(k => SCENES[k] === sc);
          const see = h('button', 'btn ghost-btn', '看过程'); see.type = 'button';
          see.addEventListener('click', () => setView(view));
          btns.prepend(see);
        }
        row.append(t, h('span', 'st ' + cls, txt), src, btns);
        li.append(row);
        if (res) {
          const open = ui.openRecords.has(item.id);
          const more = h('button', 'rec-more', open ? '收起详情' : '查看详情'); more.type = 'button';
          more.addEventListener('click', () => { if (open) ui.openRecords.delete(item.id); else ui.openRecords.add(item.id); ui.lastRecordsKey = ''; renderRecords(); });
          li.append(more);
          if (open) li.append(recordDetail(item, res));
        }
        ul.append(li);
      }
      s1.append(ul);
    }

    /* 3–5. 固定演示：双域共签、FROST 对照、x402 */
    const fixed = [['rec-cosign', 'cosign', '固定六用例，真实 AS 授权链与双域共签。'], ['rec-threshold', 'threshold', '上一版 2-of-3 FROST 方案的固定用例，保留作对照。'], ['rec-x402', 'x402', '本机测试链与自建测试代币，付款意图须经双域共签批准。']];
    const secs = fixed.map(([id, kind, hint]) => {
      const sec = h('section');
      sec.append(recHead(sec, id), h('p', 'hint', hint));
      const sub = h('div', 'fixed-demo'); sub.append(...fixedBlock(kind)); sec.append(sub);
      return sec;
    });
    box.append(s2, s1, ...secs);
    box.scrollTop = keepScroll;
    renderToc();
  }

  /* 左栏目录：每节一行，状态只取自本机服务返回的数据 */
  function renderToc() {
    const toc = $('evidence-toc'); if (!toc) return;
    const st = ui.state || {};
    const fixed = d => !d ? ['none', '尚未运行'] : d.passed ? ['ok', '全部符合预期'] : ['bad', '有用例不符合预期'];
    const res = Object.values(results());
    const total = catalog().length, passed = res.filter(r => r && r.status === 'passed').length, failed = res.filter(r => r && r.status === 'failed').length;
    const status = {
      'rec-flow': st.live ? ['ok', '现场运行'] : st.history ? ['ok', '记录回放'] : ['none', '尚无记录'],
      'rec-scenes': !res.length ? ['none', '尚未读取'] : [failed ? 'bad' : 'ok', `通过 ${passed} / ${total}`],
      'rec-cosign': fixed(st.cosign), 'rec-threshold': fixed(st.threshold), 'rec-x402': fixed(st.x402),
    };
    toc.replaceChildren();
    for (const [id, tag, title] of REC_SECTIONS) {
      const b = h('button', 'toc-row'); b.type = 'button';
      const [cls, txt] = ui.connected ? status[id] : ['none', '未连接'];
      b.append(h('span', 'tag', tag), h('span', 'tt', title), h('span', 'pill ' + cls, txt));
      b.addEventListener('click', () => { const t = $(id); if (t) t.scrollIntoView({behavior: reduced ? 'auto' : 'smooth', block: 'start'}); });
      toc.append(b);
    }
  }

  function recordDetail(item, res) {
    const dl = h('dl', 'rec-detail');
    const add = (k, v, cls) => dl.append(h('dt', null, k), h('dd', cls || null, v == null || v === '' ? '未采集' : String(v)));
    add('攻击条件', item.request);
    add('可信防线', item.defense);
    add('实际观测', res.observed);
    add('预算与效果', typeof res.budget === 'string' ? res.budget : res.budget == null ? '预算数值未采集' : JSON.stringify(res.budget));
    add('断言', (res.checks || []).map(c => ({passed: '通过', failed: '失败', skipped: '跳过'}[c.status] || '未确认') + '  ' + c.name).join('\n'), 'code');
    const ev = res.evidence || {};
    add('来源', res.source_label);
    add('退出码', ev.native_exit);
    add('结果摘要', ev.xml_sha256, 'code');
    add('快照校验', ev.snapshot_verified === true ? '已核验' : ev.snapshot_verified === false ? '未通过' : '未采集');
    add('完成时间', timeText(res.completed_at) + (res.completed_at_basis ? '（' + res.completed_at_basis + '）' : ''));
    return dl;
  }

  /* ---------- 启动 ---------- */
  setView((location.hash || '#overview').slice(1), false);
  window.addEventListener('hashchange', () => { const v = location.hash.slice(1); if (v !== ui.view) setView(v, false); });
  if (location.protocol.startsWith('http')) {
    fetch('/api/session', {cache: 'no-store'}).then(r => r.ok ? r.json() : Promise.reject())
      .then(s => { ui.token = s.token || ''; })
      .catch(() => { ui.token = ''; })
      .finally(() => { refresh(); setInterval(refresh, 2000); });
  } else {
    renderProof(); renderConn();
  }
})();
