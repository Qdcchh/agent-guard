# TEST ONLY: 非常数时间参考副本，禁止作为生产签名或基准替代。
"""两方协同 SM2 签名 —— 参考实现（教学/原型用，非常数时间，勿用于生产）。

用途：给 B 的实现提供"标准答案"。实现方可以把这里的数学逐行搬进
src/agent_guard/cosign/，并用本文件的自测思路做交叉验证。

协议（半诚实模型，乘法分享 (1+d)^-1 = d1*d2 mod n）：
  密钥生成（无需可信 dealer）：
    P1: d1 <- [1,n-1],  发送 T1 = d1^-1 * G
    P2: d2 <- [1,n-1],  P = d2^-1 * T1 - G   （公钥，P != O）
  签名（消息 M，用户标识 ID = "1234567812345678"）：
    双方各自计算 e = SM3(Z_A || M)   —— 双方都必须自己从结构化行动算出 M，不得接收对方给的 e
    P1: k1 <- [1,n-1], Q1 = k1*G, 发送 Q1
    P2: 校验 Q1 在曲线上且非无穷远点；k2,k3 <- [1,n-1]
        (x1,_) = k3*Q1 + k2*G ; r = (e + x1) mod n ; r==0 则重来
        s2 = d2*k3 mod n ; s3 = d2*(r+k2) mod n ; 发送 (r,s2,s3)，立刻销毁 k2,k3
    P1: s = (d1*k1)*s2 + d1*s3 - r mod n ; s==0 或 s==n-r 则重来
        用公钥 P 做标准 SM2 验签，通过才输出 (r,s)；销毁 k1
  正确性：k = k1*k3 + k2，s = d1*d2*(k + r) - r = (1+d)^-1 (k + r) - r，即标准 SM2 签名。
"""

from __future__ import annotations

import hashlib
import secrets

# GB/T 32918.5 推荐曲线参数 sm2p256v1
P = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF
A = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC
B = 0x28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93
N = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123
GX = 0x32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7
GY = 0xBC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0
G = (GX, GY)
INF = None
DEFAULT_ID = b"1234567812345678"


def on_curve(pt) -> bool:
    if pt is INF:
        return False
    x, y = pt
    return 0 <= x < P and 0 <= y < P and (y * y - (x * x * x + A * x + B)) % P == 0


def add(p1, p2):
    if p1 is INF:
        return p2
    if p2 is INF:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return INF
    if p1 == p2:
        lam = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return (x3, (lam * (x1 - x3) - y1) % P)


def neg(pt):
    return INF if pt is INF else (pt[0], (-pt[1]) % P)


def mul(k: int, pt):
    k %= N
    result, addend = INF, pt
    while k:
        if k & 1:
            result = add(result, addend)
        addend = add(addend, addend)
        k >>= 1
    return result


def sm3(data: bytes) -> bytes:
    return hashlib.new("sm3", data).digest()


def i2b(v: int) -> bytes:
    return v.to_bytes(32, "big")


def za(pub, uid: bytes = DEFAULT_ID) -> bytes:
    entl = (len(uid) * 8).to_bytes(2, "big")
    return sm3(entl + uid + i2b(A) + i2b(B) + i2b(GX) + i2b(GY) + i2b(pub[0]) + i2b(pub[1]))


def digest_e(pub, msg: bytes, uid: bytes = DEFAULT_ID) -> int:
    return int.from_bytes(sm3(za(pub, uid) + msg), "big")


def rand_scalar() -> int:
    return secrets.randbelow(N - 1) + 1


def verify(pub, msg: bytes, sig, uid: bytes = DEFAULT_ID) -> bool:
    r, s = sig
    if not (1 <= r < N and 1 <= s < N) or not on_curve(pub):
        return False
    t = (r + s) % N
    if t == 0:
        return False
    pt = add(mul(s, G), mul(t, pub))
    if pt is INF:
        return False
    return (digest_e(pub, msg, uid) + pt[0]) % N == r


# ---------------- 两方协议 ----------------
class Party1:
    """执行域（发起方 / 输出最终签名）。"""

    def __init__(self):
        self.d1 = rand_scalar()
        self.pub = None
        self._k1 = None

    def keygen_msg(self):
        return mul(pow(self.d1, -1, N), G)

    def set_public(self, pub):
        if not on_curve(pub):
            raise ValueError("bad public key")
        self.pub = pub

    def sign_round1(self):
        if self._k1 is not None:
            raise RuntimeError("session already open")
        self._k1 = rand_scalar()
        return mul(self._k1, G)

    def sign_round3(self, msg: bytes, r: int, s2: int, s3: int):
        k1, self._k1 = self._k1, None  # 一次性：无论成败都销毁
        if k1 is None:
            raise RuntimeError("no open session")
        if not all(1 <= v < N for v in (r, s2, s3)):
            raise ValueError("bad partial values")
        s = (self.d1 * k1 * s2 + self.d1 * s3 - r) % N
        if s == 0 or s == N - r:
            raise ValueError("degenerate s, retry")
        if not verify(self.pub, msg, (r, s)):
            raise ValueError("final signature does not verify; abort")
        return r, s


class Party2:
    """授权域（响应方，无跨轮状态）。"""

    def __init__(self):
        self.d2 = rand_scalar()
        self.pub = None

    def keygen_finish(self, t1):
        if not on_curve(t1):
            raise ValueError("bad T1")
        pub = add(mul(pow(self.d2, -1, N), t1), neg(G))
        if pub is INF:
            raise ValueError("degenerate key, regenerate")
        self.pub = pub
        return pub

    def sign_round2(self, msg: bytes, q1):
        if not on_curve(q1):
            raise ValueError("bad Q1")
        e = digest_e(self.pub, msg)
        while True:
            k2, k3 = rand_scalar(), rand_scalar()
            pt = add(mul(k3, q1), mul(k2, G))
            if pt is INF:
                continue
            r = (e + pt[0]) % N
            if r == 0:
                continue
            s2 = self.d2 * k3 % N
            s3 = self.d2 * (r + k2) % N
            return r, s2, s3


def cosign(p1: Party1, p2: Party2, msg: bytes):
    for _ in range(8):
        q1 = p1.sign_round1()
        r, s2, s3 = p2.sign_round2(msg, q1)
        try:
            return p1.sign_round3(msg, r, s2, s3)
        except ValueError as exc:
            if "degenerate" not in str(exc):
                raise
    raise RuntimeError("too many retries")


def der_signature(r: int, s: int) -> bytes:
    def enc(v):
        b = v.to_bytes((v.bit_length() + 7) // 8 or 1, "big")
        if b[0] & 0x80:
            b = b"\x00" + b
        return b"\x02" + bytes([len(b)]) + b

    body = enc(r) + enc(s)
    return b"\x30" + bytes([len(body)]) + body


def public_key_pem(pub) -> str:
    import base64

    # SubjectPublicKeyInfo: id-ecPublicKey + sm2p256v1 (1.2.156.10197.1.301)
    prefix = bytes.fromhex("3059301306072a8648ce3d020106082a811ccf5501822d03420004")
    der = prefix + i2b(pub[0]) + i2b(pub[1])
    b64 = base64.b64encode(der).decode()
    return (
        "-----BEGIN PUBLIC KEY-----\n"
        + "\n".join(b64[i : i + 64] for i in range(0, len(b64), 64))
        + "\n-----END PUBLIC KEY-----\n"
    )


if __name__ == "__main__":
    assert on_curve(G)
    p1, p2 = Party1(), Party2()
    pub = p2.keygen_finish(p1.keygen_msg())
    p1.set_public(pub)
    msg = b'AGENT-GUARD-COSM2-ACTION-V1\n{"demo":1}'
    sig = cosign(p1, p2, msg)
    assert verify(pub, msg, sig)
    assert not verify(pub, msg + b"x", sig)
    print("self-test ok")
