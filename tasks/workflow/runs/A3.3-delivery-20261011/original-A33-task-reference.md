# 原A3.3任务历史参考

下列原文为历史规划证据（包含当时的角色/前段pending/停止条件），不授予当前实施；现行状态以package-v1与最新真人授权为准，原安全与交付子义务完整保留。

# A3.3 无模型API部署复现与三代理演示任务包草稿

状态：**NOT_RUN / NOT_FROZEN / 非 PACKAGE_READY**。日期2026-10-05。本文件只是ignored规划草稿，不是正式开工包。请求worker gpt-6.1-sol/medium，有效后台metadata UNKNOWN。当前A22补正，不能推定最终accepted基线；A23/A31/A32未来API须从实际accepted源码/矩阵/报告重新绑定。不修改design-v1.md、design.md或revision原件，不建业务资源、不执行DB/容器/业务测试、不写Git/index。真人连续A3授权来源为tasks/workflow/runs/A3-closure-20261004/authorization.json，阶段仍须前段ACCEPTED、精确正式包审PACKAGE_READY后实施。本草稿本身不能放行。

依据：AGENT/AGENTS、README、接口/安全/acceptance、原tasks/A2-execution-gateway.md完整P01-P21、implementation/review/current-policy、前段实际accepted全矩阵。requirements-additions-v1.json保留逐项出处/原行为/子断言/具体拟测试函数与全30目标/全21P原文。ownership-v1.json为candidate名单而非当前授权。

## 目标/必要与可选

真实用户同意→AS根授权→planner/selector/executor两个AS签child→四工具真实签名HTTPS→sharedbudget/幂等/撤销/UNKNOWN恢复→READYreceipt/query→journal→独立auditcheckpoint→auditroleexport→独立trusted config离线验证。三holder真实独立进程及OS/mount/network权限实证；共同宿主管理员仍trusted，不宣称跨组织隔离。

必要DID：operator已有独立批准tenant/client/DID/kid/SPKI/purpose registry，从固定did:web HTTPS通过开发CA/SAN有界/no-redirect真实取得，用现有IdentityResolver验证后批准冻结did_documents并受控只读分发；保留现有AS/GW immutable快照装配，无需生产resolver新mode/config/factory。负例错CA/SAN/redirect/未知路径/controller/用途/SPKI替换不能形成新批准配置，启动后远端变化/原dict变化不改变captured字节；轮换需operator审批新kid/持钥证明/动态停用旧key。默认网络resolver已有B回归继承。

必要下游：MockDownstream独立DB/连接/事务+服务secret+固定tool/quote/recipientallowlist+真实order/notificationeffect；可信internalworker持有，holders无凭据/无DB网络route。独立下游RPC/TLSdaemon是未要求的可选增强，此包不包含。AS/GW/audit/publisher/worker各rolekey最小私有mount；现factory实际DSN要求如实说明，不凭envunset称隔离。已有SDK/canonical/SM2/proof/receipt投影/verify复用，不复制密码验权。

## 可执行文件与接口约束

候选文件逐项见ownership：demo/config/client/handoff/fixture以及init/didbootstrap/provision/worker/CLI最小接口先共享前置串行完成自查、停写、freeze实际SHA。phase2 holder/runner/faults/scenario tests只消费此冻结API及固定fixture；role/clean deployment tests另独占文件/资源消费同一冻结前置，不与scenarios互读半成品。完整deploy/demo/compose.yaml及docs/README/HANDOFF/A2report/pyproject只singleintegrator在worker停写后整合。缺真实前置接口时继续串行，不能派依赖尚不存在API的并行worker。

拟CLI：python -m agent_guard.demo init/check/provision/start/normal/attacks/faults/export/verify/stop，各只读/私有roleconfig显式runUUID/outputowner；这不是当前可用命令。bootstrap注册user/password/principals/taskpolicy，不能调用create_task_root/child替代公开ASflow。真实cookie/CSRF/state/nonce/S256code+IDToken验证、父Basic+delegateproof两次交换；invoke/resultread固定endpoint/bodypurpose，新jti。当前A23 publisher/A31 audit/A32 export/verifier实际acceptedAPI重核再写精确constructor/CLI。公众入口不暴露recover/sign/fault/任意URL。持续worker固定不可变operation、有界批次/公平轮转与既有lease，不每request起Python冒充正常成本。

## 逐项运行计划

- A33-01 角色初始化与可信渠道：tests/integration/test_a33_roles.py::test_role_init_trust_and_private_mounts；unit + real-PG integration + trusted TLS/process integration；status NOT_RUN。
- A33-02 DID真实HTTPS取得批准后immutable快照：tests/integration/test_a33_roles.py::test_operator_https_did_approval_and_immutable_distribution；unit + real-PG integration + trusted TLS/process integration；status NOT_RUN。
- A33-03 真实三holder及OS网络隔离：tests/integration/test_a33_roles.py::test_three_holder_processes_os_and_network_denials；unit + real-PG integration + trusted TLS/process integration；status NOT_RUN。
- A33-04 真实browser/code与两级委托：tests/integration/test_a33_scenarios.py::test_browser_root_and_two_delegations_real_https；unit + real-PG integration + trusted TLS/process integration；status NOT_RUN。
- A33-05 四工具完整采购与授权query：tests/integration/test_a33_scenarios.py::test_three_holder_four_tools_query_receipt_anchor_export；unit + real-PG integration + trusted TLS/process integration；status NOT_RUN。
- A33-06 下游独立DB服务认证与固定工具：tests/integration/test_a33_scenarios.py::test_downstream_separate_domain_service_auth_and_effects；unit + real-PG integration + trusted TLS/process integration；status NOT_RUN。
- A33-07 请求精确绑定与严格负例：tests/integration/test_a33_scenarios.py::test_attack_set_exact_binding_no_side_effects；unit + real-PG integration + trusted TLS/process integration；status NOT_RUN。
- A33-08 预算次数与锁后新鲜性竞态：tests/integration/test_a33_scenarios.py::test_root_mid_calls_revocation_final_clock_races；unit + real-PG integration + trusted TLS/process integration；status NOT_RUN。
- A33-09 执行完整故障矩阵与恢复：tests/integration/test_a33_scenarios.py::test_process_crash_late_success_recovery_fault_matrix；unit + real-PG integration + trusted TLS/process integration；status NOT_RUN。
- A33-10 持久回执检查点交付故障：tests/integration/test_a33_scenarios.py::test_receipt_audit_export_faults_and_offline_mutations；unit + real-PG integration + trusted TLS/process integration；status NOT_RUN。
- A33-11 无模型API干净source与wheel：tests/integration/test_a33_clean_deploy.py::test_clean_source_wheel_without_model_api；unit + real-PG integration + trusted TLS/process integration；status NOT_RUN。
- A33-12 轮换升级备份恢复清理：tests/integration/test_a33_clean_deploy.py::test_rotation_upgrade_backup_restore_owner_cleanup；unit + real-PG integration + trusted TLS/process integration；status NOT_RUN。
- A33-13 固定最大材料与公开安全导出：tests/integration/test_a33_clean_deploy.py::test_max_legal_payload_bounded_package_and_expired_public_export；unit + real-PG integration + trusted TLS/process integration；status NOT_RUN。
- A33-14 部署设计技术材料真实演示：tests/test_a33_documents.py::test_release_materials_commands_and_actual_demo_artifacts；document/CLI validation + source/wheel actual demonstration evidence check；status NOT_RUN。

## 数据/部署/交付

干净source非editable与wheel非editable各仓库外cwd/noPYTHONPATH/noimporttests，用锁安装Python3.11，pipcheck/importsitepackages/migration出处实证；TLS开发CA仅本次clientoperator信任，不改系统trust/hosts、不关闭verify；容器固定DNS:443解决restrictedDIDport，loopback随机port若映射须仍verify正确hostname。现TLS_RSA+应用SM2明确非全栈国密。

固定合成catalog/quote/order/recipient，不给模型任何密钥或API，无模型时确定性编排；完整宽授权/256items真实最大body/result/证据包预检≤256MiB并继承acceptedA32更严分项codec，不能借整包上限放宽65536HTTP/JWS，容量冲突在正式审包重核。公开export在全部synthetic token最晚exp过后/撤销，历史签验按真实窗口；独立trust/latestcheckpoint分开交付。UNANCHORED尾部/缺latest限制准确，整包超限明确失败不删record。

轮换/旧row升级保全/备份as-of/恢复/资源清理均实际验证；historicalSQL只读，legacy坏原件保预算隔离。交付本地部署说明、完整设计/威胁说明、technicalreport、实际normal/attack/fault命令结果、独立synthetic包、本轮必须可执行可复现demo脚本与source/wheel实际运行证据；acceptance§4原文“演示脚本/视频”不额外升级成视频硬门。能录制则另交诚实actualrunvideo或terminal.cast，不能用图片/伪动画替代；未录报告未录，不单因缺视频否定脚本原目标。全部绑定最终commit/wheel/locks/publictrust/latestcheckpoint。

host只读观察root提供15logicalCPU/24GiB；Docker15CPU/~7.75GiB aarch64，amd64转换如实；394GiB可用。三PG各512MiB建议+lightroles+50slots（A34），以实际峰值调整quota，不新增Docker16GiB硬门槛。不因硬件改50/10000；本agent未新增硬件测量，非性能预测。

## 不减项的验收与状态

每条新增及继承ID都须source/wheel真实检查、独立命令/退出/JUnit/日志/SHA、DB全祖先四计数/effect/event/outbox/lease/首次材料/journal/checkpoint读回，允许staging区别业务零新增。所有正式安全竞态/故障组10轮、独立连接barrier/event、真实old/newPID、SQLSTATE/future异常全收。全A1单列/A2-P01-P21/B原67及全部A22最终补正/A23/A31/A32实际accepted矩阵、历史原probe或语义等价/有效negativeoracle、锁定Python3.11及依赖/PEP517、迁移/校验/升级保全、source与noneditablewheel来源证明仍必跑，不能仅跑本新增测试。现阶段继承API/hash/function节点有待实际accepted展开，正式审包前缺展开即NOT_FROZEN，不能凭旧PASS补。

运行owner每writer/reviewer独立UUID project/network/PG/namespace/venv/证据目录，无普通DSN回退，不读打印privatepassword/DSN/env私钥；只清自己manifest可核资源，禁止prune/共享down，结束ownleftovers0。现在业务资源0。实施完整selfcheck→native停写→所有tracked/nonignoredhashfreeze→新独立xhighreviewer包审与实施验收分别记录；失败原件保留补正fresh复验。主控独占状态与授权，不由worker自ACCEPTED。

## 本次草稿小补正v2（非实施）

旧tasks/workflow/state.json是A2.1历史机器门，严格只读。未来新A33/A34 state只在新正式run目录绑定精确路径后写，当前placeholder不能PACKAGE_READY。Docker采用已有固定Python3.11 base与只读wheel装配，无需推测新增Dockerfile；正式包需冻结image digest/锁安装/非editablewheel真实来源命令。如确需custombuild，再精确扩scope/build文件审包。78规划ID是附加索引，不是最终项目全矩阵，须从新正式candidate实际accepted allA1/A2/B/A22/A23/A31/A32逐项完整展开、源码轮包全部真正运行。
