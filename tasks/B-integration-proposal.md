# A/B 整合提案：迁移 lineage 与共享契约（2026-10-03）

状态：**仅提案，未授权实施。** 本文件不修改任何历史迁移 SQL、不清库、不重编号既有已应用迁移、不解决 Git 冲突、不合并 main。需 A 负责人（`Qdcchh`）与 B 共同书面确认后，在单独授权的整合阶段执行。目标 `origin/main`：`153f14e`；B 分支：`feature/fjr-B-character`（R1 代码提交 `f84da1c`，整改后 `942dacd`），PR #3 open/dirty。

## 1. 事实基线（2026-10-03 实测）

- A/B 的 `001`—`003` SQL 与 checksum 完全一致：`d5e7bb01b9713b7f`、`bae1d72e1cf3dbe9`、`1d919f8f59a8d4f4`。
- `004`—`006` 同版本号、不同文件与 checksum：

| version | A（`origin/main`） | sha256[:16] | B（本分支） | sha256[:16] |
| --- | --- | --- | --- | --- |
| 004 | `004_execution_lifecycle.sql` | `41527dc2926c3798` | `004_authorization_code.sql` | `ac8f9235fb560145` |
| 005 | `005_event_node_seal.sql` | `29529103ec7ffab8` | `005_delegation.sql` | `176f3743702022de` |
| 006 | `006_event_seal.sql` | `3abb279bc88b2fd7` | `006_task_revocation.sql` | `39a5f4b2c632f86d` |

- 另有 B 独有 `007_admin_grant_revocation`（`6d7d44a2056d25f7`）、`008_login_consent`（`6bfd359aff88c699`）、`009_consent_policy_snapshot`（`ee94ca3672497c0c`）。
- `ag_schema_migrations` 以 3 位 version 为主键，`migrate.py` 对 SQL 文本取 sha256；已应用版本 checksum 不一致即 `MigrationError`，不会自动修复。
- 两条 lineage 的对象不冲突：A `004`—`006` 创建/变更 `ag_execution_leases`、`ag_operation_review_flags`、`ag_receipt_outbox`、`ag_event_seals`，并 `ALTER ag_ledger_events`；B `004`—`009` 只创建授权/委托/撤销/登录同意表，`009` 只 `ALTER` B 自有的 `ag_authorization_requests`、`ag_task_policies`。两者从共同 `001`—`003` 出发后互不改写对方表。
- 现存在两类真实已应用库：A-origin（A `004`—`006`）与 B-origin（B `004`—`009`）。空库也必须可建。

## 2. 迁移整合提案

共同原则：不改已提交 SQL 内容；不删 `ag_schema_migrations` 行；任何重映射先校验旧 version/filename/checksum 与完整行集合，事务内完成并留审计；空库、A-origin、B-origin、含非零/撤销/证明/操作数据的库、非法 registry 五种场景都要有回归。

### 2.1 建议方案 M-REKEY（改名不换内容 + 一次性协调脚本）

1. 整合分支保持 A `001`—`006` 原名原内容；把 B 的 `004`—`009` 文件重命名为 `007`—`012`，SQL 文本保持不变（`_discover` 只哈希文本，改名不改 checksum）：
   - `004_authorization_code` → `007_authorization_code`
   - `005_delegation` → `008_delegation`
   - `006_task_revocation` → `009_task_revocation`
   - `007_admin_grant_revocation` → `010_admin_grant_revocation`
   - `008_login_consent` → `011_login_consent`
   - `009_consent_policy_snapshot` → `012_consent_policy_snapshot`
2. 经批准的一次性脚本 `ag_reconcile_b_lineage`（只在 B-origin 库运行）：
   - 校验 registry 的 `004`—`009` 行 filename/checksum 与 B 原文件逐一匹配，且不存在未知或缺失行；
   - 将 `004`—`009` 的 version 键重映射为 `007`—`012`（checksum 不变），并把 `(old_version, old_filename, checksum, new_version, reconciled_at)` 追加到审计表 `ag_schema_migration_reconcile`；
   - 任一行不匹配即整体回滚并拒绝。
3. 随后运行整合分支迁移器：
   - 空库：按 `001`—`012` 全建；
   - A-origin：跳过 `001`—`006`，补 `007`—`012`；
   - B-origin：跳过（已重映射的）`007`—`012`，补 A `004`—`006`。
4. 新增回归：在 A-origin/B-origin 快照与空库上分别执行迁移并比较 schema；对 registry 篡改（错 checksum、错 filename、删行、未知行）必须拒绝且库不变；重跑幂等。

### 2.2 备选方案 M-LINEAGE-COLUMN（改动更大）

给 `ag_schema_migrations` 增加 `lineage` 维度（主键 `(version, lineage)`），允许同 version 在不同 lineage 下不同 checksum 并保留原行；需要同步修改 runner、wheel 部署与既有 registry 迁移。仅当 M-REKEY 不满足审计要求时采用。

## 3. 共享契约统一提案

原则：B 不放开未知字段、歧义类型与宽松编码；A 不复制 B 的密码/规范编码实现；双方都不把内部 DTO 当作“公网已验权 JSON”。

### 3.1 `ledger_changes` 与 `seq`

现状：A `execution/receipts.ledger_changes_bytes` 输出 `{operation_id, events:[{phase, seq, nodes:[...]}]}` 的普通 JSON（明确不做 RFC 8785/SM3）；B `canonical_ledger_changes_bytes` 要求 event 恰为 `{phase, nodes}`，因此拒绝 A 的材料。建议由 A 负责人在三者中选定一种，并冻结唯一权威定义：

- A2.3 签名前由 A 适配层把内部 outbox 材料投影为 B 的 v1 形状（B 契约不变）；
- 或双方确认 v1 纳入 `seq`，B 在规范编码器按 `phase` 强校验：`RESERVE=0`、终局 `SETTLE|RELEASE=1`，两事件时 seq 必须为 `0/1` 且唯一，`UNKNOWN` 只有 RESERVE 一事件。

无论哪种，`ledger_sm3` 的输入只能有一个定义；验收需跨实现向量（A 真实 outbox → B 规范化/验签）与缺/多/错位/重复 seq、错 phase、错节点集的负例。

### 3.2 invoke 可信 DTO

现状：B `verify_static` 产出进程内 `VerifiedInvocation`，`ancestor_ids=None`，未交付 A 可直接消费的完整权限 path/scope/constraints 映射；A1 的 `VerifiedInvocation` 仍是唯一可信入账输入。建议冻结（仅进程内，不上网）：

- 身份与绑定：`subject/tenant_id/task_id/grant_id/root_id`、`holder_client_id/holder_kid`、`token_digest/proof_digest/intent_digest`、`proof_iat/proof_exp`；
- 权限投影：root→leaf 完整祖先路径、`scope`、`constraints`（七个资源集 + `max_quantity`）、`evidence_ref`；
- 责任边界：B 负责签名、holder 绑定与路径投影；A 在接受事务内复核 DB 撤销、期限、额度后才可使用；HTTP 层不得接受任何“已验权 JSON”。

### 3.3 result-read 查询 DTO

现状：B `VerifiedOperationQuery` 与 A `VerifiedResultQuery` 字段/命名不一致，A 文件注释明确该绑定 pending 且 production 路径 fail-closed。建议以单一冻结字段集统一（`profile/tenant_id/task_id/operation_id/holder_client_id/holder_kid/grant_id/root_id/purpose/endpoint/method/token_exp/proof_iat/proof_exp/proof_jti/token_digest/proof_digest/evidence_ref`），并确认动态 proof 登记在 A 的读事务（A2.1 `ag_proofs.evidence_ref NOT NULL`）；B 只做静态验签与意图校验，查询不扣次数、不授权执行。

### 3.4 `evidence_ref` 生命周期与签名 outbox

- B 的 `stage_evidence` 暂存不可变的首次 token/proof/body 并返回不可伪造引用。建议冻结：写入方、唯一性与幂等、保留期与访问控制、禁止 HTTP 提供引用、失败时引用不可复用、离线验证所需最小字段。
- A2.1 只写 PENDING/未签名材料；A2.3 调 B CryptoProvider 生成 `receipt_jws`。建议冻结签名输入/输出（`typ`/`alg`/`kid`、`ledger_sm3` 输入、A 已稳定的 `receipt_id`/`iat` 幂等）与失败保持 PENDING 的语义；本提案不实现签名。

## 4. 本阶段明确不做

- 不改 A2.1 代码或历史迁移，不清库，不重编号已应用迁移，不解决 Git 文本冲突，不合并 main，不写未批准的 A2.2 业务。
- 所有版本号、文件名与契约字段以 A/B 双方确认后的整合包为准；确认前 B 不单方放开编码器、不复制密码实现。
