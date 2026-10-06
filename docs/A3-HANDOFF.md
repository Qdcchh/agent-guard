# A3 同学接续交接

交接日期：2026-10-06。目标是在 **2026-10-20 前**完成 A3.1→A3.4、完整项目验收与参赛材料。完整当前 A2 已独立接受；项目整体仍为 **PARTIAL**，A3 尚未实施。你接手的是可继续开发的工程原型，不是已经完成独立审计、生产部署或规模实验的产品。

从 [PR #7](https://github.com/Qdcchh/agent-guard/pull/7) 的 `codex/a2.2-integration` 分支开始，**当前 main 不包含完整 A2**。PR #7 用于发布完整 A2 和本交接，未授权本次合并；以实际远端 head、CI 和审核结果为准。A2 本地独立接受不等于 GitHub 人类审核或远端 CI。克隆后记录实际 commit SHA、工作区状态、依赖与测试结果，绑定后续正式任务包。

```bash
git clone --branch codex/a2.2-integration --single-branch https://github.com/Qdcchh/agent-guard.git
cd agent-guard
git status --short --branch
git log -5 --oneline
git switch -c codex/a3.1-journal-checkpoint
```

每个 A3 开发分支从上述完整 A2 发布分支或已接受的 A3 前段创建，PR 暂以 `codex/a2.2-integration` 为 base。A2 正式合并后再核实际内容并调整 base，不能从旧 main 重写或遗漏 A2。不要 reset/clean/强推覆盖他人成果，不修改 Git 身份、hooks 或分支保护。未经独立审核、必需 CI 与正常 GitHub 审核条件满足，不合并；PR #6 的历史管理员例外不继承。

此次交接要求同学完成全部 A3，可依次推进四段；每段仍要正式任务包、独立包审、实施整合、停写冻结及新的独立完整复核，前段接受后才进入下一段。历史任务中的旧路径、旧禁推送措辞和 STOP 只解释当时那一轮，不是你接续 A3 的禁令，也不允许绕过当前阶段门槛。本次交接作者只发布 A2/文档，没有实施 A3。

## 先读哪些文件

按顺序读 [AGENTS.md](../AGENTS.md)、[AGENT.md](../AGENT.md)、[README](../README.md)、[接口方案](oauth-oidc-sm2-mvp.md)、[安全模型](security-model.md)、[验收矩阵](acceptance.md)、[A3 完整计划](../tasks/A3-plan.md)、[当前协作约定](../tasks/workflow/current-policy.md)。再读 [A2 原任务](../tasks/A2-execution-gateway.md)、[完整 A2 接受记录](../tasks/workflow/runs/A2.3-receipts-20261004/acceptance.md)、[完整独立 review-r2](../tasks/workflow/runs/A2.3-receipts-20261004/review-r2.md)、[A2.2 接受记录](../tasks/workflow/runs/A2.2-integration-20261004/acceptance.md)及相关源码、调用方、测试断言。

A2 原任务和历史报告中的绝对路径与旧状态不能用作当前操作步骤。密码参数/维护边界见 [密码配置](crypto-profile-v1.md)，阶段状态以最新正式接受记录为准。`product-manifest.json` 是历史传输快照，不是当前文件清单。

Git 中包含源码、测试、锁、SQL、规范及正式报告；`.env`、私钥、可用 token、数据库内容、个人模型配置和私密 raw 运行证据不提交。历史报告引用的本地 `artifacts/` 原件和 ignored A3 builder/探针不在干净克隆中，也不是安装或实现依赖。它们的缺失不能用“已有 PASS”代替你自己的复现；新阶段需要把完整可审任务包、必要合成测试和可公开结果写入仓库，在自己的私有目录另存脱敏命令、退出码、JUnit、原始实验数据与哈希。

## A2 已接受的范围与剩余边界

2026-10-06 的完整 A2 结论绑定冻结候选 369 项文件，而不是仅绑定旧 HEAD。正式接受记录保存冻结摘要及报告 SHA。119 项要求、112 项运行义务、269 条必须断言完整保留；source 和 fresh 非 editable wheel 各完成普通套件 **1185 PASS**、真实 PostgreSQL 集成 **2810 PASS**、精确时限组 **500 PASS**。增强组 source 原 487 PASS；wheel 原 484 PASS/3 FAIL 保留，原未受影响 407 项与原模块新完整 80 项逐 case 闭合，不能改写成原组全绿。精确时限 500 项不是 500 次网络调用，包含域容量上界不是共同可达合法最大值。

当前已有真实 SM2/SM3、AS 登录同意/PKCE、根及两级 AS 签发委托、DID/登记绑定、公开 invoke/当前动态 query、四工具可信参数/报价、全祖先预算、独立下游幂等、租约/恢复、outbox 和内部真实回执连续发布。真实 AS/GW HTTPS 联合测试和演示已有；回执 SDK 可以核验单 operation 的关联与签名，仍为 **UNANCHORED**。旧未配置回执公钥的 query 只兼容 PENDING/null；READY 缺可信回执公钥须失败关闭。

未完成的是独立日志检查点、完整有界导出/离线历史重建、可交付部署与三个独立 holder 编排、50 客户端/至少 10000 调用、公平对照及最终材料。A2 测试和底层演示不能冒充这些成果。

正式记录还保留 wheel 增强旧失败的 wall/monotonic 间断（物理原因及一次 PG cause UNKNOWN）、某 Desktop 私有 FD 拒绝根因 UNKNOWN，以及旧观察器退出回执 UNKNOWN。新私有目录字面流程、原生进程检查、资源清理与独立恢复见证另有证据。密码依赖的精确构建 commit/完整安全回移维护未证实；不声称绝对无缺陷、生产安全或通用 exactly-once。

## 从干净环境建立回归基线

推荐 Linux x86_64、CPython 3.11、PostgreSQL 16、支持 SM2 的 OpenSSL CLI；其他平台须实测，不能把发行元数据的支持声明当验证结果。无需模型 API、个人代理命令或作者电脑上的 Docker 资源。网络依赖仅用于获取锁定发行包及镜像；按本机网络配置安装，不依赖 `setproxy`。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
python -m pip check
python -m ruff check .
python -m ruff format --check .
python -m pytest tests --ignore=tests/integration
openssl version
```

锁文件已包含 `tongsuopy==1.0.1`（SM2/SM3，底层 Tongsuo/BabaSSL）、`rfc8785==0.1.4`、`psycopg/psycopg-binary==3.2.13`、`uvicorn==0.35.0` 及传递依赖。SM2 使用 `sm2p256v1`、固定用户标识 `1234567812345678`；对原始 JWS 两段输入执行 SM2-with-SM3，不自行预哈希或拼旧域前缀。运行固定向量、编码和跨实现互验：

```bash
python -m pytest tests/test_crypto_profile.py tests/test_encoding.py tests/test_interop_vectors.py
```

上述互验需要 OpenSSL CLI 支持 SM2/SM3 和 `distid`；不支持时报告依赖缺口，不能删测试、替换算法或降级。应用 SM2 签名与传输 TLS 是两层；若 TLS 证书使用 RSA，如实说明，不能称 GMSSL。

不要复用已有容器、生产 DSN 或他人的库。下面创建一套明确属于自己的临时实例；名称/端口必须先确认未占用。测试密码只用于一次性 loopback 容器，禁止部署复用或输出 DSN。

```bash
unset AGENT_GUARD_DATABASE_URL
export A3_TEST_CONTAINER="agent-guard-a3-${USER}-$(date +%Y%m%d%H%M%S)"
export A3_TEST_PORT=55436
export A3_TEST_PASSWORD=local-a3-test-only-pw
docker run -d --name "$A3_TEST_CONTAINER" --label purpose=agent-guard-a3-tests \
  -p "127.0.0.1:$A3_TEST_PORT:5432" --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_USER=agent_guard_test -e POSTGRES_PASSWORD="$A3_TEST_PASSWORD" \
  -e POSTGRES_DB=agent_guard_test postgres:16-alpine
docker exec "$A3_TEST_CONTAINER" pg_isready -U agent_guard_test -d agent_guard_test
export AGENT_GUARD_TEST_DATABASE_URL="postgresql://agent_guard_test:${A3_TEST_PASSWORD}@127.0.0.1:${A3_TEST_PORT}/agent_guard_test"
docker exec "$A3_TEST_CONTAINER" psql -U agent_guard_test -d agent_guard_test \
  -c 'CREATE ROLE br_s1_untrusted NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'
docker exec "$A3_TEST_CONTAINER" psql -U agent_guard_test -d agent_guard_test \
  -c 'GRANT br_s1_untrusted TO agent_guard_test WITH ADMIN FALSE, INHERIT FALSE, SET TRUE'
python -m agent_guard.ledger.migrate --bundle
python -m agent_guard.ledger.migrate --bundle
python -m pytest tests/integration
```

首次启动如未 ready，等待后重新检查 readiness 再执行 SQL。第二次 bundle 迁移应无写入。集成测试需要创建 schema 和随机 scratch 库的测试角色；缺库必须报错，不能静默 skip。拒绝探针须先成功切换角色，再观察真实 `42501`，角色切换失败不算通过。测试 fixture 管理自有 schema/下游 scratch 库；不得宽泛清空 `ag_%`、关闭保护或访问生产库。只在核实确为本轮自建资源后清理：

```bash
docker rm -f "$A3_TEST_CONTAINER"
unset AGENT_GUARD_TEST_DATABASE_URL A3_TEST_PASSWORD A3_TEST_CONTAINER A3_TEST_PORT
```

`.github/workflows/ci.yml` 当前以 Python 3.11/PG16 运行锁安装、ruff、全部非集成、bundle 两次、全部 PG 集成；不能漏掉新增目录。push 触发只匹配 main，PR 触发 CI；开发分支 push 成功并不表示有 CI 结果。CI 不自动证明非 editable wheel 隔离、完整 A3 演示或实验，因此这些要另有正式复验。

非 editable wheel 必须单独复现。构建后端固定 `setuptools==80.9.0`，只构建 wheel，核对输入/成员/依赖与哈希；不发布 sdist。可按 README 的固定后端隔离构建示例，或在独占构建 venv 安装该固定后端后执行 `python -m pip wheel --no-deps --no-build-isolation --wheel-dir <自有输出目录> .`。在另一个 fresh venv 安装锁和生成 wheel，禁止 `-e`；清除 PYTHONPATH/editable hooks。在源码树外复制 `tests/`、`tools/`、文档、tasks、SQL 和测试所需非源码输入，不复制 `src/agent_guard`，保持相对链接；从该目录执行完整普通与 PG 套件。父进程及每个 Python 子进程实际 `agent_guard.__file__` 必须指向安装环境 site-packages，并核 installed SQL/原始 14 SQL 字节与打包源一致。仅在仓库根安装 wheel 后运行测试，不足以证明隔离。源码模式另设 `PYTHONPATH=<自己的源码目录>/src`，不能与 wheel 结果混记。

## 真实配置与现有运行入口

[README 第 5 节](../README.md#5-开发环境与验证)给出了 AS、GW、执行 worker、receipt worker 和合成 HTTPS demo 的现有命令；这些是 A3 接续入口，不是已经交付的 A3 部署。

- `python -m agent_guard.server init/check/run`：显式初始化 AS/合成 holder 密钥与私有配置；`run` 注入 `AGENT_GUARD_DATABASE_URL` 和 TLS cert/key。
- `python -m agent_guard.gateway init/check/run`：网关严格配置及私有下游 secret；`run` 只使用 `AG_GATEWAY_DATABASE_URL` 与 `AG_GATEWAY_DOWNSTREAM_DATABASE_URL`，必须 TLS。
- `python -m agent_guard.execution.worker`：内部单 operation 执行/对账；使用 `AG_WORKER_GATEWAY_DSN`、独立 `AG_WORKER_DOWNSTREAM_DSN`、`AG_WORKER_SERVICE_SECRET`、operation ID、租约 owner 及批准的 supplier/recipient/request allow-list。空 allow-list 服务为空；不可把测试同步窗口当业务运行方案。
- `python -m agent_guard.gateway.receipt_worker init/check/run`：独立 receipt SM2 signer；`init --gateway-config ... --out ... --signing-kid ...` 保留历史公钥，并生成 `gateway-public.json` 给 GW；`run` 只读显式 `AG_RECEIPT_DATABASE_URL`，可 `--once` 或 `--operation-id`，不迁移/初始化业务、不重执行业务。
- `python -m tools.a2_receipt_demo`：仓库内已有合成真实 HTTPS 演示，需分别注入 `AGENT_GUARD_TEST_DATABASE_URL` 和 `AGENT_GUARD_TEST_DOWNSTREAM_DATABASE_URL`，调用前迁移自己的 GW 测试库。生成临时 CA/SAN/密钥，完成登录、两次交换、四工具、发布/query/SDK，但仍无 A3 独立锚点/三进程编排/导出。

各 `check` 离线校验配置，不连接数据库；factory/run 不隐式 migrate、reset 或 provision。AS/GW 的 `init` 分别生成合成信任，不能把两个互不关联的默认配置直接当联合部署。A3.3 要从批准 TaskPolicy、AS/holder 公钥登记、DID 与资源目录构造一致配置，私钥仅给各自 holder/服务；网关加载公开信任而不能获得 AS/holder signer。

私有文件必须在当前 UID 自有的 0700 父目录，init 目标尚不存在；密钥、secret、配置文件 0600（读入仅0400/0600），禁止 symlink，祖先所有权/写权限按 `server/private_files.py` 验证。使用 CSPRNG，新 kid，保留可信历史公钥，失败关闭；不能通过放宽权限来解决平台拒绝。TLS 客户端必须有可信 CA，并核正确 SAN/hostname；固定签名 endpoint 为 `https://gateway.agent-guard.test/v1/invocations` 与同源 `/v1/operations/query`，不能从 Host/X-Forwarded 推导或关闭校验。

公开 invoke 使用 `Authorization: AGPoP <access-token>` 与 `AG-Proof`，只接受后返回202；内部 worker 推进业务。query 必须 result-read/new proof 与当前完整权限，不扣业务次数。不要新增公开 recover/settle/release/sign 或已验权 JSON 入口。

## 跨阶段共享约束与模块接续

根和全部适用祖先均满足 `settled + reserved <= limit`，金额/次数非负；CNY 整数分，bool 不是整数，订单成本从固定可信报价算。租户、任务、audience、工具/version、资源、参数、金额、次数、期限、深度逐级收窄；固定四工具、最多256 SKU、批准通知模板/接收方，不开放任意 URL/脚本/转发。

外部首次调用、幂等重试、交换和查询都要真实当前验权与新鲜 proof；业务幂等键不是 nonce。撤销先提交则拒绝新接受，已接受的不可变意图允许内部恢复。下游超时或查不到表示 UNKNOWN，保留全部祖先预留，不能提前释放。恢复只读取原 operation、报价、路径、证据，不用请求 body 或当前价格补造。网关与下游独立数据库/连接/事务；终局、全祖先变动和 outbox 同事务，网络不持业务锁。原14 SQL、版本登记、历史失败和锁不得修改。

| 接续位置 | 现有责任 | A3 必须接续的边界 |
| --- | --- | --- |
| `contracts/encoding.py`、`crypto/`、`authorization/`、`identity/` | 唯一编码/SM2/SM3、真实 AS 与 verifier、登记/历史信任 | 复用，不能复制另一套协议/密码或从当前 DID 倒推历史 |
| `ledger/lineage.py`、`migrate.py`、`store.py` | bundle/兼容迁移、原子祖先额度、不可变存储 | 串行先冻结新日志迁移及跨域依赖，不改历史 SQL |
| `execution/verified.py`、`service.py`、`query.py` | 验证 bundle→原子 FIRST/RETRY、worker终局、当前动态QUERY | 新 journal 与原事务绑定，新增工作后再核最终 DB clock |
| `original_material.py`、`receipt_projection.py`、`receipt_publication.py` | 首次真实材料/报价/路径/delta校验、签名/READY | 复用不可变事实，首次READY原子记日志，不引入当前撤销/报价作为历史发布门槛 |
| `gateway/`、`server/`、`private_files.py` | HTTP/严格公开与私有配置、TLS CLI | A3 新服务/演示继承失败关闭，不读 signer 私钥作公开信任 |
| `evidence/receipt.py`、`tools/`、`tests/fixtures/` | 单笔离线关联、独立下游、隔离测试 | 增加历史日志/外部 checkpoint 验证；测试夹具只用于测试 |

## A3.1：原子日志、独立检查点与可靠传送

先串行完成正式包：绑定完整 A2 基线、全部继承节点/断言、新迁移/编码/scope/genesis/事务内 seed/锁序、接入点和隔离清理。FIRST、RETRY、QUERY、TERMINAL、首次READY均与原业务事务原子记录；STAGED 不等于接受，启用后不得可选 None hook 绕过。新任务全部适用 grant 初始零计数；历史非零任务经显式停写/drain/维护导入，记录 GAP，不伪造旧 FIRST。

锁序保持 principal→task→root-to-leaf grants→operation/lease/outbox→journal head；publisher 只 outbox→既有 head，不能倒锁或偷偷 bootstrap。接受须在新增读取/写入/约束刷新后核最终数据库时刻；终局在日志后核 owner/version/state/expiry，不续租掩盖过期。执行007依赖现有006与B010；默认 legacy 发现仍限001—006，不能 glob 到007就绕过跨域依赖。独立 audit 库和 GW 库各有库存核验。

冻结共享接口后可并行检查点服务与传送 worker，各自独占文件/库。checkpoint 批次1—64，实际编码≤65536，真实SM2、`ag-checkpoint+jwt`，绑定 seq/head/previous。短事务先保存准确 pending body，释放业务锁后做真实 TLS；新进程重发同一请求，ACK精确匹配原批次，迟到ACK不能删除新pending。remote-ahead验证连续前缀，不跳最新head。核并发/重复/错误ACK、断网/崩溃/新PID恢复、锁后时限与全祖先计数；同机独立库只证明逻辑隔离。

完成条件：全部原子接入和恢复真实通过，完整继承回归不弱化，独立实施 reviewer 接受并记录实际接口，才进入 A3.2。

## A3.2：有界证据导出与离线验证

先冻结正式导出格式与外部信任接口，再按独立文件并行 exporter/verifier。REPEATABLE READ只读事务固定 S/H，完整有界物化到0700目录/0600文件，结束事务再下载，不跨长网络传送持业务事务。NDJSON每帧含换行≤64KiB；计划上限 wire256MiB、400000帧、200000对象、100000日志项、20000操作，原材料分帧24576字节、日志32768字节。正式包须用真实10000调用工作负载预检可行性，超限拒绝，不截断/无限内存；保留 JSON/原材料64KiB、JWS16KiB、外壳1MiB及链/节点限额。

独立配置 AS、GW、holder历史登记、目录、audit key、scope/genesis和外部 checkpoint，不信包自带公钥。验证签名关联、连续认证前缀、原始材料、全部祖先四计数和预算重建；篡改、错配、重排、已锚定删除及相对最新外部锚点回滚应失败。分别报告锚定历史、未锚定尾部、unsigned运行时观察；即使 N=S 仍标 `UNANCHORED_AS_OF_DB_OBSERVATION`。缺最新外部锚点不能保证最新性，当前授权状态 UNKNOWN、下游事实 `ATTESTED_NOT_INDEPENDENTLY_PROVEN`、历史缺口 GAP。保留 unsigned 状态被修改并重算根仍可能无法检出的诚实正控。

完成条件：正常与全部攻击/局限用例实跑、source/wheel整合回归、独立完整复核接受。不能以单笔 receipt SDK 验签替代历史完整性验收。

## A3.3：干净 TLS 部署、三 holder 与完整演示

串行冻结安装、配置、client和handoff前置，再并行情景脚本/部署预检；最后主入口、compose、README由一个整合者修改。独立 AS/GW/audit/DID TLS 服务、三个真实 holder 进程/私钥、独立下游库与凭据。无需模型 API 的确定性采购从可信初始化/TaskPolicy、cookie/CSRF/state/nonce/S256登录同意、code换根、两次 exchange 到四工具/version1、worker终局、发布、当前query、锚定、导出与离线验证完整闭合。根/中/叶金额次数逐级收窄，模型和holder没有下游/管理凭据。

验证真CA/SAN和wrongCA/hostname拒例、盗token/错holder/重放/扩权/撤销、256SKU、真SIGKILL/回复丢失恢复、密钥轮换、版本升级和备份恢复。不得导入测试 fixture 作为部署初始化、手造AS令牌或添加跳验开关。完整演示脚本必需，视频可选；干净克隆、source/非editable wheel及父子进程来源都须实核。现有 check/预检成功不代表完整部署通过。

完成条件：另一环境按文档无需作者本机文件即可复现，完整回归/故障/升级/轮换与独立复核接受，才冻结实验版本。

## A3.4：规模实验、公平对照与最终材料

先冻结工作负载、真实资源/计时口径、凭据、状态检查、预算与审计能力。比较 ACL、无原子共享预算消融、完整方案、SM2签名Bearer 四种模式；研究适配器独立，不给生产网关添加绕过开关。N/A 如实报告，Bearer 不伪造 VerifiedProof；无原子预算模式仍保留真实 AS/PoP/当前授权、业务幂等和撤销锁，仅使用独立研究计数消融原子共享预算。

计划固定种子2026100501/2026100502；每模式每轮5000测量＋250预热、两轮合计40000测量，完整方案10000。每轮3500合法、1000攻击、500重试；50真实客户端初始barrier、server32，第二轮反转模式顺序。正式包确认任务/证明有效期、连接/读取/依赖/drain上限和导出容量。全部真实发送尝试及失败进入原始记录，未发送记 INCOMPLETE，不补造行、续同grant、换目标或挑成功样本。

攻击包括盗token、错holder交换、重放、改body/endpoint、资源/委托扩权、SKU严格边界、失效授权与双分支预算竞争；提前绑定真实签发凭据和实际路径，区分AS拒绝与被测invoke。AS/query/audit不计工具invoke，错holder拒绝不能替代有效holder资源负例。真实10轮竞争核完整方案最多一个70000分支、研究无原子模式实际140000效果及全部祖先/下游。

记录合法验权率、正常完成率、越权/重复效果、预算不变量、撤销延迟、全部错误；吞吐、nearest-rank P50/P95/P99、凭据尺寸/存储、CPU/RSS/WAL，区分真实密码/DB/网络/模型成本。独立SM2 sign/verify/SM3基准保留向量及互操作。报告实际CPU/内存/系统/PG参数/密码版本/链深度/参数尺寸/预热/计时，不减估计密码成本、不挑最好一次、不凭不同条件对照声称优越。0越权仅限声明测试集与假设。

## 协作、独立验收与最终完成

主控维护包、接口、范围、阶段状态和材料；适合并行时先冻结共享前置，再把独占文件、数据库/端口、证据目录明确交给worker。禁止同文件并发写；全部writer停写后单一整合者完成调用方/CLI/文档/CI联调。包审与实施验收由新的独立reviewer承担，reviewer只读受审候选，自己选负例/故障并实际运行；作者自查、绿色计数或 PACKAGE_READY 都不是 ACCEPTED。跨机器/不同工具可采用同等原生回执、全哈希冻结、范围/资源隔离、完整实跑证据；实际模型元数据未知记 UNKNOWN，不依赖作者个人模型配置，标准不减。

每阶段正式包把 M1—M13、SEC/CON/REC/AUD/E2E/ENG 与前段适用要求逐项映射到真实模块、具体测试函数/断言、命令、运行方式与应观察事实，新增A3义务完整落盘。直接保全真实继承测试，不造无意义wrapper、不以helper union/AST计数代替本人语义判断。已有未受修改影响的通过检查无需无理由重复，但阶段要求的完整自查和 fresh 独立复核必须执行。保留失败、退出码、中断与补正记录，补正后重新绑定候选。

最终完成必须同时具备：四段正式接受记录；完整项目矩阵与故障/攻击回归闭合；干净部署、三holder两级委托/四工具/预算恢复/外部锚定/离线验证可复现；50客户端及完整方案至少10000调用与全部对照原始数据可核对；最终技术报告、设计/威胁分析、源码/依赖许可说明、部署与升级恢复手册、演示脚本、可独立验证的合成证据包、实验脚本/数据/分析、已知限制均对应同一固定版本。视频可选，不以视频替代脚本。

20日前固定最终 commit/tag与材料哈希，提交审查和实际CI，不合并未经审核版本。时间紧时优先削减可选页面/退款场景，不能删预算、撤销、幂等、证据或公平对照要求。存在失败/缺口则如实列 PARTIAL/NOT_RUN/UNKNOWN，不能把规划、预计性能或本地自查写成最终完成。
