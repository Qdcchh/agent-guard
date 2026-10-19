# PR9 容量来源、安全与外部供给独立审查

结论：**NOT_READY（当前 clean GitHub CI 供给尚未实施/验证）**。review_kind=CAPACITY_SECURITY_AND_SUPPLY_REVIEW；这不是最终完整 IMPLEMENTATION_ACCEPTANCE。本报告同时判定：**公有 Release 仅保存成熟 AES-256-GCM 密文、密钥受控的架构可按下述契约实施**，未发现“密文公开本身”被当前规则自动禁止的依据；本轮不授予上传、设置 Secret、commit/push 或合并许可。后台 effective metadata=UNKNOWN。

范围内独立核验已覆盖所有110历史成员SHA、当前安装139源码、三组历史/当前基准差异、原计数器读取路径、40表全档语义扫描、109辅助文件扫描及负探针。只写本 capacity-security-review 目录；其他候选文件、历史数据和用户文件未修改。尚缺外部供给实现及 clean runner 证明，必须保留这项阻断，不能用本报告替代6839原测试、全部非PG、部署或最终最新head全绿。

## 1. 依据与来源完整性

直接读取 AGENTS.md、AGENT.md、current-policy.md、本轮 package-v1/user-local-updates/package-review-r1，及相关 README、设计、安全、验收、review-contract 和原测试/fixture/工具。先后复算指纹见 reviewed-inputs-start.json 与 reviewed-inputs-end.json。完整110成员的真实来源相对路径、角色、长度、SHA见 input-manifest.json；没有省略大型archive的实际散列。原件全部符合既有binding SHA。

关键冻结输入：

|输入|SHA256|
|---|---|
|tools/pr9_capacity_inputs.py|6c6e445b5d7bbdabbf6f92c67c25782d70bf55687d45cdcc6268ba389a420f3a|
|tests/unit/test_pr9_capacity_inputs.py|d08ffbc07db9f64bc6e5abe2b6d9da6ebc6c350e778884b0c986bea74e830636|
|worker report.md|8332cb90a2cfa9d71fe016defccaec13a95f87c16b0e9234074a57886e4a8e4b|
|tests/fixtures/a32_joint.py|80308ae8d1332f8b6b55a55f3a11df416b66b0303dd99ec76ab5dbd1e53f411f|
|tests/integration/test_a32_joint_tls.py|222003bf4173cdea33c2e68e4a3b995ae955f8a7242e14b4aeda4ce3895b9660|
|原r6 binding|4509d6f5620634104d51a682a58aacd7e6bff48c7939142f699600b31a9e2a45|
|原826390481-byte archive|9eafeecc22541229d5c3ccc9cc0d033f5a4d89497e51e45282fe8255501a4358|

三组基准不可混淆，均由实际字节/AST独立复算：native原100→r6安装为96同字节/4变化；r6安装100→当前source为83同字节/17变化；native原100→当前source为81同字节/19变化。分别见 native-original-v-r6.json、source-independent.json、native-original-v-current.json。历史96+4分类仍准确描述当时比较，不能描述当前整体业务。

当前139个.py与worker真实非editable安装逐SHA相等（current-installed-independent.json）；本轮另在独立容器重新执行 bind-installed，实际Python3.11.17、__file__、139个import spec、禁止editable/PYTHONPATH均通过。这里复用了只读的worker安装，并未声称本轮重新安装全部锁依赖；全锁、pipcheck、fresh clean安装仍由最终独验/CI完成。

## 2. 原计数器与当前局部复用资格

直接检查原test及 count_original_capacity：test先散列全部members与actual installed，验证10000独立ID、执行完成与真实旧拒绝，再让当前codec读取原archive。计数器实际消费gateway八表：streams/bootstrap/bootstrap_chunks/records/verified_evidence/operations/receipt_outbox/grants。它验证原journal链、原材料摘要、FIRST path非空及bootstrap授权ID绑定，实际encode合法批次和object chunks；TERMINAL是原行算术投影，footer根为长度seed占位，acceptance=NOT_ASSERTED。这不是新10000业务运行、PG导出、AUDIT TLS观察或完整bundle验签。

当前相对r6的export.py、task_bundle.py、audit/contracts.py、audit/checkpoint.py、contracts/encoding.py、contracts/ledger_changes.py、crypto/sm.py同字节。journal仅新增_json_value Decimal分支，目标counter不调用；task_verify _bootstrap/_verify新增语义不被本counter调用。其余变更涉及真实业务/执行/部署，不能据容量计数结果批准整体业务复用。native→r6四差异包括receipt_semantics、export、task_verify、journal；原export top-level函数AST未变，原nonempty guard路径在10000 FIRST上实际检查。

工具保留旧classification是为了原测试兼容，同时加pending/current-review标志；**该标志本身不是安全门**。供给consumer须有当前源码资格清单，精确绑定原fixture/counter/test/当前source/依赖/构建安装，实际bind每个consumer自身安装并真实跑原测试。任何hash变化须重新评估资格，不能只拷贝历史classification或别的环境的139个路径。

## 3. 独立安全审计与新阻断

audit-independent.json为本轮独立解析所有40表、每行/字段/类型、嵌套JSON、hex UTF8、顶层metadata及紧凑JWS的聚合；没有输出JWT/DSN/password/原始日志内容。结果：

- 3个ag-at+jwt，全部已过期，iss/tenant/task匹配合成测试；10011个ag-pop+jwt，全部已过期。proof本身没有同样tenant/issuer字段，不能据此说proof具有这些claims。
- 10000个ag-receipt+jwt没有exp，tenant/task均匹配合成测试；不能写“所有JWT都已过期”。本轮只解码，未验签，未试用任何外部凭据。
- 10000个不同非空lease owner_token均已过期，对应operations全部SUCCEEDED；当前store还要求合法非终态、owner、fence及锁后数据库时钟。20000次字段出现是重复表示。历史handle仍属敏感值，不据过期批准raw发布。
- 四个非UTF8值均32bytes；两个bootstrap raw_authorization_snapshot逐字节等于code_sha256，另两个为auth code摘要。code已消费、code/task过期，users/login_sessions/login_csrf/authorization_requests为空。独立结果见semantic-extra-independent.json。
- archive未发现私钥PEM/URI DSN/password assignment/Bearer header；4个sk-命中位于紧凑JWS签名随机子串，与worker语义核对一致。模式缺失不构成通用秘密不存在证明。

**CAPSEC-01（阻断不安全raw供给及现有安全总结）：109辅助成员并不都是无凭据文件。** 独立扫描发现native_rejection_xml与native_rejection_stdout各两处`password=`形式的libpq keyword DSN；URI-only扫描漏检。共一个不同43字符未脱敏password，host为单标签测试服务名。已离线逐值比对原private/pg.env相等，原run.py从该私有设置构造DSN并明确注入AGENT_GUARD_TEST_DATABASE_URL后跑原test（源SHA e3381edf28dd95ef7442d56a42231efd74340dcd2aba97e98be5c88fc6839832）。其纯历史隔离测试来源可核验，但当前有效性**UNKNOWN_NOT_PROBED**，password本身没有exp。没有DNS解析、服务连接或试密；不需为此做真实凭据可用性探测。

聚合证据为raw-log-credential-indicators.json、keyword-dsn-semantic-review.json、keyword-dsn-location-classification.json及keyword-dsn-origin.json。worker support-content-audit与报告需要补正：无postgres URI不等于无DSN；禁止两份raw日志进入Git或公开raw附件。补正可以保留旧审计原件，再新增更正报告，不能重写历史110字节以隐藏泄漏。这一发现不自动禁止全110认证加密的外部传输；它要求把辅助日志纳入同等秘密保护，且不再宣称全档无当前凭据。

## 4. 110最小闭包

原test逐SHA读全部110，故在保持原binding全部来源检查前提下，文件闭包仍是110。纯语义读取角色为archive+generation+execution+rejection XML，加formal_plan。stdout/exit/100原源码/3控制结果是来源资格证据；不能悄悄删掉以减少供给。

八表默认JSON payload独立复算总789734026bytes，与worker一致。即使投影缩到这些表，也仍是含token/proof的数据库数据，且会产生新SHA与新来源契约；不解决Git禁令。当前没有新投影或新数学输入被实施/接受。以新随机业务运行追求同一精确raw/wire/首次超限数字并不可靠，不能填常数或补齐字节伪造原历史。保持原110真实字节是本次最小风险路径。

## 5. 可实施外部密文契约

规则判断：AGENT明确不提交数据库数据、私钥、API token、.env、原始敏感日志；当前policy禁止raw秘密上传。原archive与两份DSN日志不得进Git，分片、LFS、加密后进Git都不能绕过数据库提交禁令。**只在Git保存安全manifest/SHA/来源与验证代码，外部保存成熟认证加密密文，Secret保存独立随机密钥**，实质上属于受控测试输入传输，可有条件采用；没有发现需要把“公有密文不能彻底撤回”扩张成自动禁止的依据。实际上传仍需主控按真人授权和既有门控明确执行，不由本报告授权。

实施必须满足：

1. **全110与原字节**：仅allowlist这110，不包含private/pg.env、worker整根、venv、私钥、无关日志或新凭据。公开manifest逐成员记录相对安全路径/role/length/SHA、archive来源与既有失败身份；所有原件保持SHA，日志也放密文。现有原DB测试password不得进入manifest/日志/命令参数。plaintext目录0700、文件0600。
2. **成熟AEAD及完整绑定**：采用经过维护且锁定版本/哈希的成熟库，256bit CSPRNG key、独立唯一96bit nonce，禁止口令充当key和nonce复用。AAD绑定格式版本、dataset ID、原manifest摘要、压缩与原文长度/摘要。可将约102MiB gzip作为一次AESGCM消息，体量允许且比自研分段协议简单；如分段，必须AAD绑定总段数/index/完整摘要并拒绝缺段、重复、乱序、尾随数据和截断。全部GCM tag通过后才向consumer暴露明文，不能边未认证解密边解析。成熟库文档明确nonce复用破坏安全、错误key/nonce/AAD/tag应失败：[Cryptography AESGCM](https://cryptography.io/en/stable/hazmat/primitives/aead/)。压缩器参数/版本记入来源；不同压缩字节可产生新cipher版本，但原110 SHA不变。
3. **多层完整性与解压安全**：下载固定asset ID/不可变版本，验证公开cipher SHA/字节长，再认证解密、核对完整压缩SHA，限长流式解压，核对每个原成员长度/SHA及archive的826390481bytes。不得直接不受限extractall；拒绝绝对/../重复/符号与硬链接、设备、未allowlist成员、额外压缩流与超长输出。失败必须非零、清理partial且绝不fallback到假输入。
4. **公有cipher、私有key如实披露**：公有Release上的cipher任何人可下载，访问控制只作用于key及明文，不称其为私有工件。key独立于fixture的SM2/DB密码；只Actions Secret提供到必要解密step环境，不经CLI参数或GITHUB_ENV，不入Git/artifact/cache/debug输出。使用最小权限且checkout persist-credentials=false；生成端本地key0600并明确生命周期，不上传原key文件。公有cipher可能长期留存，事后删除/轮换key不能撤回已复制的旧key+cipher，属于需接受的生命周期边界。
5. **可信head与runner边界**：Secret仅step env限制不保护后续明文，也不防此前恶意代码驻留。因此供给、解密器、workflow、build hooks、tests、当前源码及依赖必须在同一冻结、审查过的精确same-repo head；无不可信代码先行执行，第三方Actions固定完整SHA，依赖按锁/哈希并避免可变远端脚本。采用新鲜临时runner，不将明文跨job/artifact/cache传递。所有取得明文的代码都纳入可信边界，不能只审解密器。禁止pull_request_target/workflow_run替fork拿Secret后执行fork源码；GitHub明确警告这种形态：[GitHub可信事件与不可信代码](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)。
6. **缺Secret/来源时明确失败**：普通same-repo PR9可在合适Secret配置后执行；fork/Dependabot默认拿不到Actions Secret，这是供给限制，不能将fixed10000 skip/if跳过后算绿。必须保留完整原测试并非零失败，或经独立精确head审查后在可信事件运行同head完整必需check。不得放宽fork Secret策略来取巧。官方限制见[GitHub Secret类型](https://docs.github.com/en/code-security/reference/secret-security/secret-types)。
7. **持久性与重取**：Actions artifact有默认90天保留，不能作为唯一长期可复现来源；如采用，需固定run/artifact ID、校验摘要、过期明确失败及持久备份/重供给说明。[GitHub工件保留](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts)。现无私密对象服务时，公有Release仅cipher可行；约102MiB低于官方单asset2GiB限制，需固定asset与cipher SHA并验证实际下载，不依赖可变latest/tag名。[Release限制](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)。可用immutable release提高可用版本绑定，但需先确认仓库实际配置，且一旦不可变不得声称可删：[Immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)。
8. **consumer实际绑定与复验**：clean checkout仅凭已记录配置与安全取得的cipher/key即可重建原110路径，禁止ignored本地依赖。每个source/wheel真实安装自行bind-installed到当前全部139源码；测试保持原classification兼容但新增独立资格清单必须绑定当前源与原counter/test。原fixed10000必须实跑并保留所有数字/边界/NOT_ASSERTED；全6839原节点及其余CI仍需完整独验。
9. **证据出口和清理**：公开/CI artifact仅allowlist的脱敏聚合、退出码、JUnit统计、当前安装/来源SHA。不要上传整个evidence/root目录；失败trace同样可能重新暴露DSN。trap/finally在成功、失败、取消路径清理解密temp/plaintext/key env，不执行共享prune/down。记录own资源fullID/owner及归零；runner回收不是可证明物理内存擦除。

实施接受前的负探针至少包括：cipher位翻转/错key/nonce/AAD/截断/换manifest/错原SHA；缺Secret/asset失效；路径逃逸/链接/重复成员/额外成员/解压超长；错误当前source或旧安装；失败artifact无raw秘密。所有失败应非零且无consumer可读残留。应先用自有合成小fixture验证封装器，再对原110本地roundtrip逐SHA验证，最后clean GitHub same-head完整CI。

## 6. 本轮实跑与最终边界

原fixed10000本轮独立复跑 **1 passed / 0 failed / 0 error / 0 skipped，exit0，411.07秒**，Linux子进程峰值RSS 1715124KiB。10000操作、30009 journal、668批次、203285 objects、291623992 raw bytes、439169636 exact chunk wire及首raw超限对象165414/268436418 bytes、首object超限200001全部保持。结果在counter-independent-summary.json、counter-independent.xml及counter-evidence/exact-original-encoding-counts.json；最终聚合见counter-independent-aggregate.json。容器输入只读、network=none、cap-drop=ALL，未连接任何PG或外部服务。实际runtime信息见runtime-independent.json，固定镜像sha256:7c1484073ed19a42683234e65416e0ba78634c1715d2a220a9566ec959a71aaf；Linux x86_64在Apple arm64/Rosetta，性能不能冒充GitHub原生。

工具8项单测本轮独跑通过；另3个独立bind负探针wrong-installed-root/wrong-source-root/PYTHONPATH均非零且未产生binding输出。见unit-independent.xml、negative-probes.json。初次显式--platform的docker create失败（镜像metadata实为amd64）；未创建容器，随后由固定image自动选择架构并实际核验x86_64/Python3.11。失败历史保留说明，未冒称第一次成功。

本轮未实施加密/上传/Secret/workflow，没有重新安装全锁环境，没有重跑10000业务、完整6839/非PG/部署与远端CI。这些均NOT_RUN，不构成此局部架构审查的虚假PASS，但仍是完整实施接受/合并前硬门。

最终资源归零见resources-final.json；运行期间只检查/操作本轮创建且fullID/owner核验的容器，无PG/网络创建、无持久新私钥/env；原/worker私密证据只读保留，未删除他人资源。报告、SHA清单和所有自有证据为独立可复核输入。

**STOP — NOT_READY（当前clean供给未闭合）；外部全110 AES-256-GCM公有cipher方案可按第5节契约实施，绝不据此绕过原测试或最终完整独验。**
