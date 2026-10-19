# PR9 传输子域独立 IMPLEMENTATION_ACCEPTANCE r1

结论：**ACCEPTED_FOR_ENCRYPTED_EXTERNAL_PUBLICATION**。本轮是全新独立上传前传输实施审查，接受范围为本报告冻结的封装器、安全公开metadata及指定最终外部密文候选；没有发现该局部范围的阻断缺陷。这不是重复PACKAGE_REVIEW，也不是PR9完整最终接受、已发布供给或合并批准。effective model/reasoning metadata=UNKNOWN，不以请求角色参数冒称后台证明。

根任务可按既有真人授权及供给契约继续处理**仅指定密文**的外部发布；本报告不批准raw/archive/DSN日志、key、数据库数据或加密payload进入Git/LFS。公有cipher任何人可留存，控制的是key及明文；旧key+cipher被复制后无法靠删除/轮换撤回。本轮没有上传、设置Secret、网络访问、Git写入、PG或子agent。

## 1. 独立依据与冻结范围

直接读取AGENTS.md、AGENT.md、current-policy、package-v1、user-local-updates、capacity-supply-contract-v1，以及capacity-security-review/report.md全文和第5节全部门控；核对相关README、方案、安全/验收和review-contract、实际工具/测试/原counter/fixture及四份metadata。安全报告SHA为`b79c2585a3d95e719e704cff0dad25f98319b76cee76c4baef893af10946e55f`，worker STOP报告SHA为`c2e63ad0eb383e58afaae1b7f16b0003c4dd634d9b60743b4a35086cd4cca552`，均独立复算吻合。

reviewed-inputs-start.json与reviewed-inputs-end.json共**160项，逐项完全相同**，含当前139个业务.py、工具/测试/fixture、相关契约与安全报告、pyproject和四份metadata。另独立复核source-map的148个实际路径SHA全部吻合。其他deployment/A31/CI及用户文件存在独立writer，未修改，也不据此作全PR冻结/接受。

|冻结输入|SHA256|
|---|---|
|tools/pr9_capacity_inputs.py|631889021ccbcd3d2059584c15d7b6d6f76f159bafe4d3d6f8f9806f26ad69cb|
|tools/pr9_capacity_transport.py|ca8a7661181df037c61f58f2335d488a6d57fd59c6fd5c89b5d9481cb07c1919|
|tests/unit/test_pr9_capacity_transport.py|332e291a8e336b9a7f505f4637f3ef1cb4c489783fd068383597674174ca0417|
|tests/unit/test_pr9_capacity_inputs.py|d08ffbc07db9f64bc6e5abe2b6d9da6ebc6c350e778884b0c986bea74e830636|
|dependencies/pr9-capacity/README.md|039391cabe013b231a74a7a6eafe553629804272c6c2b108e694fbd5f1f29de5|
|dependencies/pr9-capacity/source-manifest.json|a83e5c91dc5423dfa7a80dc442d04fd5a54fc3dd410448f1161a9c6880422fcf|
|dependencies/pr9-capacity/source-map.json|cdea4b8510c6e900b084f269bb6cd7cbaf3d911669b45efa958247688a0933f2|
|dependencies/pr9-capacity/transport.json|a997268036fdba8d9f9912342baef17a0c7a81b7f46f37ca70329adfb6b5230d|

最终cipher **107401523 bytes**，SHA256 **fb5cf3fc1b0158568c726ca3afced324c6a9c18712dae0ab0beaa6a63d5a8975**，开始使用及结束保留核验均一致。精确key/cipher定位只读取worker的0600 private-context.json，不复制其定位、key值、base64、key指纹、JWT、DSN或raw到报告。

## 2. 第5节契约逐项结果

|契约|本轮直接查证与实跑|后续边界|
|---|---|---|
|1 全110及原字节|PASS：以SHA4509d6…的原fixed-capacity-dependency-r6.json独立pack；manifest与冻结公开manifest完全相等；仅110原成员，合计828090701 bytes，archive仍826390481 bytes。另逐份核对最终cipher解包与原件的长度/SHA，110/110。合成源根有private/pg.env及未列文件，pack输出不含这些字节。|不允许改写原敏感日志来隐去历史；不能上传raw。|
|2 成熟AEAD与绑定|PASS：实际cryptography50.0.2 AESGCM，os.urandom32-byte key/12-byte nonce；两次独立合成pack的key及nonce不同。AAD覆盖格式/dataset/canonical manifest SHA/framed与gzip长度SHA/compression/nonce。错key/nonce/AAD及重算公开SHA的损坏cipher均在创建任何输出目录前失败。|物理内存擦除不可证。|
|3 完整性及解压安全|PASS：cipher精确长度/SHA→完整GCM认证→gzip长度/SHA→有界解压→header/逐成员SHA→原文SHA完成→rename为ready root。无tar/zip、payload路径或链接记录。正式测试与独立探针拒绝截断、额外gzip流/尾随、bomb/超长、SHA错、重复/重叠/绝对/../链接/额外字段，失败清理。|实际下载固定asset ID尚未实施。|
|4 公有cipher与私有key|PASS本地：最终key为私密目录内0600单链接文件，CLI只收路径/env名称；env值被读取后pop。四份公开文件中最终key的raw/base64/hex及两DSN日志实际43字符password均无匹配；不输出这些值。README如实披露公有cipher及不可撤回边界。|repoSecret设置、step-only传递及CI无GITHUB_ENV/artifact/cache，仍由root在后续精确head闭合。|
|5 可信head/runner|PASS本地边界：固定镜像、network=none、cap-drop ALL、repo只读、独占输出；本轮所有取得明文的探针及消费者脚本随报告保存。|完整workflow/build hooks/其余源码/依赖的same-repo frozen head、fresh runner、Actions完整SHA、persist-credentials=false、禁止fork提权事件，仍是最终独验硬门。本轮不接受这些未完整审查部分。|
|6 缺来源/Secret硬失败|PASS局部：缺cipher/缺key/env均非零、stdout空、固定安全stderr且无明文树；没有fallback或skip。|实际asset失效/Secret缺失的工作流门控必须再实测，不由本地缺文件测试替代。|
|7 持久性及重取|README记录固定asset ID/长度/SHA及持久供给要求；当前明确UNPUBLISHED_PENDING_ROOT/id=null。|NOT_RUN：实际发布、固定ID下载、重取验证、保留/重供给说明完成情况。不得使用latest或短期artifact冒充长期来源。|
|8 消费者实际绑定及原counter|PASS本地：本轮新建非editable应用安装，prepare后消费者自己bind全部139源码/import origins，无PYTHONPATH；错root/PYTHONPATH和同139树单文件字节变更均拒绝。未改原fixed10000测试本轮1/1通过，保留所有原数字/边界/NOT_ASSERTED。|依赖来自固定镜像，未声称全锁全新安装；source/wheel其余consumer、全6839及其余CI仍待最终独验。|
|9 证据出口和清理|PASS本地：只保存明确allowlist的manifest/SHA/聚合/JUnit/安全退出结果；原日志及明文输出不保留。真实子进程SIGTERM在认证后.partial存在时，exit1且树被清理。最终自有资源/明文/key/env均0，root候选保留。|CI成功/失败/取消的always/trap、runner回收和禁止全root artifact仍须最终工作流实测；SIGKILL/宿主崩溃不能承诺finally执行。|

## 3. 独立实跑及探针

运行脚本为run_independent.py、probes_independent.py、cancel_independent.py、pack_independent.py、bind_byte_negative.py，均只写本目录。实际环境：Python3.11.17、cryptography50.0.2，固定镜像`sha256:7c1484073ed19a42683234e65416e0ba78634c1715d2a220a9566ec959a71aaf`，Linux x86_64在macOS Apple arm64仿真环境。以下时间只描述本机条件；pack与counter局部并行过，不能据此声称GitHub原生性能。

- `python -m pytest -p no:cacheprovider tests/unit/test_pr9_capacity_transport.py tests/unit/test_pr9_capacity_inputs.py -q`：**44 passed、0 failed/error/skipped，exit0**。见unit-independent.xml。
- 四个工具/测试文件的`ruff check --no-cache`与`ruff format --check --no-cache`：exit0，见ruff-check.txt/ruff-format.txt。
- **21项**额外独立合成负探针：真实GCM错key、改cipher并重算公开SHA的InvalidTag、错nonce/AAD/manifest/截断；重叠/逃逸/重复路径及link字段；认证后多gzip流/尾随/5000000-byte额外解压bomb/截断gzip/错成员SHA；pack allowlist、独立key/nonce、原有目的目录保护、缺env/asset固定安全CLI、公开metadata无payload。见negative-independent.json。不是对正式测试名称的转述。
- **1项真实取消探针**：子进程GCM认证成功并创建.partial后，父进程实际发送SIGTERM；exit1、stdout空、stderr固定安全句、partial不存在，源件及输入key保持。见cancel-independent.json。
- **4项额外bind拒绝**：wrong-source-root、wrong-installed-root、PYTHONPATH、同139文件但一份源码字节不同；均非零且无binding输出，最后一项实际到达SHA mismatch。见bind-negatives.json/bind-byte-negative.json。
- **全110独立pack**：原binding先实际SHA核对为4509d6…；约15.866秒，输出manifest与冻结manifest完全相等；gzip107401507 bytes/SHA25c080…可复现，压缩明文临时件已删除。新生成key/cipher全部清理，不替换root候选。见pack-independent-summary.json。
- **最终cipher全110独立unpack**：约5.655秒；828090701原成员字节逐SHA/长度与真实原件相同，目录0700/文件0600，见members-independent.json。
- **新应用实际构建安装**：从本轮当前源码和完整必需build输入经`pip install --no-index --no-deps --no-build-isolation <own project>`进行非editable安装，依赖通过显式image-runtime.pth读取固定镜像的既有包，未指向源码/PYTHONPATH。应用__file__及139个import spec/SHA均指向本轮安装；pipcheck exit0。见installation-independent.json、consumer-pipcheck.txt、actual-build-inputs.json。pyproject为adb600…；实际打包的requirements-ci.lock为1b9a10…；本轮没有全锁依赖重新安装。
- **原fixed10000真实消费者**：`<own Python> -m pytest -p no:cacheprovider tests/integration/test_a32_joint_tls.py::test_real_fixed_10000_capacity_preflight -q`，**1 passed、0 failed/error/skipped，exit0，418.354秒**，见counter-independent.xml/counter-aggregate.json。10000原操作、30009 journal、668批、203285 objects、291623992 raw bytes、439169636 exact chunk wire、首raw超限object165414/268436418 bytes、首object超限200001全部保持。`acceptance=NOT_ASSERTED`、footer仅length seed占位、TERMINAL原行算术边界保持；这不是新10000业务运行/PG导出或旧A3完整实验接受。

独立AST比较也确认checked/sha256/write_private/prepare/bind_installed相对读取的旧worker源快照未改；快照实际SHA明确保存在inputs-ast-independent.json，不把不同旧快照混作同一冻结版本。工具审计补充keyword DSN，CAPSEC-01勘误保留旧历史；两原日志password当前有效性仍**UNKNOWN_NOT_PROBED**，本轮没有解析DNS、连接或试用。

## 4. 本轮装配失败如实保留

前两次独立安装启动使用嵌套venv的`--system-site-packages`，未继承镜像`/opt/venv`依赖路径。attempt1 pipcheck exit1；attempt2保留pipcheck五项依赖不可见记录，pytest启动exit1且未取得有效JUnit，不计为通过或44项已执行。仅修正本轮审查脚本为显式image-runtime.pth后，完整新建安装、pipcheck、44单测、110/139/原counter全部重新执行通过。未修改候选。记录为independent-summary-attempt1/2.json、consumer-pipcheck-attempt2.txt。

另第一次额外pack探针误选同目录的native-business-qualified-dependencies-r6.json，原SHA预检查即失败，未进入pack；随后改用实际SHA4509d6…的fixed-capacity-dependency-r6.json重新完整pack通过。见pack-independent-summary-attempt1.json。上述审查装配失败没有被抹成首次全绿，也不构成候选缺陷。

## 5. 资源、出口与尚未执行

每个运行容器使用随机本轮owner、明确创建返回fullID；主运行fullID及owner/网络/退出已归档在main3-resource-identity.txt/main3-completed-identity.txt，其余身份见各resource-identity和container-id文件。只操作自己创建的资源，无PG/网络创建，无共享down/prune。resources-final.json对本轮11个精确owner逐项查询：容器**0**；自有private/probe/pack/cancel树**0**；自有明文、压缩临时明文、key及秘密env文件**0**。原worker/root候选cipher/key依然存在，cipher SHA未变，key模式0600；未删除他人材料。

公开证据仅本报告、代码探针、SHA/安全metadata、JUnit统计及容量聚合；所有本轮生成的数据库明文、准备后复制件、新安装及私有原日志均已清理。对本轮保存文件另查最终key raw/base64/hex与两原DSN日志实际password，无匹配；未输出实际值。Python/容器/runner回收不证明物理内存擦除。

**NOT_RUN且仍为后续硬门**：实际asset上传/固定ID下载/远程SHA长度重取、repoSecret设置、最终same-head workflow与完整trusted执行边界审查、全部6839原集成/其余非PG/source-wheel/部署矩阵、最新head GitHub全部CI。当前asset仍UNPUBLISHED_PENDING_ROOT；本报告不得把这些状态改写为PASS。完成实际asset定位后须再次冻结最终完整候选并进行fresh完整独验，最新head全CI绿后才可由root按授权正常合并。

**STOP — ACCEPTED_FOR_ENCRYPTED_EXTERNAL_PUBLICATION，仅上传前传输子域。**
