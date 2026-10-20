# C4未接受：原B迁移兼容与固定HTTPS测试域名环境

C4的high r1已STOP_NOT_ACCEPTED/own0，尚无发布。除query初次proof窗口竞争，low真实UID1001原B三文件17pass/2fail，legal001/003因旧assert仅期待到006，而当前bundle真实返回原剩余至006加008/009；007为audit单独lineage，不可简单range到010。原006前缀SQL与所有18迁移字节保持。原70TLS则真70passed，原environment/1001门真过，不能抵销此B失败。

授权部署worker仅helper的该原historical-adapted/b/test_r2_migrations.py物化适配及必要unit：原完整applied==旧剩余序列的语义作为prefix精确assert保留，再额外强制完整applied==该原剩余序列+['008','009']，禁止动态从actual推expected或只改range上界。新008/009安装/当前来源raw SHA与新增registry filename/version/checksum实际逐项绑定，完整registry/idempotent no-op/旧prefix registry/旧七业务表前后不变/非法历史回滚全部原assert保持。原.py.txt字节不改，适配记录明确为“当前追加迁移兼容资格”与物理映射区分，精确原/执行AST/SHA记录；不得称执行的旧6迁移whole-equality AST完全没变。

A32/A34真实34selected当前先4pass后固定域名DNS失败；原test自己在本机443启动真实audit reader或gateway，以固定https://audit.agent-guard.test及gateway.agent-guard.test请求并真验SAN。低诊断确认这两literal需真实OS loopback mapping，不是生产DNS问题。主控仅修改ephemeral GitHub runner CI：两域/etc/hosts映射127.0.0.1，确保可信该runner非root可bind443（仅该临时VM sysctl unprivileged_port_start=0），启动前真实DNS/SNI/443可用性检查。不得改用户Mac全局hosts/网络。

部署worker仅trusted嵌套create追加两条--add-host domain:127.0.0.1，原URL/SAN/TLS/错误CA/错域名断言不变，normal12roles DNS/权限不动。普通PGworker只可在自己的fresh控制器做同样--add-host；真实PG仍独立、pg-audit Dockeralias不同域名不混。两domain测试按原namespace顺序绑定443，不杀无关占用者。

root授权受控停r4已知B失败全域，保原实际partial/cancel与各70TLS/B/1001证据、strict own0；只补上述已确认测试兼容/环境再STOP。root并行独占CI/docs，query worker独占一函数互不写。新候选全内容冻结→全新high完整独验→最新exact head所有CI green→普通expectedSHA squash门保持。
