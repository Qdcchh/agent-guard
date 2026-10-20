# COSM2 A1/A2 提前交付 v1

真人来源：本聊天 2026-10-17：“我是A……worker改成6.1sol low，reviewer改成6.1 high……A1A2两部分，今晚先给做了，开始吧”。授权 GRANTED，仅本轮 A1/A2，不含 A3 或 B 任务。附件作为需求参考，不将附件中对其他角色的任务当作授权。

分支 codex/cosm2-2p-A，继承工作区改动；原状 diff/status 在 artifacts/cosm2-a1-a2-20261017/controller/baseline*。不 commit/push。当前 B1 公开向量缺失，不虚构 B 产物。

## 需求与验收矩阵

- A1-01 新增 tools/cosm2_vector_check.py，默认读 tests/cosm2-public-vector.json，兼容三个既定字段；严格解析公开材料，不泄露秘密，不引入运行依赖。
- A1-02 SPKI 转 PEM、64 字节 r||s 转 DER、临时目录及清理；执行 OpenSSL 3 pkeyutl SM3、distid 1234567812345678，正例须退出0且有 Signature Verified Successfully，消息翻转一个字节后须验签拒绝；工具/向量缺失或 OpenSSL 运行错误不得伪装负例成功，最终退出非零。
- A1-03 macOS Homebrew OpenSSL 3 或显式路径；可用给定参考实现生成临时公开向量验证工具，报告清楚“参考实现向量”，B1 向量后续到达再跑，不冒称 B 已通过。参考实现不进生产路径，不更改原件。
- A2-01 只改 web/teacher-demo/index.html、app.js、style.css，保留当前用户改动。新增 cosign 导航位于 threshold 前，threshold 改名 FROST 对照；SCENES 场景包含规划指定文案、五泳道、三轮与独立谓词检查、正常一单示意及授权域 AUTHZ_REVOKED 负例，后续网关/下游未发生。
- A2-02 五类 cosign 事件、中文旁白、exec-domain/authz-domain 各六项说明卡、三行 delta、半诚实/n=2/同主机/推广未实现 honest、总览扩展能力文案。
- A2-03 无真实结果维持 illustrative，来源标签醒目“示意推演”，live/replay 不混用；不接假真实运行按钮/结果。保持 CSP、无内联脚本/样式/CDN，安全展示不含份额/随机数/令牌。
- A2-04 node tests/test_teacher_demo_frontend_logic.cjs 通过；1366×768 浏览器检查无重叠，正常与负例和模块点击可用。审查在 artifacts 自建必要探针，不删旧断言。
- V-01 相关脚本/页面检查、ruff check 与 format（全仓基线问题如实分类），git diff --check；实际命令、原样输出和局限保存报告。

## 执行与审查

独立 fresh PACKAGE_REVIEW 无阻断后分配两名 low worker：A1 独占 tools/cosm2_vector_check.py 及其自身 artifacts；A2 独占上述前端三文件及其自身 artifacts。共享接口只读，无数据库/业务网络资源，不修改 B/旧迁移/签名格式。主控维护正式文档与测试证据索引；全部 STOP 后冻结候选与相关调用方，fresh high reviewer 独立全矩阵验收，缺陷最小补正后 fresh 复验。审查写入仅 artifacts/cosm2-a1-a2-20261017/review-*；主控保存正式报告。B1 未到只限制对 B 的密码学结论，不阻止交付可复现工具/参考验证/示意页面。
