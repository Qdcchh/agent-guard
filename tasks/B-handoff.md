# B 独立交付封版交接（2026-10-02）

状态：B 角色可独立完成的范围已封版。**端到端初版未完成**；`/v1/invocations`、`/v1/operations/query` 的 A 侧读事务、执行/恢复、`/v1/evidence/export` 与网关回执公钥仍等待 A 提供（见 [B-interop](B-interop.md) 与 Issue #4）。本轮之后不再新增 B 单边功能。

封版代码提交：`5dc832a`（功能性提交）。本交接记录为随后的文档提交；最终 head 以远程 `feature/fjr-B-character` 的 `git log` 与 CI 为准。

## 1. 干净安装与运行

CI 的 `clean-install (wheel)` 作业在 Python 3.11 + 空 PostgreSQL 上验证“不依赖源码目录”的安装：

```bash
# 1) 构建 wheel（不打包 migrations；迁移 SQL 在仓库/部署目录单独提供）
python -m pip wheel . --no-deps -w dist

# 2) 隔离环境安装（Python 3.11）
python -m venv .clean
.clean/bin/python -m pip install -r requirements-dev.lock
.clean/bin/python -m pip install --no-deps dist/*.whl

# 3) 依赖注入：迁移目录与数据库
export AGENT_GUARD_MIGRATIONS_DIR=/path/to/migrations
export AGENT_GUARD_TEST_DATABASE_URL=postgresql://user:...@127.0.0.1:5432/db

# 4) 空库执行全部迁移（幂等、checksum 保护）
.clean/bin/python -m agent_guard.ledger.migrate

# 5) 校验
.clean/bin/python -m ruff check .
.clean/bin/python -m ruff format --check .
.clean/bin/python -m pytest tests --ignore=tests/integration
.clean/bin/python -m pytest tests/integration          # 含 OpenSSL SM2 互验与 TLS 全链路
.clean/bin/python -m tests.demo_b_flow                 # 合成 B 授权演示
```

开发部署启动（开发 TLS 边界，非生产）：

```bash
python -m agent_guard.server init --out ../ag-as-dev
python -m agent_guard.server check --config ../ag-as-dev/config.json
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=localhost \
  -keyout ../ag-as-dev/tls-key.pem -out ../ag-as-dev/tls-cert.pem
AGENT_GUARD_DATABASE_URL=postgresql://... python -m agent_guard.server run \
  --config ../ag-as-dev/config.json --ssl-certfile ../ag-as-dev/tls-cert.pem \
  --ssl-keyfile ../ag-as-dev/tls-key.pem
```

## 2. B 公共 API（包根导出）

| 包 | 入口 |
| --- | --- |
| `agent_guard.crypto` | `sign_compact_jws` / `verify_compact_jws`、`sign_sm2_message` / `verify_sm2_message`、`serialize_sm2_public_key` / `load_sm2_public_key`、`sm3_digest` / `sm3_b64url`、`generate_sm2_private_key`、固定 `JWS_ALG`/`JWS_TYPES`/`SM2_USER_ID` |
| `agent_guard.contracts` | `load_strict_json` / `canonical_json_bytes` / `b64url_*`；`PURPOSE_INVOKE`/`PURPOSE_RESULT_READ`、`INVOKE_ENDPOINT`/`QUERY_ENDPOINT`、`VerifiedInvocation`、`TrustedCost`、`AcceptResult`、`ErrorCode`/`LedgerError` |
| `agent_guard.authorization` | `InvocationVerifier.verify_static` / `verify_result_read`（→ `VerifiedInvocation` / `VerifiedOperationQuery`）、`validate_access_claims` / `validate_child`、`sign_ag_proof`、`GrantPolicy`、`AuthorizationCodeService` / `CodeExchangePreflight`、`TokenExchangeService` / `ExchangePreflight`、`IntrospectionService` / `IntrospectionEndpoint`、`TokenEndpoint`、`LoginService` / `ConsentService` / `BrowserLoginApp`、`TaskRevocationService` / `GrantRevocationService` / `RevocationHttpApp`、`verify_id_token` / `pkce_s256_challenge` |
| `agent_guard.identity` | `IdentityResolver`、`RegisteredIdentity`、`ResolvedIdentity`、`did_web_url`、`IdentityError` |
| `agent_guard.ledger` | `ExecutionLedger.accept`、`apply_migrations` / `applied_versions`、可信初始化夹具（`create_task_root` 等） |
| `agent_guard.evidence` | `ReceiptTrust`、`verify_receipt_bundle`、`VerifiedReceipt`、`ReceiptVerificationError`；（`AG-EVIDENCE-1` 目前仅接受 `anchoring_status="UNANCHORED"`） |
| `agent_guard.server` | `load_server_config` / `load_secrets` / `resolve_paths`、`build_app`、`RequestTimeoutMiddleware`、`python -m agent_guard.server init/check/run` |

`VerifiedInvocation`、`VerifiedOperationQuery` 与 `AG-EVIDENCE-1` 包/回执字段由 `tests/test_interop_vectors.py::test_public_contract_field_sets_and_exports_are_frozen` 冻结；字段清单见 [B-interop](B-interop.md) §2。

## 3. 固定向量与可信公钥配置

- 固定向量入口：`tests/fixtures/interop.py`（**TEST-ONLY**：5 把合成 SM2 私钥、冻结 SPKI/SM3、planner→selector→executor 令牌链、invoke/result-read AG-Proof、三方路径 `AG-EVIDENCE-1` 包）与 `tests/test_interop_vectors.py`（无数据库，`python -m pytest tests/test_interop_vectors.py`）。私钥严禁用于部署。
- AS 签名公钥：通过项目私有 `/ag/keys`（非标准 JWKS）或配置内的 SPKI PEM 提供；轮换使用新 `kid`，旧公钥仅验签（`historical_verification_keys`）。
- 网关回执公钥：由部署方独立注入 `ReceiptTrust.gateway_keys`（kid→公钥），不得取自证据包自带字段；轮换用新 kid，旧 key 仅历史验签。
- holder 历史公钥与登记：`ReceiptTrust.holder_keys` + `historical_registrations`，与 `IdentityResolver` 的预登记快照一致；不得用当前 DID 文档倒推历史授权。
- `AG-EVIDENCE-1` 目前无独立检查点：只能验证单笔变动的签名与关联，不能检测重排、删除或回滚。

## 4. CI 与验证记录（截至封版）

| run | 内容 | 结果 |
| --- | --- | --- |
| #36 `db36ec2` | result-read 验权与向量 | success |
| #37 `3c6a188` | 文档与联调请求 | success |
| 封版 run（见 B-progress 最新记录） | `checks` + `clean-install (wheel)` 双作业：ruff、非集成、空库迁移、真实 PostgreSQL 集成、OpenSSL SM2 互验、TLS 全链路、合成演示 | 以 CI 结果为准 |

本机无 PostgreSQL、OpenSSL 与 Python 3.11，因此本机仅执行 ruff、非集成测试（199 passed）与 wheel 干净安装冒烟；数据库/互验/TLS 结论以 GitHub Actions 为准。

## 5. 已知限制

1. A 侧 HTTP 网关、四工具、下游幂等/恢复与证据导出未实现；接缝测试不代表端到端。
2. 独立审计检查点未实现；无最新锚点时的回滚检测不成立。
3. 生产密钥托管（HSM/KMS）、自动轮换调度、泄露取证未实现；开发 TLS 与自签证书仅限本地。
4. 性能与对照实验（50 并发/10,000 调用）未执行。
5. wheel 不含 `migrations/`，安装部署必须设置 `AGENT_GUARD_MIGRATIONS_DIR`。

## 6. M1—M13 状态

| 项 | 状态 |
| --- | --- |
| M1 登录/同意/换码 | 局部覆盖（含真实 TLS 全链路；浏览器/反代生产部署未验证） |
| M2 两级委托 | 局部覆盖（AS 签发、收窄、接缝接受；A 网关 HTTP 未验证） |
| M3 DID/登记 | 局部覆盖（只读解析与绑定负例） |
| M4 盗用令牌 | 局部覆盖（验权与接缝层；网关 HTTP 未验证） |
| M5 绑定与重放 | 静态与账本局部覆盖 |
| M6/M7/M11/M12/M13 | 未通过（依赖 A 网关/下游/恢复；A1 账本内部并发/幂等已有测试） |
| M8 撤销 | 事务与撤销 HTTP 局部覆盖；网关竞态未验证 |
| M9 回执验证 | 合成 `AG-EVIDENCE-1` 覆盖；A 真实导出包未验证 |
| M10 干净部署 | 仅 B 侧 wheel/迁移/演示；完整端到端未验证 |

## 7. 等待 A 提供（下一位接手必须核对）

按 [B-interop](B-interop.md) §2 与 Issue #4：`/v1/invocations`、`/v1/operations/query`（读事务复核）、状态机与 UNKNOWN 恢复、`/v1/evidence/export`、网关回执公钥（kid+SPKI）、共享事务域与配置对齐。交付后先 `git fetch` 核对 `origin/main`，再执行真实 HTTPS 端到端联调并逐项留痕；在此之前不得宣布 M1—M13 通过。
