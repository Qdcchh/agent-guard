# A3.2 S0 shared 实施任务（正式派发）

已由 fresh r2 PACKAGE_REVIEW 判 PACKAGE_READY，主控亲核524项候选与六Git controls及reviewer原件/STOP；本任务生效。包审报告 package-review-r2.md，root readback artifacts/workflow/A3.2-evidence-20261011/controller/package-review-r2-root-readback.json。最新真人允许连续至A3.2实际接受/清理后停；任一有效额度窗口剩余≤10%安全暂停、保存原生证据/清理自有资源。worker Sol/low，有效metadata UNKNOWN。不Git或A3.3/A3.4。

阅读AGENT.md/current-policy/实施与review原契约、本段authorization/requirements-v1/完整原A3计划合同、package-v1及package-v2准确覆盖、runtime/ownership/node-bindings-v2、A31正式acceptance及相关实际代码/调用/测试，不将历史拟函数和包审当实跑。保全当前HEAD2a8cc7da4867ad1876350855c0ed5569c5ce6472、handoff/a23-local-20261005、空index及dirty/untracked；不能误用父Git、reset/clean。

仅9个owner a32-shared路径：src/agent_guard/evidence/{receipt,receipt_semantics,task_bundle}.py；src/agent_guard/gateway/{__main__,config,evidence_auth}.py；tests/fixtures/a32_common.py；tests/unit/{test_receipt_components,test_task_bundle_codec}.py。不改其他代码/SQL/locks/state/正式报告/peer文件。自己的ignored artifacts/workflow/A3.2-evidence-20261011/s0-shared-sol-low-r1/ 可保存运行适配、精确原始证据、报告、manifest和STOP；报告不含凭据/完整DSN/JWS/私钥。root行政state与调度另行管理。

最小提取同一 ReceiptComponents/verify_receipt_components（准确字段签名见包），保原ReceiptTrust/VerifiedReceipt/ReceiptVerificationError公共类型与错误/所有旧调用签名及v1字段/准确outer1MiB/逐组件64KiB/JWS16KiB/UNANCHORED。不复制SM2或放宽strictcodec；复用原真实密码/claims/narrowing/proof/history共同窗口/intent/fullpath-delta语义，quote/context/source验证按task必需而原v1缺字段兼容。不从头重写已接受功能。

实现 task_bundle 有界HEADER/OBJECT_CHUNK/FOOTER、24576 raw分块、LF含65536边界、稳定身份typedrefs、object/wire SM3 fold、完整count/EOF、原noncanonical request exact raw保留；default codec限制不变，不整包JSON或假ID拆超限。冻结 iter_frames/encode_object_chunks/ReceiptComponents 公共输入输出及错误，S1只消费S0冻结公共接口。

实现v2 load_checkpoint_history和深不可变readonly descriptor/可信localinput config；真实checkpoint.verify_checkpoint/CheckpointTrust/scope/previous原ASCII/role-range一致核，有界逐行公有NDJSON和原件hash/身份前后核。LATEST/MINIMUM末原JWS与四字段pin一致；UNKNOWN材料一致且不提升latest，具体规则按v2。不要提前实现/导入S1 export/task_verify或接任何网络/生产route。独立预登记export凭据CSPRNG/constant-time/可信tenant/task，保持旧配置无export时原两路由可用。publicfixture必须为S1提供可独立使用的真实签名公有材料、原件/typedref/报告预期与正负控，不能依赖peer半成品。

自查两mode(source与新非editablewheel/Py3.11)全部当前S0新节点/拒绝/边界/原组件签名语义以及受影响v1旧回归。直接实际调用v1路径：tests/test_receipt.py、test_receipt_paths.py、test_interop_vectors.py、tests/unit/test_receipt_publication.py；按代码影响核 tests/integration/{test_gateway_receipt_query,test_key_rotation,test_verified_execution,test_receipt_publication}.py 和tools/a2_receipt_demo，不用一个wrapperPASS代完整受影响行为。S2最终完整A2/A31+所有继承20组选定矩阵自查/新独立接受仍必需，但S0不无理由重跑真正未影响的长组。

实际资源只能当前owner/phase/mode计划的独占namespace/project；先准确记录image/fullID/label/service/mount/private/新anonvol/DB角色/原生PID UID-start-argv/backendID/candidateSHA、cap/OOM，清除普通DSN，不能访问foreign。有限同类运行适配连续获人授权，不降低验收/TTL/预算/撤销/真kill/signonce/十轮；网络失败先setproxy。允许沿A31成熟脚本机制新owner新代码快照/source+wheel实际成员校验，不能继承旧PASS、旧源码/旧owner资源。新SDK模块实际清单随新增重核，不机械固定92上限；SQL16/旧14/依赖锁不变。先实际collect再记录精确选择/all actual parameter IDs；所有native/raw/XML/断言/安装provenance SHA，失败证据不覆盖/删/skip。

完成完整相应自查/ruff check+format，写精简实现报告、准确接口冻结提议、逐节点/原子证据索引和完整原始manifest；所有自有资源精确清理并实际核0，自有host/container进程STOP。停止全部写入交主控，不自PACKAGE_READY/ACCEPTED、不自行启动S1/S2或改正式state。主控全文/原件/实际所有权和无漂移核后冻结S0接口，才启动两个独立S1 writer。
