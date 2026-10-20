# PR9 C8 r5 — STOP_SCOPE_REDUCED，实际结果交付

全新独立 reviewer，requested gpt-6.1-sol/high；后台 effective metadata UNKNOWN。最新真人明确要求不再完整复核，root于本轮运行中转达停止扩展、停止 ordinary 并提供实际结果/论文性能边界。本报告遵从该最新范围，**不是完整 IMPLEMENTATION_ACCEPTANCE，也不判为完整全绿**。source/wheel 完整域未启动。没有修改受审源码、原测试、204原夹具或用户文件，没有 Git/远端操作。

## 本轮实际结果

|项目|本轮独立实际结果|计时与证据|
|---|---|---|
|完整非集成|2303节点：2302通过、0失败/错误、1原跳过；native0|pytest suite476.376秒；`nonintegration.xml` SHA8c5b3655b3e3c25ac193c3e2798cdcd1046e2538ba0218f52af495a38af22f0e|
|原RealCli补闭|独立1通过/0跳过，真实Docker六用例通过、资源空；native0|suite6.415秒；XML SHA5d324e3a2f409b28217ba4f48abc153764d76e568ba642f5f3fde35a2470386c。新范围指令到达前已自然完成；不伪称原2303同轮零skip|
|普通集成部分|91具名节点通过，0失败/错误/skip，随后人类要求SIGINT；native2|suite546.425秒含被中断工作；XML SHAe3400bf3a411f340dbdfd70b3d5aedd4c4f48632ed409c2802750ccbe035ca60|
|原容量计数|已进入执行但被中断，**未完成/无PASS**|XML另有1个无name/class、time0中断占位，不能计第92个通过；原fixed10000数字不作本轮完成声明|
|完整收集|6839集成、2303非集成；唯一并集6839、分区6821/9/9、零重叠|collect native0；分区是计划，source/wheel未执行|
|观察器补正|新Linux3.11下正式helper单测全部通过；另独立64真实Popen均通过，25次观测到早期非声明argv，最终kernel/start/UID/startup/atexit均匹配；另真实wrong-argv、wrong-UID拒绝|`startup-real-summary.json`；不是密码性能基准|
|容量公开链|无key公开下载107401523bytes/固定SHA→独立短命decoder AEAD110→退出销毁→无key CLIprepare/严格validator/实际新安装139绑定；四种真实provenance篡改均拒绝且无输出|`fetch-isolation.json`、`decoder-isolation.json`、`capacity-independent-summary.json`、`capacity-independent-negatives.json`|
|工具与质量|全21 CI+41 x402锁哈希安装、最终逐版本核验/pipcheck通过；fresh Rust1.99.1 locked构建真实Linux ELF64/e_machine62；Anvil固定SHA、版本和来源脚本通过；全局Ruff/format及Node语法/前端逻辑通过|`final-target-inventory.json`、`rust-independent-build.json`、`quality-results.json`、`host-node-results.json`|

完整非集成已实际覆盖本轮新增观察器单元；精确数见 `completed-static-runtime-evidence.json`。普通域装配真实三独立verify-full PG/system_identifier，实际139安装绑定和拒绝角色均通过。没有把root/low历史结果记为本轮重跑。未执行完整6839、两mode各20继承组、完整12角色/故障/注册/scenario矩阵或最新head GitHub CI；root后续按最新真人范围决定发布门控，不由本报告声称这些已绿。

## 性能数据的使用边界

本轮上述476.376秒、6.415秒、546.425秒是**测试套件耗时**，含装配、数据库、负例或中断，不能写成SM2签名延迟、吞吐量或论文密码性能。64进程是观察器正确性样本，也不是SM2性能。没有新增完成的密码性能benchmark；原容量算术被中断，不产生新容量结果。论文如引用既有基准，须由root引用其原始记录、样本n、统计量、计时边界与环境，明确为既有测量，不能重标为本轮新跑。

实际环境：Apple arm64宿主、Docker Desktop29.8.1、Linuxamd64/Rosetta翻译、Python3.11.17/nonroot UID501。daemon15 CPU/8318844928bytes；own controller cgroup无限额，共享daemon仍受该上限。普通域与非集成曾并行，Rust在其前完成；不能声称Linux amd64原生性能。长hostdriver均process-scoped caffeinate，无持久电源/业务时钟修改。

## 冻结、用户资料与保留失败

C8 manifest SHA36af36390566b80dba30e5f5acf09aba243dfe74b3d210856c1abffbe4728669，base eafb6f28aa87a041e149c0190b76054424f1c9cf。开始shared+RO逐1235成员全部一致，symlink按link text。结束RO1235仍全部一致；shared1234一致，仅`tasks/workflow/current-policy.md`因最新真人范围更新发生漂移；manifest不变。该漂移如实记录，不将缩减/中断审查包装为冻结完整接受，也不误称业务源码故障。独立核139业务+18SQL与base逐字0差异；196原Python+8sidecar对真实历史原路径/provenance全核通过；source-map151当前SHA全匹配。C7→C8 AST独核：原helper声明仅execute_observed_command改变，verify_observer_output及其它旧声明同AST。

CSS/03docx/main.pdf三SHA与冻结值一致，DOCX ZIP/XML有效。读root12Chromeview/13docxpage/15PDFpage全部可读报告及真实UI成功/失败保留记录，并独立查看既有overview/cosign/x402截图、DOCX首尾页/PDF首尾页；此为既有渲染查证，**未独立重新浏览器运行或重新渲染全文**。新glossary/rename-guide已全文读，作为保存的用户文档，不执行改名、不采用卖点作为本轮能力或实施授权。草稿/红待填与未来状态承诺边界保留，缓存不提交。

本轮没有确认新的源缺陷。保留初代理TLS EOF失败；直连重试成功。私有driver的重复HOME mkdir、x402[evm]版本查询名称错误与首次无命中中断选择均保留为装配错误，修正只发生在自有脚本。首次通用XML摘要误把无名中断占位计为通过，原件改名`attempt1-generic-ordinary-xml-summary.json`保留；最终只认91具名完成节点。所有原失败/未跑均未抹去。

## 清理与最终边界

受控SIGINT发给actual owned pytest PID22，原pytest保留部分JUnit/native2，inner与host严格cleanup native0。独立按18个own owner过滤查询 containers/networks/volumes/images四类全部0。只删除自有解密/prepare原件副本、安装/构建/源码复制树、临时PKI/keys/env，未删root保留工具像、原key/cipher/受管Secret，未知历史卷仍UNKNOWN且未碰。raw日志/XML/native记录仅本地0700/0600保留，不授权公开上传；不声称物理内存擦除。

**STOP_SCOPE_REDUCED。本轮实际结果可交付；完整实施接受、完整历史CI绿色及合并状态均不由本报告宣称。**
