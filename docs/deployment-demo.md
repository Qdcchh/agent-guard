# 正常隔离演示操作

联合v1 PACKAGE_READY，正常装配必要接口自查已完成，未接受。正常发行脚本为deploy/demo/supervisor.py、compose.yaml和Dockerfile；没有ignored历史驱动依赖。

宿主Python3只控制明确owned Docker资源；镜像为Python3.11.17，生产与开发锁安装、pip check、noneditable source或wheel。先准备固定synthetic注册公钥/CA与12角色独立UID、两个pair GID、三PG16 C/C/UTF8+verify-full。operator没有CREATEDB，holder没有DB/DS网络，offline没有网络/DB/private挂载。临时root只负责新owner的初始化/activation、公有冻结pack分发。

宿主持有operator bridge的私密stdin/stdout FD。operator私密0700临时目录Unix socket用SO_PEERCRED限制operator UID；normal与relay只接受固定action/role/run/owner。密码只在operator→planner私密输入链，不能日志/argv/共享文件；token留在holder并经两pair credential校验handoff。正常operator没有Docker socket、setuid或其他holder私密/IPC挂载。实际native role PID/UID/start/NULargv与宿主launcher PID分开记录。

运行README字面脚本；从外cwd执行时显式AG33_REPOSITORY为checkout绝对路径。supervisor --mode source|wheel --capacity-items 1|256 --run-id UUID --owner-id OWNER --evidence NEW_PATH；有限cap默认14400秒，失败/native exit和精确owned cleanup保留。--serve-only用于最终测试准备，测试入口使用allocated-resources.json/run.json及每case fresh owner；不要让多个维护case共享runtime。

授权真实browser root→两AS exchange→两个Unix handoff；root300/proof60，child240/180上界按parent剩余严格收窄。bootstrap前四authority writers真实native停止/凭据随容器stop卸载且PG sessions零；live host poll核原process身份。remote audit stream/key/principals提交后，独立authority exactdescriptor confirm。worker公平常驻处理不可变意图，publisher READY与DeliveryWorker独立TLS audit持久ACK。UNKNOWN保留预留、lease30及首次材料不变。

正常四工具完成后真drain/freeze独立trust/latest/history，以SELECT-only exporter生成有界task-bundle；offline无网络四参数验证。公共synthetic材料等实际最晚token失效后交付，保留当前授权UNKNOWN/下游ATTESTED/未锚尾部限制。256路径在provision前冻结s000..s255与112*274+144*273=70000，三holder一致，不改原caps。

维护最终闭合遵循test_a33_clean_deploy：停四writer，三domain as-of完整dump/restore逐列比较，历史kid/READYbytes及旧001/003非零升级保全、恢复behind external latest诚实GAP；新kid显式批准及持钥证明，旧kid disable拒绝外部新请求而既有内部恢复仍有效。该完整维护/12freshfull/sourcewheel各20继承组将在联合最终自查和新独立验收执行，本段不冒维护PASS。清理只核本run/owner的完整container/network ID与精确volume名，不prune或shared down。
