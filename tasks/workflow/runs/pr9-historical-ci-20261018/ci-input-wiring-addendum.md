# PR9 CI输入装配与输出保密补充

真人授权仍为完整历史CI修复、全部检查通过后合并PR9，并纳入本地前端/Word/PDF。此补充不扩大业务语义。

主控独占ci.yml、tools/pr9_ci_run.py及其单测。容量传输独立审查通过后，主控已将唯一AES-GCM密文上传固定Release asset653345275；真实公共下载长度107401523、SHAfb5cf3fc1b0158568c726ca3afced324c6a9c18712dae0ab0beaa6a63d5a8975已核对。独立随机key通过stdin配置仓库AG32_CAPACITY_KEY Secret，不进入Git、参数或公开日志。该持久受管Secret是CI环境依赖，不计为待清理的临时文件。

CI严格使用same-repo head、完整SHA Actions、无持久checkout凭据；fork/Dependabot明确失败，不使用pull_request_target。所有runner代码/构建hook/依赖/测试均属于同一可信受审head边界，不能声称step env提供代码隔离。未来任何改变此边界的head必须重新审查。

根CI项目改为真实非editable安装；全21哈希锁定版本和原x402锁不变。取得密文不带GitHub认证，核验固定asset ID/name/URL/length/SHA；解密key只在unpack step env，AEAD及110成员原SHA全过后交付。prepare产生readonly nested /capacity/inputs绑定，根consumer另用自身3.11/site-packages逐139来源/import核验。每个source/wheel消费者仍须独立绑定自身安装。

部署UUID-only ownerbase和source/wheel安装证据使用分离私密目录。always先严格cleanup-all依据实际完整ID/owner/run/project清理所有已记录资源；未知身份失败并保留，不prune。之后清理本轮解密/复制输入、测试私密日志/tmp、审计临时CA/key。GitHub runner服务实例按job生命周期销毁。取消/超时必须走always，原6小时job内保留20分钟尾部预算；测试deadline从开始装配计340分钟。失败不得吞掉，不跳原6839节点。

新增私密pytest运行器仍调用原完整pytest范围，原生exit/JUnit结果决定成功。stdout/stderr、JUnit及basetemp仅落本轮0700/0600私密目录，公开只输出elapsed/count/native exit；不输出原始历史DSN、失败堆栈或上传整个artifact。集成任何skip均失败；非集成原有skip保留可见计数。测试启动失败、JUnit缺失、失败/error、取消、超时均非零。真实子进程负例验证通过/失败/skip策略、现存与链接路径拒绝、缺JUnit与取消转发，不以伪造JUnit替代业务执行。

本补充不是完整实施接受：全部writer STOP、完整候选SHA冻结、新high实施审查及最新head完整GitHub CI仍是合并门槛。原失败日志和未跑项目保持记录。
