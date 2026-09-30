# 密码与编码配置 v1

状态：**MVP 配置已冻结，单实现可运行；双实现互操作验收尚未完成。** 本文只冻结密码原语和线格式，不代表授权链、账本或服务 API 已完成。

## 1. 冻结参数

| 项目 | v1 取值 |
| --- | --- |
| SM2 实现 | `tongsuopy==1.0.1`，底层为铜锁 Tongsuo |
| 曲线 | `sm2p256v1`（库内名称 `SM2`） |
| 摘要 | SM3 |
| SM2 用户标识 | ASCII `1234567812345678`，v1 固定，不由请求方传入 |
| 签名输入 | 域前缀与 RFC 8785 正文组成的完整消息；不在应用层预哈希 |
| 签名编码 | ASN.1 DER `SEQUENCE(INTEGER r, INTEGER s)` |
| 公钥编码 | X.509 SubjectPublicKeyInfo DER |
| 二进制 JSON 表示 | RFC 4648 URL-safe base64，无 `=` 填充，解码后重编码必须完全一致 |
| JSON 规范化 | `rfc8785==0.1.4`；UTF-8、拒绝重复字段、浮点数、负整数及大于 `2^53-1` 的整数 |

铜锁 Python SDK 的公开 API 不允许调用方配置 SM2 用户标识。v1 因此固定采用标准默认值，并用公开验签向量锁定这一行为。未来更换后端时必须先通过同一向量，不允许在验签失败后自动尝试其他用户标识、签名格式或曲线。

## 2. 精确消息格式

签名输入：

```text
ASCII("AGENT-GUARD/v1/" + domain + "\n") || RFC8785(payload)
```

允许的签名域为 `capability`、`invocation`、`result-read`、`receipt`、`checkpoint`。

摘要使用独立前缀：

```text
credential_digest = SM3(
  ASCII("AGENT-GUARD/v1/hash/credential\n") || RFC8785(signed_envelope)
)

chain_digest = SM3(
  ASCII("AGENT-GUARD/v1/hash/chain\n") ||
  RFC8785([BASE64URL(credential_digest_0), ..., BASE64URL(credential_digest_n)])
)
```

凭证按根到叶排序。改变 payload、签名、凭证数量或顺序都会改变相应摘要。

## 3. 依赖决策与边界

- `tongsuopy` 是铜锁项目的 Python SDK，Apache-2.0，PyPI 标注 Production/Stable，提供 Windows ABI3 wheel；本地已在 Windows 及 Python 3.12 验证。项目目标运行时仍为 Python 3.11，并由 CI 验证。
- `rfc8785` 由 Trail of Bits 维护，Apache-2.0，无运行时传递依赖。项目不自行实现 JSON 规范化算法。
- `requirements.lock` 固定运行时直接和传递依赖；修改依赖必须重新运行本文测试向量与全部安全测试。
- `tongsuopy` 的最新公开稳定版发布时间较早，且本机没有第二套 GmSSL/铜锁命令行实现。因此当前不能宣称完成“两种独立实现互验”。进入正式演示冻结前，必须用独立 GmSSL 或兼容实现完成双向验签，并记录版本、命令和结果。

私钥生成交给铜锁的随机数实现。仓库测试只生成临时密钥；公开向量仅包含公钥，不提交固定私钥、生产密钥或 `.env`。

## 4. 当前公共接口

`agent_guard.contracts`：

- `load_strict_json(raw)`：在规范化前拒绝重复字段和不安全数字。
- `canonical_json_bytes(value)`：生成 RFC 8785 字节。
- `b64url_encode` / `b64url_decode`：严格无填充 base64url。
- `signature_message` / `hash_message`：生成固定域分离输入。

`agent_guard.crypto`：

- `generate_sm2_private_key()`：生成临时 SM2 私钥。
- `serialize_sm2_public_key()` / `load_sm2_public_key()`：严格 SPKI DER 公钥交换。
- `sign_sm2_message()` / `verify_sm2_message()`：完整消息的 SM2-with-SM3 签名与验签。
- `create_signed_envelope()` / `verify_signed_envelope()`：协议签名信封。
- `credential_digest()` / `chain_digest()`：凭证及有序授权链摘要。

业务层不得直接绕过这些接口另建编码、域前缀或“先做 SM3 再让库签名”的路径。

## 5. 已执行与待执行验收

已自动化：

1. SM3 `abc` 标准向量；期望值为 `66c7f0f4...8f4ba8e0`。
2. [铜锁官方 SDK 示例](https://github.com/Tongsuo-Project/tongsuo-python-sdk/blob/main/demos/sm2_verify.py)所用 SM2 公开验签向量，消息为 `message digest`。
3. 临时密钥签名、篡改拒绝、错误域拒绝、DER 签名、SPKI DER 严格回读。
4. 重复 JSON 字段、浮点数、负数、越界整数、填充或非规范 base64url 拒绝。
5. 凭证摘要及链顺序绑定。

仍需完成：独立实现双向互验、密钥注册/轮换/撤销流程、硬件或密钥服务接入评估，以及授权 payload 的逐字段业务模式。
