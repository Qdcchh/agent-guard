# COSM2 A3–A7 连续交付 v1

本聊天真人2026-10-17授权：“直接继续A的内容吧，一直到全部完成为止”，并确认“B没有开始”。沿用用户指定 worker gpt-6.1-sol/low，fresh reviewer gpt-6.1-sol/high，effective metadata UNKNOWN。分支codex/cosm2-2p-A，保护所有继承dirty/untracked，baseline在本轮controller目录，不Git发布、不恢复旧长期实验、不接管B。

本轮原始要求为《复赛冲刺材料-20261018/01-双域协同SM2实施规划-A与B分工.md》第0节与A3–A7、B接口表。B核心、公开向量、真实共签demo结果均缺失；所有“全部完成”结论必须受此真实依赖约束，不通过skip/mock/参考替代伪造完成。

## 完整当段需求矩阵

- A3-01 复制参考实现到tests/fixtures/cosm2_reference.py，明确仅测试用、非常数时间；数学不改，允许ruff纯格式。新增tests/unit/test_cosm2_crosscheck.py：固定d1/d2公钥逐坐标、双向真实签名/铜锁与参考验签、20随机消息compute_e一致。B缺失时明确失败/阻塞，不默默跳过或偷偷切参考核心；按规划接口写小型明确adapter并记录需B最终确认。
- A4-01 新增experiments/cosm2_bench/bench.py、plot.py。正式环境固定threshold runner，记录CPU/Python/tongsuopy/镜像标识，预热10、100次，不删异常值。测三轮与总时间、含DB谓词round2（缺依赖明确未测）、单SM2签名/验签、真实Rust FROST sign-quorum且标进程启动开销、真实B7 e2e（样本数如实）。CSV每样本、summary每项n/median/p95/min/max，未测n0/null/status/reason，不造0延迟；缺依赖总体PARTIAL且完整验收模式非零。
- A4-02 plot输出矢量fig-latency.pdf、中位/p95、单位/样本量/环境与未测说明，不混机器数据、不把参考共签当B性能；已测单SM2/FROST可先出部分测量图并醒目标明缺共签。统计/输入边界/坏数据有必要测试。
- A5-01 前端FIXED_DEMOS新增cosign/cosm2-run及B7六例译名，真实结果解析严格、来源与run_id/time，timing标“单次运行，非统计结果”。有真实结果才显示本次现场运行，无结果继续示意，不让summary结果冒充逐帧真实事件。
- A5-02 B7尚未实现，控制接口缺失时不添加后端假的运行入口；UI可显示未就绪禁用。允许只读接入已存在的真实B7 result.json契约到server清洗/状态，保留完整验证/去敏；不能读取份额或任意磁盘路径。前端、读取端和真实缺失状态测试，集成未实跑保持待B7。
- A6-01 生成可复现矢量fig-system.pdf、fig-protocol.pdf到论文figures。中文统一字体/配色，双域边界、智能体无份额、P2独立谓词、最终标准验签。明确设计示意/本阶段未集成，不冒称已运行；报告lab制作，PDF render逐页视觉检查。
- A6-02 fig-negative.pdf仅来自真实run证据：七攻击×AS/授权域/网关验签/接受事务填拒绝码；可用当前真实FROST/已有安全场景但必须按方案/来源区分，不能迁移为COSM2实证。B缺失的COSM2单域签名/共签撤销列未测，不虚填。仅当有合法真实数据时导出部分矩阵并显著标未覆盖，无法则保留生成器与待补清单，不制作伪结果。
- A7-01 总览、场景1/3/6、共签示意、真实记录页原图无标注；共签真实结果截图依赖B7，缺失明确待补。Playwright截图/3分钟演示录屏使用真实页面和来源标签，能看到run_id/日期；B7未实现时不录假共签现场。可录现有真实记录导览，不能作为共签现场视频完成项。
- A7-02 交付C目录及表：图/截图/summary/raw与命令或run_id映射、状态、SHA、日期/环境、局限、缺失条件和一键续跑命令；交付本地目录不擅发消息给C。B依赖项未闭合不可标全A完成。
- V-01 合适的纯逻辑、strict输入、误标来源、坏result、测量/统计测试；相关Node/pytest与ruff/diff，保留所有旧断言。新增运行依赖不随意修改项目锁；优先已锁runner/内置图表库。每段自查后STOP，fresh高模型独立完整审查与代码/证据SHA冻结，报告已测和阻塞分别列明。

## 所有权与执行

包审通过后可并行：worker-measure独占A3 tests/fixtures/cosm2_reference.py、tests/unit/test_cosm2_crosscheck.py、experiments/cosm2_bench/**及其必要新增专用测试；worker-ui独占web/teacher-demo三文件、tools/teacher_demo_server.py、现有相关tests增补；worker-figures独占新增tools/cosm2_paper_figures.py与论文figures新图/来源文件。每人仅自己artifacts子目录。现有README/旧图/历史报告不覆盖。

槽位有限可按阶段调度；主控唯一整合、管理本轮独占HTTP服务及A7截图/录屏/交付索引。共享result契约严格沿用B7，不修改B生产协议；writer STOP后再冻结审查。PDF技能要求authoring前标记operation started，reportlab矢量生成、Poppler render视觉核查。录屏/图表可能用已带Playwright/matplotlib/ffmpeg工具，工具不可用先检查内置依赖，不为此扩大产品依赖。

## 放行边界

包审仅评可实施性，不能因尚未实施测试NOT_RUN否决。最终完整A3–A7 ACCEPTED必须B依赖到位且全矩阵真实运行；当前可分别接受“工具/设计资产实现”与明确阻塞清单，不将PARTIAL写成全部完成。若无B交付，完成所有独立工作后向用户给出准确剩余依赖，不自行编写B替代或无进展等待。
