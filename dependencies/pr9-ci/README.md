# CI二进制依赖来源

requirements-ci.lock固定既有requirements.lock与requirements-dev.lock的19个包版本，并加入现有部署构建已经使用的setuptools80.9.0和wheel0.45.1；不改变业务运行依赖版本。只允许PyPI对应固定版本发布的wheel文件SHA，禁止隐式源码构建；SOURCES.json保存逐包metadata来源URL、原metadata SHA及各wheel文件URL/SHA。不同平台wheel均保留，具体Python3.11 Linux安装以pip兼容性选择并核对哈希。原runtime/dev锁保留，部署原版本断言继续执行。

主CI及部署镜像使用--require-hashes --only-binary=:all:安装此锁。本地项目的source/wheel构建使用已安装构建工具并禁用build isolation，避免从未锁定构建环境取得新版本。付款依赖继续使用既有requirements-x402.lock及其哈希来源，原Rust/Anvil校验不改。

ACTIONS.json记录解密输入所在CI job使用的官方Actions版本解析；workflow固定完整commit而不是可移动主版本标签，checkout不持久化Git凭据。全部能读取解密明文的当前源码、测试、构建逻辑和依赖都属于可信边界，单独限制Secret的step环境不能隔离后续代码。
