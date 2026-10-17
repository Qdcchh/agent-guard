# COSM2 A3–A7 独立工作候选 · READY_FOR_REVIEW / PARTIAL

真人授权、完整矩阵和包审见package-v1.md、package-review-r1.md；B明确尚未开始，未接管B。两名实施worker及一名图表worker已STOP，主控截图/录屏/打包完成。候选等待fresh gpt-6.1-sol/high完整独立审查。不得将本报告当作全A完成或正式接受。

当段交付/命令/数据/未测条件统一见[交接说明](../../../../docs/cosm2-a-handoff-20261017.md)。原样worker报告分别在artifacts/cosm2-a3-a7-20261017/measure/implementation.md、ui/implementation.md、figures/implementation.md；主控原样命令及输出在controller目录。

本轮实现：测试参考fixture/三项真实B交叉测试，bench/plot与24项纯工具测试，B7只读保存结果适配及严格输入测试（合并相关49项），三图生成器与8项坏来源/输入测试，截图/185.36秒回放导览与C包工具。主控相关总计81 pytest通过、Node通过、11文件局部ruff与diff通过；交叉3项因B缺失FAIL。正式SM2签/验/FROST各100+10真实成功，三轮/DB/e2e未测；首次FROST失败run01保留。

C包复核26文件SHA一致，含4PDF、原数据/来源、9截图、两格式回放视频与缺项表。原始资料/前段验收/继承dirty保护，不改001–009/GM/V1–V3协议，不commit/push。所有图主控已逐页检查；录屏抽帧可见真实历史run_id/来源，日期在详情页可见，不充共签现场。

最终审查必须对A3-01/A4-01~02/A5-01~02/A6-01~02/A7-01~02/V-01逐项区分独立实现和B依赖；可评独立工具/设计资产质量，不可接受全A实跑。主控本轮HTTP服务独占127.0.0.1:50087，审查可只读使用；由主控最后关闭。此前worker自有容器均已退出，无数据库操作。
