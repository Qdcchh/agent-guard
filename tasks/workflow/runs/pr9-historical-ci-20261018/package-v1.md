# PR9 历史验收CI修复包v1

## 真人授权与目标
用户要求最新分支PR到main合并；在完整集成预查发现阻断后，明确选择“先修复并补齐历史验收环境，CI 通过后再合并（推荐）”。当前分支codex/cosm2-2p-B，基线eafb6f28aa87a041e149c0190b76054424f1c9cf，PR https://github.com/Qdcchh/agent-guard/pull/9。主控唯一commit/push/merge；仓库仅允许squash。新授权覆盖旧发布禁止及必要历史验收装配修复范围；不把本轮当旧A3四万实验正式接受。

## 已有事实与失败
最新head远端非PG/迁移已PASS，PG正在运行。独占真实PG预查收集6839，早期失败后中断，执行133=48pass48fail37error，exit1（含中断teardown KeyError），不是完整结果。原件/公开脱敏证据在artifacts/pr9-ci-20261018/full-pg-preflight/。精确首因：test_a31_inherited_trusted_material中preverified_handle仅4参数，HTTP执行器传第5approval导致TypeError、503目标被500替代。其它缺A31审计独占DB、证据目录、AG32固定10000容量依赖、AG33最终资源清单/源码指纹。此前修复CI锁/Rust/Anvil、5份公开测试fixture和本地ZIP链接已提交，独验报告保留在artifacts/pr9-ci-20261018/。并行用户dirty style.css/汇报docx/TeX必须保留不提交。

## 验收矩阵
|ID|修复与实际证明|
|---|---|
|P9-01|完整6839原集成测试/原非PG全部保持；不能删测试、skip、降状态/预算/幂等/证据断言或缩范围冒充全绿|
|P9-02|修复旧preverified测试适配器签名，显式拒绝非空approval，保持真实原query/回滚/503/no-store/重放断言；真实PG全文件复验|
|P9-03|CI及本地真实独占authority/downstream/audit域和角色/证据目录，按所需真实数据库/容器隔离，不用同事务替代跨域；无普通共享DSN|
|P9-04|AG32容量输入自洽、原数字/边界测试原样；无假JSON或伪造历史、无敏感档案发布；明确真实来源/字节SHA/可重建命令，clean checkout能生成/安全取得所需输入。不得靠改原期望规避历史依赖|
|P9-05|AG33 source/wheel真实隔离安装、12角色/三PG/权限/源码binding和运行配置由当前源真实生成，不能假清单关闭旧源码校验；完整角色/部署/场景/注册/故障测试实跑|
|P9-06|调查后续完整套件发现的真实故障并最小修复，原业务安全不变量和18迁移不改；新范围涉及生产语义先串行冻结契约，不隐式扩张|
|P9-07|固定Python3.11、既有锁pipcheck、Rust1.99.1 locked、Anvil来源SHA、全局Ruff/format/Node、clean checkout无ignored本地前提；不虚称本地仿真为远端原生性能|
|P9-08|worker独占移交STOP，候选全部SHA/依赖/测试/fixture冻结，全新high独立实跑影响域/完整集成与负例探针；原失败/未跑/局限不掩盖|
|P9-09|精确发布候选，完整最新head GitHub所有CI成功、主控核对head/base及check，然后expectedSHA普通squash合并；不force/不绕过保护|
|P9-10|其它任务dirty/untracked不碰；秘密不入Git/公开输出，全部own PG/net/containers/keys/env清理到0，报告实际结果及边界|

## 组织与门控
先全新high PACKAGE_REVIEW。期间只读分析，不授业务写。包审ready后按独占边界：授权/query适配与基础CI装配；容量输入与可复现准备；部署角色/当前资源装配。共享ci.yml由主控唯一写，worker提供准确接口/命令。容量/部署准备先冻结接口再接CI，不消费半成品。每worker只在其独占文件、随机owner资源写；发现超出边界报告主控分配。全部writer停写后冻结完整候选，全新high IMPLEMENTATION_ACCEPTANCE。阻断真实保留并补正/换全新审查。不能用这次包审代实施接受。

## 资源及证据
只用新随机owner本轮PG16/网络/容器（可复用固定公共镜像，不复用旧owner/PG），记录fullID/label，退出清理own。测试authority/downstream/audit独立DB/连接/事务，部署12角色按原规范真实装配。私密env/keys0600目录0700，日志原件含秘密0600，公开副本脱敏/声明。历史档案只读取，不重写原SHA；大档案不未经检查上传Git。正式新生成输入另run，不冒称原历史实跑。所有命令/退出/JUnit/源指纹/来源映射进artifacts/pr9-historical-ci-20261018/{component}/。root按实际证据维护状态与PR描述，不以AI口头成功当PASS。
