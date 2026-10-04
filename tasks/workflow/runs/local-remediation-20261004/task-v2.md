# B 整合补正文档收尾任务包 v2

状态：PENDING_PACKAGE_REVIEW。v1 worker 已 native completed / READY_FOR_REVIEW 并停写，主控已核17路径指纹、无越界及自有测试资源清理；完整自查见 [implementation-r1](implementation-r1.md)，并非正式验收。本包冻结后由新的 reviewer 做 PACKAGE_REVIEW，PACKAGE_READY 后才能实施此文档补充。

## 授权和继承

用户本会话已明确要求修复、按工作流复核、删除不影响项目的过时或错误文档、更新应改文档并最终条件合并 main；随后批准本轮运行适配。授权原文与来源见 [authorization.json](authorization.json)，适配规则见 [runtime-addendum-proposal.md](runtime-addendum-proposal.md)。无需重复请求已授予的文档维护权限。

完整范围、安全不变量、五项修补、资源隔离、历史原件/等价回归和合并门仍按 [task-v1](task-v1.md)。[requirements-v1.json](requirements-v1.json) 的67项要求、60项独立运行义务逐字不变。本补充不增加功能、改变协议或降低任何测试标准；v1实现和测试交付作为待正式验收候选，不因自查全绿提前ACCEPTED。

本包仅为主控已发现的五份现行文档状态/边界同步补充精确路径，并使当前三份索引有稳定的阶段报告入口。六处实现、七处正式测试、SQL、依赖、原契约/历史报告/旧state及旧门均只读。本轮fresh最终验收仍须对完整候选（含文档）独立运行全部要求。

## 单一worker精确写路径

1. `AGENT.md`
2. `docs/acceptance.md`
3. `docs/security-model.md`
4. `docs/oauth-oidc-sm2-mvp.md`
5. `docs/crypto-profile-v1.md`
6. `README.md`
7. `HANDOFF.md`
8. `tasks/A2-report.md`
9. `tasks/workflow/runs/local-remediation-20261004/implementation-docs-r1.md`（新）

同一实施worker串行续做，创建时显式请求过 `gpt-6.1-sol / medium`；有效后台元数据仍UNKNOWN。仅另写自有 `artifacts/workflow/local-remediation-20261004/worker-docs-r1/` 证据。主控拥有本包/本轮state/问题台账/调度和正式审查报告，不与worker交叉写。新增必需路径或实际功能问题先回报主控重新定范围。

## 必须同步且不得扩张的内容

- `AGENT.md` 只纠正“当前项目处于骨架阶段”的失实项目状态，保留全部安全、授权、Git、实跑和如实报告规则，不能借改代理规范放宽约束。
- 四份设计文档把“当前”状态和环境结果转向本轮真实实施/验收索引。历史Python/PG/CI结果必须明确绑定历史，删除“本轮CI未授权”等与新授权冲突的现行措辞；未触发远程CI仍如实写未运行，不提前报通过。
- 接口文档明确订单items为1—256项，重复SKU等原拒绝规则不变；安全模型明确结果成功变体须匹配工具、异常保持UNKNOWN和原预算；密码/回执文档明确祖先grant ID全路径唯一。这是已批准v1行为同步，不改wire、签名、迁移或错误策略。
- 验收文档保留M1—M13及全部SEC/CON/REC/AUD/E2E/ENG原要求，逐项关联本段67项/具体测试证据入口，并准确指出A2.2公开网关/最终动态查询、A2.3持续签发发布、A3锚定/导出/完整E2E/规模实验的剩余范围。尚待fresh复验与后段未实现分开，不用局部通过覆盖整个目标。
- 三份当前索引应区分“实施交付时FIXED_PENDING_REVIEW”与后续主控正式验收结论，使用稳定的本轮state/报告入口；整体PARTIAL、后段范围与outbox PENDING继续保留。不要让当前状态永远停留在已过时诊断轮，也不能提前写ACCEPTED或已合并。
- 保留固定依赖及已知维护不确定性的准确限制。README现有setuptools上游sdist风险有官方依据，不能无证据删风险或称已修复。本包不升级依赖、不构建/发布sdist、不增加外部服务。
- 只删除被新现行表述替代的过时段落；不删除历史正式验收、失败证据、原始任务或有用规范文件。此前删除的setup历史文档及理由仍可追溯。

## 验证、交付和冻结

实施前核对本包、fresh包审、v1交付停写回执和当前文档基线。原worker代码/测试已停写，文档实施不再改其字节。无需为纯文档重复业务全套；必须实际运行本地Markdown链接与fenced JSON检查、`git diff --check`，并人工逐项对照设计表述与真实v1实现/报告、已授权但未完成的工作和后段边界。

依原implementation模板交付 `implementation-docs-r1.md`，列准确增改、测试命令/退出码/日志、首尾只读源/测试/SQL/依赖哈希。只标READY_FOR_REVIEW，明确进程/资源归属和停止写入。主控核范围后冻结完整candidate、两个任务包与全部契约/需求；另开fresh `gpt-6-astra / high` reviewer执行完整IMPLEMENTATION_ACCEPTANCE，不能用本包PACKAGE_READY或文档检查代替67/60正式实跑。

通过后依已授权的正常Git流程交付，不自批或管理员绕过，不提前进入下一阶段。绝对无缺陷或生产安全不是可验证结论。
