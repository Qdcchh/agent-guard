> 历史工具说明：本文对应旧 A2.1 state/schema，不是当前 Codex 运行适配器。当前阶段、模型与授权先读 [现行约定](current-policy.md) 和 [context](context.md)；不得直接复制旧运行字段放行新阶段。

# 状态与验收索引填写规则

本文件供主控维护 `state.json`；实施者与 reviewer 不修改控制状态。JSON仅是索引，实际授权、行为、独立性、日志与语义仍须直接核实。所有 artifact/contract/report 路径相对仓库根，禁止 `../`、绝对路径和越界符号链接。CLI相对 `--state` 同样以 `--root` 解析。

## 当前初始状态

`current_stage=A2.1-core`，`status=AWAITING_USER_APPROVAL`，`authorization.status=PENDING`，`source_message=null`，`review=null`。配置请求不授权实施。初始 snapshot 是配置完成时的实际文件清单，不能当未来代码验收。

收到明确批准后，核对原始 OpenCode 真人消息和范围，保存 `source_message={role:"user",session_id,message_id,text}`。填写完整文件所有权、当前stage、禁止动作，确认授权与正式 Markdown 包一致，才设 `authorization.status=GRANTED`、`status=IN_PROGRESS`。首次经 `PACKAGE_REVIEW` 无阻断后再发实施任务。授权检查须退出0且 `can_start=true`；不能凭改JSON伪造批准。

## 实施验收记录

实施者停写后，主控生成当前 snapshot，逐个 SHA256 冻结 `contract_files`，至少包含原任务/安全/设计/验收要求、本阶段正式文档、当前任务包与适用契约/模板。不能漏掉 runs 中的已批准任务包，仅因该目录排除代码快照而跳过其哈希。`issues.md`单独传给reviewer并核对内容，不以清空台账绕过未闭合问题。

每轮完整审查报告保存且读回后，`review` 的格式为：

```json
{
  "review_kind": "IMPLEMENTATION_ACCEPTANCE",
  "independent_session_id": "本轮全新的真实reviewer session ID",
  "model": "openai/gpt-6.1-sol",
  "reasoning_effort": "xhigh",
  "report_path": "tasks/workflow/runs/A2.1-core/review-rN.md",
  "report_sha256": "该完整报告实际SHA256",
  "snapshot_fingerprint": "本轮reviewer独立核对的snapshot指纹",
  "contract_files_sha256": "本轮reviewer独立核对的contract摘要",
  "requirements": [
    {
      "id": "逐个正式expected_requirement_id",
      "status": "PASS",
      "evidence": [
        {
          "path": "artifacts/workflow/真实本轮目录/证据文件",
          "sha256": "该文件实际SHA256",
          "kind": "independent_run",
          "exit_code": 0
        }
      ],
      "reason": "具体断言、结果和覆盖范围"
    }
  ],
  "open_blockers": []
}
```

占位必须替换成实际值，每个必需ID独立一行。证据类型仅 `independent_run`、`inspection`、`historical_log`；静态/历史证据可用 `exit_code=null`。历史日志不能独自支撑PASS；运行类必需ID必须有本轮独立运行且退出0的原始证据。必需项不能用NOT_APPLICABLE/NOT_RUN/BLOCKED放行。未纳入当段的后续要求保留在Markdown中，不伪报已完成。

契约摘要：仅取每项 `path`/`sha256`，按path排序，使用 `json.dumps(items,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')` 后SHA256；脚本公开 `contract_files_sha256(items)` 可直接使用。Reviewer自己的两个指纹必须保留，不能只刷新state后沿用旧审查。

## 接受、补正与阶段切换

- 完整实施审查通过后，在 `READY_FOR_REVIEW` 运行 `--require-accepted`。仅退出0且 `can_accept=true`，并经主控核原始证据、完整矩阵、问题关闭记录之后才写 `ACCEPTED`。写后可再次核验；`accepted=true`只是结构核验结果。
- 最终review之后只更新排除在快照外的state、issues和runs报告。context、规范、正式任务与业务文档在本轮冻结范围内，不能在写总结时顺手修改并继续沿用review；需要修改则重新冻结和复验。阶段停等期间以state/acceptance报告记录最新结果，下一段获批准并归档后再更新context。
- 有缺陷则 `CHANGES_REQUESTED`，按补正Markdown交回MiMo；受外部依赖或必要条件阻塞则 `BLOCKED`。修复后新快照、新reviewer、新完整报告，不覆盖失败轮。BLOCKED解决后需主控核对同阶段授权，再恢复IN_PROGRESS，不能跳过门检查。
- 每阶段ACCEPTED后维持当前stage并停止，展示结果和下一段提案。收到新真人批准才归档本段 state/review/指纹到版本化 runs 记录，更新context，并设置下一stage和其新授权、完整需求ID及运行ID。前段验收资料与未关闭建议不能丢失。
- 下一段A2.2/A2.3的提案须展开为正式任务及矩阵后审包，再实施；不能复用A2.1清单或review报告作为该段通过。始终保留前段回归与原A2完整验收义务。
