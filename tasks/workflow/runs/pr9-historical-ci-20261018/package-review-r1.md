# PR9历史验收环境修复独立包审

结论：**PACKAGE_READY**。review_kind=PACKAGE_REVIEW；本轮仅核对包的范围、授权、实际基线约束及可安全执行的门控，**不是IMPLEMENTATION_ACCEPTANCE**，未把任何尚未实施或未运行义务写为PASS。基线HEAD为eafb6f28aa87a041e149c0190b76054424f1c9cf，目标PR为https://github.com/Qdcchh/agent-guard/pull/9。本轮不启动PG、不运行测试、不修改候选源码/测试/CI/正式文档/数据，不commit/push/merge，不调用子代理。只写本package-review目录。

## 受审依据、授权与指纹

已直接读取AGENTS/AGENT、现行policy、package-v1、最新追加user-local-updates、前轮full-pg-preflight报告、local-updates inventory、现行CI和相关legacy测试/fixtures、部署compose/Dockerfile及前端README；设计/安全/验收文件与实施/审查契约作为上下文，旧阶段的长实验要求不替代本轮任务。全部输入指纹及观察到的Git状态见inputs.json。

|冻结输入|开始SHA256|结束SHA256|
|---|---|---|
|package-v1.md|44a9987e9405c6f5840e5d3fbe77aafcb32d36e3962d444a73c7b1bf875b0d27|44a9987e9405c6f5840e5d3fbe77aafcb32d36e3962d444a73c7b1bf875b0d27|
|current-policy.md|ac70afd134cd1c83998a12602b0b781cc6c66b1fc11729244debd17b1022e14d|ac70afd134cd1c83998a12602b0b781cc6c66b1fc11729244debd17b1022e14d|
|AGENT.md|fd7a38b4ba1e0fe74d52cd77aa4fa6da1ffa9040f6280e8270f5cdc13f160862|fd7a38b4ba1e0fe74d52cd77aa4fa6da1ffa9040f6280e8270f5cdc13f160862|
|user-local-updates.md|d04f9039b4a1e8b04b36d0e9a5f790e4cbae2693c6a630e2abf7dcd5120a77e7|d04f9039b4a1e8b04b36d0e9a5f790e4cbae2693c6a630e2abf7dcd5120a77e7|

以上四项首读和结束复算完全相同。前轮报告SHA256=7570c4ec49b9fda0a46aeeb4a80861b92e327c743079f42cc3088f627b940816；本地更新inventory SHA256=68d0ae80dd8808ef2fed46986c2f62eef9a27219474d464c2f47e56830789278。

任务所传真人选择“先修复并补齐历史验收环境，CI通过后再合并”与包/policy一致，授权必要适配、真实装配、可复现输入及root唯一发布。最新真人“本地文档与前端一并合并”通过独立追加输入纳入P9-11；它按时间覆盖包/policy中旧的“style.css/docx/TeX不提交”字样，仅对明确列出的CSS、03汇报docx、main.pdf生效。其他dirty/untracked继续受保护，aux/out/synctex.gz保留本地而不入Git。原包未修改，无需把追加输入误当包篡改；最终实施候选须同时冻结两份输入。

## P9-01..11完整包审矩阵

下表“充分”指包义务与门控充分，实际实施结果全部NOT_RUN。

|ID|独立静态核查与执行义务|包审|
|---|---|---|
|P9-01|原前轮记录确实为6839收集、仅133执行且有中断，不能当完整回归。包保留全部原集成及普通非PG；最终必须证明原节点完整保留、无删除/skip/弱化状态/预算/幂等/证据断言。新增测试可以增加总数，不能用改计数掩盖原节点缺失。|充分；NOT_RUN|
|P9-02|tests/integration/test_a31_inherited_trusted_material.py:32真实存在四参shim；与HTTP第五approval不兼容。最小测试适配签名并显式拒绝非空approval，仍走真实query、回滚、503/no-store/重放断言，整文件真实PG复验，符合修复范围。|充分；NOT_RUN|
|P9-03|原CI只装配一个基础DSN；legacy audit和证据目录前提缺失属真实环境缺口。包要求独占authority/downstream/audit域、独立连接/事务及证据目录，部署按原三PG要求；不得把同事务或共享业务DSN当替代。|充分；NOT_RUN|
|P9-04|test_a32_joint_tls.py:71-142要求真实来源/成员SHA、10000独立操作/完成、原拒绝以及30009 journal、668 batches、203285 objects、291623992 raw bytes、439169636 wire bytes、原首个越界点和NOT_ASSERTED标志。a32_joint.count_original_capacity读取实际原生行、校验摘要并重新编码计数。包明确保留全部数字/边界及真实性，不承诺已解决重建。可以本轮真实生成而不用私密硬编码旧路径，但必须满足原断言并证明来源；不能随手生成JSON冒称原历史，或修改预期过关。必要迁移原档案必须保持bytes/SHA与来源映射，并先检查秘密/公开资格。clean checkout重建/安全取得仍是实施硬门，技术未解不构成本包虚假完成。|充分；NOT_RUN|
|P9-05|a33_roles.py:100-150含source/wheel非editable安装、当前模块对照；:697-725要求12个不同fullID及owner/run/project标签，:739起必须真final资源。clean_deploy.py:159起要求三域verify-full且三个不同host；并校验完整JUnit无fail/error/skip。提供真实当前资源可绕开旧S0历史指纹分支，但必须额外建立当前源→build→运行安装绑定，不能只设置假manifest关闭校验。包要求全角色/部署/场景/注册/故障及source/wheel实跑，义务未减。|充分；NOT_RUN|
|P9-06|允许完整套件后续真实失败的最小修复，禁止更改18迁移/安全语义。若触及生产语义先冻结契约；若发现真正超出本轮范围的前提，必须显式分scope并报告，不能隐式削减测试。|充分；NOT_RUN|
|P9-07|原CI固定3.11、锁/pipcheck、Rust1.99.1 locked、Anvil SHA；包保留并补全全局Ruff/format/Node和clean checkout。必须记录真实工具链及仿真边界，旧image二进制不能冒称新源构建。前端README规定Node语法/逻辑及相关Python检查与真实浏览器验证，应作为P9-11的影响域证明。|充分；NOT_RUN|
|P9-08|包明确包审与实施独验分离；独占worker交接、全部writer STOP、源码/测试/fixtures/配置/依赖/输入完整SHA冻结后全新high完整独验，保留失败与未跑。当前capacity/deploy low仅只读分析；PACKAGE_READY不自动授予任意文件写权，由root按边界移交，CI唯一writer=root。|充分；NOT_RUN|
|P9-09|最终精确候选commit/push后，须核对PR9最新head/base和全部GitHub CI成功；pending/失败/旧head绿均不够。root以expectedSHA普通squash合并，不force、不绕保护；若head变化须重核绑定和门控。用户已授权此最终动作，包审本身绝非合并许可满足的证据。|充分；NOT_RUN|
|P9-10|随机owner/fullID核验；仅own资源清理，秘密env/keys0600、目录0700，敏感raw本地、公开显式脱敏，历史原件不改。并行dirty不得reset/clean/覆盖。需分别证明候选无秘密与自有PG/net/container/key/env归零；不能删除他人/历史留存来凑0。|充分；NOT_RUN|
|P9-11|追加准确限定style.css、03汇报docx和main.pdf成品；缓存不入Git、不改写用户内容、不把计划写成已实现。最终冻结前后核对实际SHA，若并发变化应重新盘点冻结；候选/独验/发布必须包含这三项。文档需检查内容与可读成品，前端需确认视觉、控制及现场/回放/示意来源和局限无回归。本轮仅审查此计划，不声称已完成文档/视觉验收。|充分；NOT_RUN|

## 边界与后续门控

无阻断包缺口。容量精确重建与部署供应脚本尚未实施/验证，这是实施待办，不是包审失败或行为通过。实施者须先冻结共享接口/路径/权限/清理约定，再由root串行接入CI，不能消费半成品。若无法安全取得原容量输入或真实生成满足原断言，应如实阻塞实施，不改旧数字，不发布未经检查的敏感档案，不将本包结论包装为可合并。

本轮修复全6839原集成及已存普通非PG，并保留真实测试固有的容量/部署前提。旧stage185或40000矩阵不机械导入；旧A3长期正式实验尚未正式接受这一事实保持，CI修复成功也不等于接受旧实验。真正发现必需扩大范围时单独明确，而不能借历史契约字样默默扩大任务或删减当轮义务。

本轮证据等级全部是“独立静态查证/既有报告核对”；没有独立实跑结果。原报告的6839、133与失败计数是历史记录核对，不是本轮重新收集。未读取秘密、未操作Docker/网络/PG、未创建密钥/env；本轮自有运行资源和秘密=0。现有源/测试/CI与用户dirty未写入；未开展实施、未作远端CI成功或合并状态声明。

**STOP — PACKAGE_READY，仅允许按root后续精确独占授权开始实施；完整全新IMPLEMENTATION_ACCEPTANCE及最终最新head全部CI成功仍是发布硬门。**
