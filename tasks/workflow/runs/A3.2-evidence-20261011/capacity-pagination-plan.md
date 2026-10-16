# A3.2 容量实测与正式分页接续规划

状态：FORMAL_CAPACITY_FOLLOWUP_PLAN，未实施、未授予新协议或下一阶段开工权限。当前 AG-TASK-EVIDENCE-2 及原组件、总量、预算与验收门保持原值。本文件落实原 A32-08.01 的“actualcounts/lengths preflight ifover formalpagination gap”，不把容量拒绝称为单包成功，也不代替完整独立验收。

## 真实依据与现行限制

原生 source 在原 token 300s / proof 60s / 真实时钟下接受 10000 个合法四工具操作，278.226356544008s、失败0；随后不可变执行/发布全部完成，累计680.9669491029927s、失败0。完整真实 RR 行原件826390481字节，SHA256 `9eafeecc22541229d5c3ccc9cc0d033f5a4d89497e51e45282fe8255501a4358`。这是业务生成证据，不是10000单包成功、独立AUDIT观察或A3.4性能结果。

基于该不可变原件的隔离网络断开编码预检，生产 encode_append_batch 按64候选/65536响应最大合法前缀得到668批，完整 previous 链采用本地真实SM2；含10000操作、30009 journal、203285对象/块、291623992原始材料字节及439169636 OBJECT_CHUNK wire字节。明确数学示例HEADER/FOOTER后的439170405字节、203287帧，不冒称真实PG完整导出。数学snapshot标签与本地签署检查点的证据类别在完整报告中明确。

原生产首次拒绝在 journal seq23963 TERMINAL/public ledger，第165414对象累计原材料268436418字节，超过原268435456；此时尚未加入检查点。完整预检第200001对象在runtime阶段，亦超原对象200000。原wire上限256MiB、frames400000、objects200000、journal100000、operations20000及所有组件/chunk/行上限保持；当前拒绝前不返回完整包，不静默截断，不产生VERIFIED报告。额外“每record检查点”原失败也保留，不能拿它替固定基线。

## 后续分页方案与硬门

后续正式包拟采用一次 READ ONLY REPEATABLE READ 捕获的固定 S/H、全部原件与运行观察，先完整有界物化整个不可变snapshot，再关闭TX；分页不能重读活动DB或为每页选新S/H。最多2页的固定基线候选足以容纳已测约419MiB编码材料，最终每页分割点、页/整体元数据开销、全量大小必须实际预检；不能把该估计称为已通过。每对象的全部块连续、保原typed身份/原字节及全局次序；完整manifest包含snapshot scope、S/H、页数/顺序/长度/SHA、全局计数和fold，任一页缺失、重复、替换、乱序或截断均不得给全task VERIFIED。

拟新增独立版本容器/profile，旧AG-TASK-EVIDENCE-2文件及其所有上限原义不变。外层单文件封装manifest和全部页，使现有四CLI参数/三个输入SHA仍能覆盖全部实际输入；禁止manifest引入URL、环境、网络、私钥或任意外部路径。原完整外部CP链、固定reader观察、bootstrap/全祖先四counter/RETRY/QUERY/TERMINAL/PUBLISH和未锚尾部诚实边界跨页统一验证，不能各页单独验证后拼凑“全量完整”。

新profile候选仍须有限整体上限（拟512MiB wire、最多2页/页256MiB、整体最多400000对象，整体operations20000/journal100000/frames400000及原单组件限制不减）；这些只是将来包审的参数提案，不修改现行门。必须核新增manifest/页封装开销、真实合法最大业务与所有拒绝/边界、有限磁盘与内存/TOCTOU/资源归属/断连/真进程死亡及恢复，不自动延有效期或释放预算。若提案实际仍不足，重新规划固定有界分区，不无限提限或删材料。

开始任何分页代码前需要新的正式范围/接口/所有权/运行矩阵及全新 PACKAGE_REVIEW，通过后再独立实施、自查和新 IMPLEMENTATION_ACCEPTANCE。A3.3/A3.4如需完整10000数据交付，必须先闭合该功能与验收依赖；本轮只完成A3.2原预检与正式规划、完整现行功能自查/独立验收，不自动进入下一段。项目仍PARTIAL。

原件索引：`artifacts/workflow/A3.2-evidence-20261011/s2-integrator-sol-low-r1/capacity-native3/` 的 generation.json/execution.json/immutable-dataset-preservation.json及原失败；独立计数 `counting-native1/`。正式实施/独立报告必须给具体原件路径/SHA与准确证据类别，不能只引用本规划数字。
