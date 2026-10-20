# 完整历史集成测试的环境与输入

完整集成测试除普通PostgreSQL连接外，还需要独立审计库的verify-full TLS、本轮真实部署资源，以及固定10000容量预查的原始输入。只有基础数据库连接不构成完整验收环境。CI保留全部原集成节点；缺少前提必须失败，不能静默跳过。

主CI使用Python3.11、PostgreSQL16、OpenSSL、Docker Compose/buildx、原README复现命令所需zsh，以及既有Rust1.99.1和固定Anvil。zsh仅为测试控制器工具，由runner发行版签名APT仓库安装，不进入业务Python依赖或普通角色的新权限。requirements-ci.lock为原runtime/dev相同版本及既有构建工具增加wheel哈希，安装必须使用--require-hashes --only-binary=:all:；项目构建禁用build isolation，主CI项目也使用真实非editable安装。来源见[依赖说明](../dependencies/pr9-ci/README.md)。原runtime/dev版本锁和原版本断言保持。

主CI分别启动业务、下游观察域和审计三个独立临时PostgreSQL实例/连接，下游域用真实MockDownstream建表，供审计原子性测试比较全部非系统表，不能以空缺环境变量或authority同DSN替代。tools/pr9_ci_audit_tls.py只配置显式传入且完整容器ID和owner标签相符的临时服务，生成本轮CA和localhost/127.0.0.1证书，实际以verify-full TCP连接确认TLS，再生成私密receipt供测试夹具验证。本轮PR9_A31_TLS_RECEIPT及PR9_CI_OWNER绑定真实容器、证书SHA、路径和模式；旧历史装配分支保留。文件和目录必须为0600/0700，不能用假旧owner记录代替本轮资源身份。导出HTTPS另用原test_gateway_tls.certificates生成本轮独立CA与仅gateway.agent-guard.test的SAN证书，通过A32_EXPORT_TLS_DIR传入并在always清理；source/wheel各20组也各自生成同样独立材料，保持原错CA/错SAN断言。

容量预查保留原10000操作、30009 journal、668批次、203285 objects、291623992原始字节、439169636线缆字节及原超限边界。其含义是当前codec对固定原件的容量算术预查，acceptance仍为NOT_ASSERTED，不代表重新运行10000业务、完整PG导出或完整bundle验签。历史96+4是旧native对旧安装的比较；当前源码需另做实际安装绑定与局部资格复核，不能把旧标签直接当新业务接受。

完整来源闭包是110份原字节。数据库快照含过期合成token/proof、无exp的审计回执和终态租约handle；两份历史失败日志还含libpq keyword DSN/password，已离线确认隔离测试来源，但当前有效性未知且未探测。不得将原件、原始日志或加密分片提交到Git。供给方案仅在Git保留安全manifest/来源SHA与程序，外部Release只保存认证加密密文，独立随机key仅由仓库Actions Secret提供。

公有Release密文可被任何人下载留存，只有key和解密明文受控；删除或轮换不能撤回别人已持有的key+cipher。传输程序使用锁定的成熟AES-256-GCM；认证、压缩长度/SHA和全部成员长度/SHA通过前不交付输入。固定来源asset失效、缺key、任意校验失败均非零退出，不fallback或造数据。明文与key不进入GitHub artifact/cache，原始测试失败堆栈也不得整体上传。

取得明文的同一runner内，workflow、解密器、构建hook、源码、测试及依赖都必须来自受审的可信same-repo head；仅把Secret放在解密step不足以隔离后续代码。相关Actions固定完整SHA且checkout不持久化凭据，不使用pull_request_target或workflow_run为fork执行不可信源码。fork/Dependabot缺Secret时明确失败，不通过跳过容量测试制造绿色结果。

部署测试按每个消费者新建本轮12角色、3个verify-full PG域与网络。source/wheel都真实非editable安装，逐139个当前Python源码和import origin核对，并检查21个锁定版本及安装后的锁文件SHA。各消费者重新bind-installed容量输入；只读原件和不可变构建层可复用，动态资源、秘密、安装身份与旧JUnit不可复用。清理只能依据完整ID和owner/run/project身份回收本轮资源，不使用共享down/prune。

继承的20组命令还包含旧A1/A2/B测试：其中的固定数据库名必须指向本轮独占PG内实际创建的数据库，保留原current_database身份断言；不能只给所有文件同一个DSN。A2明确使用的历史独立迁移目录只含原001–006，并逐源文件与安装文件核对SHA；其它使用当前默认迁移集的测试则保留旧迁移序列前缀，并精确校验新增008/009及registry元数据。原七张业务表快照、完整旧registry前缀、非法升级回滚、幂等和负例均必须保留。观测日志只映射到本消费者私密证据目录。204份原始夹具不改写，逐处物理适配与语义资格复核另存原始/执行SHA及AST；不能把原始全等断言已作资格适配说成字节未改。C5独立审查发现的真实阻断与下一轮修复边界见[拒绝与修复契约](../tasks/workflow/runs/pr9-historical-ci-20261018/candidate5-rejected.md)。

三个旧独立探针还固定了原37表集合。当前真实完整迁移schema为41表，需明确保留原31表与审计6表，并精确加入threshold approval及三张payment表；不能过滤新增表以满足旧数量。完整前后状态比较应覆盖全部41表，观测标签区分历史37与当前41，并用新增表快照变动的负例验证拒绝效果。

下游完整schema还包含现行MockDownstream.provision创建的ds_cosm2_bindings，因此完整状态集合为原三表加该表，共四表；它与008/009的来源不同。原A2.effects()三表兼容视图保持原定义，声明完整状态比较的测试则必须包含四表，并区分历史3与当前4。测试控制器还须把PostgreSQL inet值规范成host地址后与记录的Docker IP精确比较，所有资源身份与TLS校验仍需通过。

当前CI环境修复的范围与最终状态以[本轮任务包](../tasks/workflow/runs/pr9-historical-ci-20261018/package-v1.md)、[本地更新补充](../tasks/workflow/runs/pr9-historical-ci-20261018/user-local-updates.md)及[现行工作流](../tasks/workflow/current-policy.md)为准；这份环境说明本身不声明全量测试或远端CI已通过，也不接受旧A3四万条长实验。

当前固定密文位于[CI输入Release](https://github.com/Qdcchh/agent-guard/releases/tag/ci-capacity-inputs-20261018-r6-v1)，asset ID653345275；Git中transport.json固定其ID、长度及SHA，缺失或漂移必须失败。AG32_CAPACITY_KEY为受管仓库Secret，刻意持续保留以供后续CI；本地临时复制及解密明文另行按owner清理。

原始pytest stdout/stderr、JUnit和临时目录只写job内0700/0600目录；公开输出仅为原生退出码、耗时及实际JUnit计数。完整集成出现skip亦失败，不会用隐藏失败文本换取绿色。always先按fullID/owner回收已记录部署资源，成功后清除其私密材料，并清理本轮输入与日志；未知身份会令清理非零，保留私密现场到临时runner销毁，不宣称已清零。

原A32真实HTTPS端到端测试并存两套独立CA及服务：audit.agent-guard.test解析到127.0.0.1:443，gateway.agent-guard.test解析到127.0.0.2:443。只在临时CI VM和trusted测试控制器装配这两映射；VM通过临时sysctl允许非root测试用户绑定443，先验证DNS和两地址端口可绑定。普通业务角色及用户Mac网络不变，原URL、SAN和证书验签全部保持。

演示镜像先在独立层安装21项同版本、同SHA锁定依赖，再按INSTALL_MODE进行source或wheel的非editable项目安装和pip check。切换安装模式不再重复下载同一依赖层；首次依赖获取仍需真实网络成功，不关闭TLS或放松哈希。

C6独立审查发现公开传输重建binding与原始binding是两个不同文档，prepare不得把重建文件SHA当原始历史SHA，也不得盲信自报original_binding_sha256。修复必须保留两层实际SHA、与固定公开manifest的完整重建关系及全部110原件/139当前安装核验；原失败保留，后续重新完整独验，详见[C6拒绝与修复](../tasks/workflow/runs/pr9-historical-ci-20261018/candidate6-rejected.md)。

后续补正采用同一纯重建函数连接unpack与prepare：prepare先核固定manifest canonical SHA和transport元数据原字节SHA，再要求收到的重建binding逐字等于合法canonical加换行。仅实际原binding原字节SHA可走原历史分支；缺marker不能回退。qualification分别记录可信历史SHA、实际接收文档SHA及manifest SHA。旧151文件来源图已按原字节归档，现行来源图显式更新四项修复并要求新一轮完整接受；密文及Secret未重发。

C7全新独验还确认Rosetta启动包装argv的短暂状态会令单次/proc命令行采样误拒绝真实原A1成功进程。补正仅对父启动采样增加有界严格条件等待；保持真实kernel身份和退出观察器全部校验，参见[C7拒绝](../tasks/workflow/runs/pr9-historical-ci-20261018/candidate7-rejected.md)。
