# 部署公开控制输入与有界清理补充

原生Linux下角色UID210xx必须读只读bind的/control公共输入，host umask077不能让这些公开输入变为角色不可读。授权部署worker仅将control子目录设0755，严格allowlist settings.json、allocated-plan.json、approval-messages.json、approval-proofs.json、bootstrap.json五文件设0444；host祖先owner根仍0700，角色mount仍readonly。这些只含scope/ID/角色分配/公开签名/摘要/计数，不包含私钥、完整令牌、DSN、口令、secret注册凭据或原业务行。记录bootstrap必须先校验RegistrationDescriptor闭合字段/类型/摘要与scope，不能把任意operator value写入公共文件。其它private/env/key/raw路径继续0700/0600，不将整个owner目录开放。

cleanup-all接口为--root PR9_DEPLOY_INPUTS_ROOT --cleanup-all，可选--installation-evidence-root SIBLING。base0700、原absolute路径及祖先无symlink、仅UUID子dir；安装证据为source/wheel/UUID及0600 installation-state.json，记录mode/run/owner/imageFullID/tag/创建containerFullIDs，创建后逐次持久化。清理每一资源先核验fullID、owner/run/project或准确image标签与专属tag绑定，仅删除本轮记录资源。已有删除可幂等；坏JSON/symlink/未知entry/归属不符不删除，继续处理其它合法owner但最终非零。原私密证据不删、不上传，聚合只含数量/错误类/未知名哈希。SIGTERM/finally与CI always使用同一严核验；不能吞cleanup失败伪装0，不做全局prune。

job总预算按完整历史矩阵设有界6h，并给最后always清理留5–10分钟；不改单项测试等待预算，不跳过原1000clock/20继承组或原节点。实际总耗时仍需本轮实测，不把估计当结果。
