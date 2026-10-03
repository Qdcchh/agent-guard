# 文档补正 LOCAL-DOC-CLEAN-CHECKOUT

授权与文件范围继续按已审task-v2，67/60不变，不修改产品代码/测试。主控读回发现docs/acceptance.md新增的两个Markdown链接指向artifacts/workflow下的Git忽略文件。原本地97链接存在检查不能证明干净克隆可用；tests/test_docs.py在CI只收到Git交付文件时会断链。这是文档工程阻断，尚未进入最终验收。

请把现行文档的验收入口改为实际随Git交付的本轮实施报告/控制状态，原始本地证据目录如需指明以明确标注本地、Git忽略的文本路径引用，不将它们作为干净克隆必须存在的Markdown链接。核对README/AGENT/AGENTS/docs全部链接，全部v2九路径既有本地检查继续。

在自有证据区构建只包含git ls-files --cached --others --exclude-standard所列现存文件的临时副本（不复制artifacts/.git/venv/缓存），精确保持实际文件内容；在此副本运行既有tests/test_docs.py并检查完整tracked文档入口，不靠创建假的artifacts文件通过。保留首次失败和修后日志，源码/正式测试/SQL/依赖/v1证据仍只读。

之前交付原报告及哈希已由主控另存controller/implementation-docs-r1-original.md，原worker-docs-r1证据不可覆盖，新增证据放其correction-r1子目录。更新允许的implementation-docs-r1.md说明此失败/补正与实际结果，不暗示首轮已验证干净克隆；新stop-binding和SHA另保存。完成后READY_FOR_REVIEW并停写，主控再冻结完整候选给fresh验收。
