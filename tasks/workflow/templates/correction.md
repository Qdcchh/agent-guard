# <stage> 补正包 r<N>

- 同一阶段用户授权引用：
- 对应完整review Markdown和独立review session：
- 被review的snapshot/contract摘要：
- 本轮 worker 的原生 task/thread 身份（缺失字段如实记录，不混用旧平台身份）：

## 逐项补正

| Issue ID / requirement ID | 严重性、位置和触发 | 实际影响/证据 | 必须修正行为 | 回归探针及绕过变体 | 完成证据 |
| --- | --- | --- | --- | --- | --- |
| <每条必填，不能仅写已修> | | | | | |

所有未关闭阻断问题必须处理；无法处理写BLOCKED和依据。不能降低需求、改验收矩阵或删测试。修复影响其他不变量时补相关回归。

## 交付

读回实际文件，保存代码变更和真实自查结果、剩余问题，标READY_FOR_REVIEW并停写。主控冻结新版本，新reviewer复验原问题、变体及最终整段回归；实施者不能自行关闭issue或ACCEPTED。
