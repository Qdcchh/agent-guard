# A2 当前实现与验收索引

更新：2026-10-06。**完整当前 A2 ACCEPTED；当前版本协作发布到PR #7，暂不合并。** 项目整体PARTIAL，A3未实施；由同学按[完整交接](../docs/A3-HANDOFF.md)继续完成全部A3。历史复核的未发布范围保留在原接受记录，当前发布授权另见[真人指令](workflow/runs/A2.3-receipts-20261004/user-publication-20261006.md)。

[正式接受](workflow/runs/A2.3-receipts-20261004/acceptance.md) · [完整独立review-r2](workflow/runs/A2.3-receipts-20261004/review-r2.md) · [state](workflow/runs/A2.3-receipts-20261004/state.json) · [HANDOFF](../HANDOFF.md)。新独立Sol/xhigh reviewer实际FINAL STOP，主控Sol/high读回原件后接受，后台有效metadata UNKNOWN。119项、112运行义务、269原must_assert、41节点/88原子逐项闭合。

| 已验证范围 | 本轮独立依据 |
| --- | --- |
| 完整普通与PG集成 | source/fresh非editablewheel各1185P＋2810P，四套真实exit0/0F/E/S |
| 祖先共享预算、撤销、新鲜性、UNKNOWN不释放、幂等与恢复 | 原完整矩阵、有效10轮竞争及60 oracle负控；独立GW/DS事务域，全31ag＋3DS状态比较 |
| 内部持续发布、当前授权query与SDK | 真实SM2/SM3、17claims、原可信材料及算术签前拒绝、稳定id/iat、core及实际CLI SIGKILL/不同PID恢复 |
| AS/GW真实HTTPS四工具链 | 真实CA/SAN、login/consent/code/PKCE/IDToken、两次exchange、DS终局、发布/当前query/独立SDK与攻击负例 |
| 前段/历史/时限/容量/质量/README/迁移 | 各500精确时限、A1原及现行、A2原482、B原失败及精确等价、14SQL/非零数据/锁/轮包来源/原门全部核验 |
| 增强组 | source原487P；wheel原484P/3F/exit1保留，原407未受影响PASS＋原模块新完整80逐case闭合，未称原487单次全绿 |

P2算术缺陷、source整套覆盖缺口、历史注释及容量/格式/上界标签均依据本轮完整独立证据闭合，见[issues](workflow/issues.md)。原r1 NOT_ACCEPTED、所有操作/封存失败、未知原因、两次工具隐私事件保留。500组本身是实际查询与错误映射探针而非500次HTTP传输；边界故障fixture和包含域上界不冒称合法最大值。容量独立较紧canonical上界51035、兼容rawJWS上界64695，不改64KiB组件/16KiB JWS/65536公开/1MiB外壳门。

受审冻结369首尾与Git无漂移；STOP后只同步当前文档/状态，77Python＋14SQL及测试/依赖/CI不变，实测wheel元数据仍对应冻结README。5172证据对/44XML与51结束制品哈希核过；精确自有container/network/匿名volume及native运行进程0。原始证据留本地Git忽略目录，正式报告不能重建原件。

## Git与历史

作者原本机提交与dirty成果全部保留。协作版本从原PRtip选择已接受产品与可移植文档的新提交，未直接发布混合本机绑定的本地提交；[公共产品指纹](A2-public-product-manifest.json)绑定代码/测试/锁/迁移/CI字节。远端分支 `codex/a2.2-integration`、[PR #7](https://github.com/Qdcchh/agent-guard/pull/7)；当前CI/审核以实际候选为准，不把旧CI或本地独立接受当合并条件。本次禁止合并，PR #6例外不继承。

B补正67/60已接受并经PR6合并；[接受原件](workflow/runs/local-remediation-20261004/acceptance.md)保留。A2.2为[95/88独立接受](workflow/runs/A2.2-integration-20261004/acceptance.md)，原两P2复验及CTX回归保留。A2.1历史[A2.1接受](workflow/runs/A2.1-core/acceptance.md)、[本地质量复核](workflow/runs/local-quality-20261004/review.md)、[A2.3原r1否决](workflow/runs/A2.3-receipts-20261004/review-r1.md)、[各实施及补正自查](workflow/runs/A2.3-receipts-20261004/implementation-remediation-r2.md)与停止/恢复记录均保留其实际时点，不追改测试数、模型、失败或授权。旧云端缺失原件不能由新接受补造。

## 剩余目标

回执仍UNANCHORED，单operation一致性不等于独立审计完整性；旧无receipt_keys配置保持PENDING兼容。A3检查点/审计链、导出/离线校验、部署/三代理编排、至少50客户端/10000调用与公平对照实验及参赛材料均未实施，见[A3四段规划](A3-plan.md)。最新真人已要求协作发布/交接全部A3，发布者不实施A3；同学逐段正式包审、整合与独立接受，暂不合并main。
