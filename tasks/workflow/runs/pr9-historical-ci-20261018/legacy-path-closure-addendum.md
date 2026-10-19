# PR9 原20组两项确定物理路径缺口

只读closure分析确认并经root核对：historical-adapted/b三个r2测试仅把实际观察结果写到/evidence/logs，当前非root控制器既无该路径也无父目录写权限；environment_observer.py两处动态pathlib.Path('/e/'+mode+'-venv/...')未被已有连续字面量映射命中，实际/opt/runtime非editable路径会被错误拒绝。

candidate2已失效，部署worker当前停运行/补环境期间，授权在原helper materialize_legacy及对应单测完成纯物理映射：

- 将/evidence/logs替换为该consumer output/legacy/evidence-logs的真实0700目录，提前创建，文件继承umask077/0600；原B三测试的写入内容/HTTP400–499/FIFO/private/migration全部assert不变，日志保留在既有最终复制的私密结果树。不新增普通角色/evidence挂载，不另建跨consumer共享日志根。
- 两处动态venv lib/site-packages与share/agent-guard/migrations前缀替换为真实sys.prefix对应路径，只影响物理路径表达式。原逐模块/原14/current18迁移SHA、真实DB观察/非editable/UID及所有assert保持，原件不改、记录准确AST/bytes差异。

原observer对旧/e/{mode}-tests/src不存在的断言保留，不能谎称它证明当前/testsource/src不存在（当前readonly src专供139字节绑定，实际存在）。当前真实非editable direct_url、全139实际安装/import origin及逐SHA检查才是当前无源码遮蔽的门；两者证据意义分别明确。不得删除原assert或伪造observer输出。

用非root真实原B节点和原environment observer/source+wheel验证这些前提，再完整各20组。新scope与导出TLS/private tmpfs合并一轮STOP，root再冻结完整candidate3。fresh high、完整6839保持和exact head全CI green门不变。
