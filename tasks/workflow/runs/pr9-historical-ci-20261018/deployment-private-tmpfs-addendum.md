# PR9 trusted嵌套控制器原/private环境门装配

部署worker以真实LinuxUID1001独立探针证实：原_environment_gate固定mkdir('/private')，非root controller不能在/新建目录。临时证据native-linux-private-root-uid1001.json，未读秘密、own0。当前本机UID0可隐藏这个GHA非root必现错误；必须补足环境，不能放宽原observer路径/身份断言。

candidate2已经因导出TLS缺前提而失效，无high审查进行。进一步仅授test_a33_clean_deploy.py的trusted嵌套create装配：为/private增加独立tmpfs，以当前实际os.getuid()/os.getgid()绑定owner，mode0700，并用rw,noexec,nosuid,nodev和有限大小（16MiB足供原runtime.json）约束。原/private/runtime.json路径、原environment observer与原139/source/migration/UID断言保持，文件umask077/0600。普通12角色不获得此mount、Docker.sock或任何新权限。

与export-tls补充合并在一次source补正STOP后冻结新候选；原r3已过2mode真实探针保留，未完成的全域停止/部分状态如实记载。新tmpfs必须在真实LinuxUID1001执行原环境gate及private mode/owner/write-positive/无权UID拒绝控制，仍只依据自身fullID/owner/run回收资源。完整四文件/20组、全新high及exact head所有CI仍为门槛。
