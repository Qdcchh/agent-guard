# PACKAGE_REVIEW · cosm2-a1-a2-20261017 · r1

结论：**PACKAGE_READY**。无阻断项；仅批准包质量，不构成实施验收。项目整体仍为 **PARTIAL**。

Reviewer 全新独立会话 `/root/package_review`，请求 `gpt-6.1-sol / high`，effective metadata UNKNOWN。日期2026-10-17 Asia/Shanghai。

已只读核查 AGENTS/AGENT/current-policy/review-contract/package-v1、原始规划第0节及A1/A2、前端场景/事件校验/模块/来源切换、逻辑测试和两份参考脚本。授权依据本聊天真人消息和current-policy顶部覆盖，不套用旧A3/旧模型。

分支 codex/cosm2-2p-A，HEAD 6ab288c928f8b63778856d426e3bbbec9511144c。继承dirty/untracked受保护，baseline-status/patch存在。

| 需求 | 静态核查判断（非行为PASS） |
|---|---|
| A1-01 | 三字段、默认B1路径、严格公开输入解析、零新增运行依赖覆盖 |
| A1-02 | PEM/DER、临时清理、固定SM2 ID、SM3/OpenSSL正负例及拒签/工具错误区分完整 |
| A1-03 | Homebrew/显式路径与参考向量可行；参考只作测试，不改原件或进入生产 |
| A2-01 | 三文件保护、导航/FROST更名、文案、五泳道、授权域拒绝及未发生完整；ACTORS/VIEWS/绘图须同步 |
| A2-02 | 五事件、旁白、两卡、三行对比、局限与总览覆盖 |
| A2-03 | illustrative与来源、无假真实运行、CSP和敏感材料保护完整 |
| A2-04 | Node回归、1366×768视觉/正常负例模块交互与探针覆盖，不删旧断言 |
| V-01 | 检查/diff/原样输出与局限完整；全仓基线问题应单列 |

第0节适用边界均保护：不改001–009、既有签名语义/格式或B网关路径，不伪造成功，不输出秘密、不发布。份额和随机数生命周期属B，本轮不冒称实现。

独立确认B1 tests/cosm2-public-vector.json不存在。可先交付工具、参考向量真验证与示意前端，不能写B1/G1通过。两名worker独占文件可行，无需数据库/容器。

独立两次SHA一致：package 71f7015033298e69a1e99bec9051774fa0b9b01e98746c329e0a306b0c77d7b0；current-policy 95b63f23cd2faf80f006022603047aac314cbaaf0dec850540f0beccbbdab7e2；review-contract 1ccdba2d10c3b12abe38c71e8d48eeef8aa40f7d2dad97594c5f4633861aab19；规划7136a4a5cf187c784f977b5033dc9c7533a6baf4ab2bf21fb557e7f53ce67f0e；index e37d16e617730a83b9856db6f22a5826d7812effeadd87220f43065b30c3f1d6；app 04fd1fd403859ff108507b89dc2af7df97ca38dd6f81dfc51dad24bd83dafc98；style d46779e6f8870ded2643c8564c537762b7816f2be4afe4d35c17bf7aa58e1055；逻辑测试8057ef611e4c746522bd38aeeb1e99dda8eabde679c99fb7f3561d00ef95b17f。

含上述文件、AGENT和两份参考脚本的11文件清单排序规范JSON SHA 4e7a6681e63372171cb2eca9ec406aa70a958c363123b04a9f816cd8185f54c7。

未运行实施测试、创建资源、修改文件或调用子agent，未commit/push。主控可按真人授权派两个worker，全部STOP后冻结候选并fresh独立验收；B1到达仍须真复验。
